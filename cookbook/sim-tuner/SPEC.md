# sim-tuner: GPU-batched sim-to-real system identification — SPEC

An agent works inside a disposable sandbox on a real robotics engineering
problem: calibrate the hidden MuJoCo contact and actuation parameters of a
box-and-arm test rig from noisy "real robot" recordings, then prove the
calibration on recordings it has never seen. The judge decides; the artifact
is a five-number `params.json`. The evaluation loop the agent is expected to
build is one batched `mujoco_warp` run over hundreds of parallel worlds on a
4 GiB GPU slice — the workload that justifies the GPU sandbox.

## Goal

- Artifact: one JSON file, `params.json`, with the five calibrated physics
  parameters (table below), passing every gate below.
- Judge: `judge/grade.sh` with numeric, deterministic pass rules. Physical
  scoring (G2/G3) is host-side CPU MuJoCo 3.8.1, an engine independent of the
  GPU numerics the agent optimised against; G4 then re-scores the artifact on
  a fresh GPU slice and requires the two engines to agree.
- Self-test: `judge/selftest.sh` proves the judge fails known-bad artifacts.

## Non-goals

- Learning dynamics outside the five named parameters. Everything else in
  the model (masses, geometry, servo gains, timestep, gravity) is known and
  fixed; the MJCF is in `judge/engine.py` and printed by `run.py`.
- Robustness to model-structure error (the rig IS a MuJoCo simulation with
  measurement noise; the sim-to-real gap modelled here is parameter error,
  not structure error).
- Speed targets on the GPU loop: timings are measured and reported, never
  gated.
- GPUs other than the RTX 5090 slice served by the agent-next `accel` lease
  API, and MuJoCo versions other than 3.8.1.

## The artifact contract

`params.json` is a strict JSON object with exactly these five keys, each a
finite JSON number inside its physical range:

| name | range | what it is |
|---|---|---|
| `mu` | [0.15, 0.90] | sliding friction coefficient of the box-table pair |
| `solref_tc` | [0.005, 0.020] | contact solref time constant [s] |
| `solref_dr` | [0.80, 1.60] | contact solref damping ratio |
| `damping` | [0.02, 0.35] | hinge joint damping [N·m·s/rad] |
| `armature` | [0.005, 0.060] | hinge armature [kg·m²] |

Anything else — an extra key, a missing key, a string, `NaN`, an out-of-range
value — fails gate G1 before any physics runs. Values are never clamped into
range: an out-of-range artifact is rejected, not fixed.

## The scenario (what is simulated)

The rig is a 0.2 kg box sliding on a plane and a 2-link arm with position
servos (`kp=60`), simulated at 2 ms for 1.0 s per recording, with a step in
both servo commands at t = 0.5 s. Six signals are sampled every 8 ms (125
samples per recording): `box_x, box_z, q1, q2, q1dot, q2dot`.

From `--seed` (default 7) the judge derives:

