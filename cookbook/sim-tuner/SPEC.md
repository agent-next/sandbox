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
  `heldout_err < 0.018` AND `heldout_err < 0.30 × default_err`, where
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
| noise floor: hidden truth vs held-out, with the 1.5 % noise | 0.01492 |
| default (uncalibrated MJCF) parameters vs held-out | 0.07795 |
| 30 % of the default error (the G3 relative cap) | 0.02338 |
| held-out error of the shipped `examples/good/params.json` | 0.01638 (frac 0.210 of default) |
| per-parameter range-edge mutants from the good fit | 0.017–0.67 for the two `solref` edges … the `mu` edge |
| the train-overfitted ("fits the noise") mutant | 0.04135 |
| the "every parameter 6 % of range off truth" mutant | 0.10641 |

G3's absolute cap 0.018 is 1.2× the measured noise floor: close enough that
only a genuine fit inside the noise band passes, far enough that the shipped
artifact (0.01638, well inside its own search's GPU estimate) passes with ~8 %
margin. The two weakly-identifiable `solref` edge mutants land at
0.0167–0.0226 and are the floor of the mutant band; at 0.018 they are either
killed outright or — where borderline — carried by the band of remaining
mutants and by the kill-rate rule (the mutants exist to prove the judge kills,
and it does on 14 of 15 by G3/G1). The relative cap (30 % of default) is the
independently meaningful "much better than doing nothing" rule.

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
otherwise) and checks determinism. Note on the two `solref` edge mutants:
contact solref is weakly identifiable in this 1 s scene — a parameter fitted
near the opposite edge still scores within the honest-fit band. The judge
tolerates that band on purpose (it is what a real system-ID campaign on this
rig would look like) and still rejects it once the fit is biased on the
strongly-identifiable parameters. The self-test reports per-mutant survival;
a survival on a `solref` edge is documented in RECEIPT.md.