- the hidden ground-truth parameters, uniform in the ranges above;
- 10 initial conditions (box velocity, 4 servo command values), split into
  6 train recordings (given to the agent's tools as `data.npz`) and
  4 held-out recordings (never leave the judge);
- reference trajectories from hidden-truth CPU MuJoCo 3.8.1, with seeded
  Gaussian measurement noise of 1.5 % of each signal's train RMS added to
  both splits.

Ground truth and held-out data exist only as a deterministic function of the
seed inside `judge/engine.py`; nothing the artifact can read carries them, and
the artifact is graded from a copy in a fresh temp dir. sha256 of every file in
`judge/` is compared before and after grading (`judge_intact` in the verdict).

## Judge gates (numeric pass rules)

`judge/grade.sh <params.json> [--seed N] [--json out.json] [--cpu-only]` exits
0 only if every gate passes. `--cpu-only` skips G4 (no GPU lease created); the
verdict then records G4 as skipped and the run cannot fully pass the demo's
promise — the full judge always needs the GPU check.

- **G1 ranges** — the artifact parses as strict JSON, is ≤ 16 KiB, has exactly
  the five keys, each finite and inside its physical range.
- **G2 training error (reported)** — CPU MuJoCo re-simulation of the artifact
  against the six train recordings: RMS mismatch over all samples and signals,
  each signal normalised by its train RMS. Reported for information; the
  binding error gates are on held-out data. Pass: always records (never gates)
  so that mutants fail on the informative gate.
- **G3 held-out error** — CPU MuJoCo re-simulation against the four held-out
  recordings (different initial conditions, same hidden rig): pass iff
  `heldout_err < 0.025` AND `heldout_err < 0.30 × default_err`, where
  `default_err` is the held-out error of the uncalibrated MJCF defaults.
  `--cpu-only` grades G1–G3.
- **G4 GPU/CPU agreement** — the artifact is scored once more on a fresh 4 GiB
  GPU slice: one batched `mujoco_warp` 3.8.1 run (`nworld = 6`, the six train
  recordings 500 steps each), error over the train split. Pass iff
  `|gpu_err − cpu_err| ≤ 0.003` AND `≤ 10 %` of the CPU error. This kills any
  artifact that only "works" through a mismatch between the two engines, and
  proves the batch evaluator the agent loop relies on measures what the judge
  measures. The lease stack (mujoco 3.8.1, mujoco-warp 3.8.1, warp 1.13.0,
  numpy, Python, kernel release) is checked against `judge/version-table.json`
  (written by `judge/setup.sh --record` on the reference lease); a mismatch
  fails the grade with the differing fields named.

### Calibration of the thresholds (measured, CPU MuJoCo 3.8.1, seed 7)

| quantity | measured |
|---|---|
| noise floor: hidden truth vs held-out, with the 1.5 % noise | 0.01400 |
| the default-parameter error (measured per grade; it rides the scenario) | 0.118–0.883 across the shipped metric revisions |
| weakest range-edge mutant (`solref_dr` at 0.80) | 0.03948 (2.82× floor) |
| strongest range-edge mutant (`mu` at 0.15) | 0.62888 (44.9× floor) |
| all ten range-edge mutants | 0.039–0.629 (2.8×–44.9× floor) |
| honest-fit scatter: one parameter ± 5 % of range off truth | 1.05×–7.0× floor |
| honest-fit scatter: one parameter ± 20 % of range off truth | 1.35×–16.3× floor |

The G3 relative cap is 30 % of the default error, recomputed at every grade
from the same seed, so the ratio travels with metric changes; the numbers in
this table are what grade run r3 measured (default 0.11849). Two scene
choices make this band wide enough to gate on, both measured:

1. **The `box_zdot` channel is recorded** (vertical velocity of the box). The
   box is airborne until its landing, so this channel is ~0 everywhere except
   the landing transient, which is exactly what `solref_tc`/`solref_dr` shape.
   Without it, `solref` edge mutants score 1.01–1.08× the noise floor — inside
   the honest-fit scatter — and no threshold separates them.
2. **That channel is normalised by a peak scale** (95th percentile of
   |signal|), not its RMS. The RMS of a mostly-zero channel sits ~4× below the
   transient amplitude; RMS normalisation then amplifies landing-timing error
   at the 8 ms observation frame until the metric has a sub-1 % needle at
   truth (0.0149 at truth, 0.19 at one 13×13-grid step — 1.3 % of range —
   away in `solref_tc`). Peak normalisation keeps the transient the channel's
   content (edge mutants 2.8–45×) while making the neighbourhood of a fit
   continuous (approaching truth the metric descends 0.30 → 0.15 → 0.075).

G3's absolute cap 0.025 is 1.6× the noise floor and 1.6× below the weakest
edge mutant: a genuine fit must land within a few percent of range per
parameter (the honest-fit scatter at ± 5 % of range reaches 7× floor), and
every range-edge mutant fails by ≥ 1.6×. The relative cap (30 % of default =
0.265) is the independently meaningful "much better than doing nothing" rule
and independently rejects the defaults and the extreme mutants.

## Acceptance oracle

The judge never trusts "the solver ran" or any error the artifact reports
about itself. The acceptance oracle is the hidden ground truth, used twice
removed: seeded generation of (a) the true parameters and (b) recordings the
agent never sees, with the candidate re-simulated from the same MJCF by the
second engine of the pair (CPU for scoring, GPU for the cross-check). The
attacker-visible surface is five floats in a JSON file; there is nothing in
the artifact to overfit to except physics.

## Toolchain (pinned)

- Judge host venv (`judge/setup.sh`, `$HOME/.venvs/sim-tuner`): CPython
  3.10–3.13 on x86-64 Linux, `mujoco==3.8.1`, `numpy==1.26.4` (3.10–3.12) or
  `numpy==2.1.3` (3.13; 1.26.4 has no cp313 wheel). All pins sha256-checked via
  pip `--require-hashes` from `judge/requirements.lock`. What was actually
  installed is recorded to `judge/VERSIONS.txt` at setup time.
- GPU lease stack (RTX 5090 slice, `vram_gb: 4`, `reserve: exec`): NOT
  installed by setup — validated. `judge/setup.sh --record` leases a fresh
  slice, records its versions to `judge/version-table.json`, and destroys the
  lease. Every grade then compares the served lease stack against that table
  (G4); a mismatch is a judge failure naming the field, per the demo standard
  ("for GPU jobs setup mostly validates the lease stack versions and fails if
  they differ from SPEC").

## Reproducibility

- Deterministic given `--seed`: scenario, noise, reference trajectories and
  CPU errors are pure functions of the seed on a pinned toolchain; G4 compares
  against the CPU number the same process just computed. `selftest.sh`
  requires two same-seed grades of the good artifact to produce byte-identical
  verdict JSON except the `timing` key (which also carries the lease's
  creation time and exec wall times).
- The default error and the noise floor are recomputed per grade, so the G3
  rule travels with the seed; `--seed 8` is a valid independent reproduction.
- RECEIPT.md carries two fresh-sandbox runs (setup → selftest → grade, exit
  codes, kill rate, key numbers, wall times, versions, deviations).

## Known-bad examples (self-test)

`judge/mutants.py` scripts ≥ 10 mutants of `examples/good/params.json`:
each single parameter pushed to both range edges (10), the uncalibrated MJCF
defaults, a "6 % of range off truth on every parameter" band mutant (derived
from the hidden truth, not from the good fit), a params vector fitted to the
train recordings only (fits the 1.5 % noise; produced by an L-BFGS-B/local
search against the train split starting from a 512-sample random rest), a
swapped-units pair (damping ×10, armature ÷10), plus structure violations:
extra key, `NaN`, string value, out-of-range. `judge/selftest.sh` grades the
good artifact (must pass G1–G4 on a real GPU lease), then every mutant (each
must fail ≥ 1 gate), prints the kill rate (must be ≥ 90 %, exits non-zero
otherwise) and checks determinism. With the `box_zdot` channel and peak
normalisation, every range-edge mutant fails G3 by ≥ 1.6× (2.82× floor at the
weakest, `solref_dr` at 0.80) — contact parameters are identifiable from the
landing transient, so no edge survival is expected or tolerated.
