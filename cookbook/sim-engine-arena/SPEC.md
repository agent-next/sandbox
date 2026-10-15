# sim-engine-arena: physics-engine agreement demo — SPEC

An agent works inside a disposable sandbox on a real simulation-engineering
problem: port one neutral scene spec into a physics engine it may have
never used (MuJoCo), producing four rigid-body trajectory datasets, which a
judge it cannot fool scores against analytic oracles the agent never sees.
The judge never accepts "the solver ran": every scenario has a closed-form
answer derived from Newtonian mechanics, and the trajectory must land on
it within stated tolerances. Inspired by Manda Robotics' physics-engine
primer (https://mandarobotics.com/blog/comparing-physics-engines/primer.html),
which contrasts what different engines do on the same scenes; this demo
adds the missing piece — an analytic referee.

## Goal

- Artifact: one Python file (`sim.py`) that reads `spec.json` (the neutral
  scene spec below), builds each scenario in **MuJoCo**, steps it at the
  spec timestep, and writes one CSV per scenario: `traj_drop.csv`,
  `traj_incline_stick.csv`, `traj_incline_slide.csv`, `traj_pendulum.csv`.
- Judge: `judge/grade.sh` runs the artifact in the sandbox, then scores the
  trajectories against the analytic oracles with numeric, deterministic
  pass rules, plus cross-engine agreement with the judge's own reference
  MuJoCo port.
- Self-test: `judge/selftest.sh` proves the judge fails known-bad ports.

## Non-goals

- Other engines for the artifact (PyBullet, Genesis, Drake): the public
  artifact contract is MuJoCo only. (The original internal version ran
  four engine lanes; the cross-engine comparison here is the judge's
  reference port versus the agent's.)
- Tuning contact-solver parameters, damping or friction beyond the spec:
  the scenes are deliberately simple so the analytic answers hold.
- GPU execution as a gate: the optional `run.py --gpu` lane replays the
  MuJoCo MJCF on a GPU slice and is reported in the table but never gates.
- Continuous collision, air drag, or relativistic corrections: the oracle
  tolerances absorb the engines' contact-model differences.

## The neutral scene spec (`spec.json`, committed in `judge/`)

The agent sees `spec.json` and nothing else — it contains geometry, masses,
friction, timestep and required CSV outputs, and **no expected results**.
Values (SI): gravity 9.81 m/s² along −z, timestep 0.001 s, friction μ = 0.5.

| scenario | setup | output CSV | oracle (agent never sees this column) |
|---|---|---|---|
| drop | 1 kg rigid sphere (r = 0.05 m) released from rest, center at z = 1.0 m, onto a static horizontal plane at z = 0 | `traj_drop.csv` (t, z, vz) | center reaches r at t = √(2(z₀−r)/g) = 0.4401 s |
| incline_stick | 1 kg box (0.1 m cube) at rest on a plane tilted 20° about y, descending toward +x, μ = 0.5 | `traj_incline_stick.csv` (t, x, z, vx, vz) | tan(20°) = 0.364 < μ: the box stays put |
| incline_slide | same, tilt 35° | `traj_incline_slide.csv` (t, x, z, vx, vz) | slides downhill with a = g(sin θ − μ cos θ) = 1.6088 m/s² |
| pendulum | 1 kg point mass on a massless rigid link L = 1 m, hinge at (0, 0, 2.0), released from rest at θ₀ = 0.1 rad | `traj_pendulum.csv` (t, theta, omega) | period T = 2π√(L/g)·(1 + θ₀²/16) = 2.0073 s (finite-angle corrected) |

Durations: drop 1.5 s, inclines 1.0 s, pendulum 10 s. CSVs have a header
row and one row per timestep with t starting at 0.

## The artifact contract

`sim.py` is a Python program that:

1. reads `spec.json` from the current directory;
2. for each scenario in `spec["scenarios"]`, builds the scene in MuJoCo
   from the spec's geometry and initial conditions;
3. steps the simulation at `spec["timestep_s"]`;
4. writes each scenario's CSV with exactly the spec's `columns` header.

Rules the judge enforces structurally: the port must be MuJoCo-based (the
text must use the `mujoco` package), must read the spec at runtime (not
hardcode the scene), must not hardcode oracle numbers (any of the values
0.4401, 1.6088, 2.0073, or a numeric literal within 2 % of one in the
artifact text is rejected — see gate 1), and must record the true
trajectory (rows must advance in t; the judge checks monotonicity and row
count in gate 3). The judge runs the artifact from a copy; sha256
checksums of `judge/` before and after must match.

## Judge gates (numeric pass rules)

`judge/grade.sh <artifact> [--seed N] [--json out.json] [--skip-run]`
exits 0 only if gates 1–5 all pass. `--seed` (default 0) is recorded in the
verdict and offsets the reference-port seed (the reference is re-run every
grade so the comparison stays live). `--skip-run` re-scores CSVs already
present next to the artifact instead of re-running the sim (used by
`examples/good/loop.json` bookkeeping, never by selftest).

1. **structure** — `sim.py` is at most 96 KiB, byte-compiles, uses the
   `mujoco` package, reads the spec at runtime (`spec.json` load in text),
   and contains no hardcode-scanned oracle literal (the four oracle
   numbers above, or any numeric literal in the file within 2 % of one).
2. **run** — the artifact runs in the sandbox's judge venv and exits 0
   within 900 s, writing all four CSVs. A crash, a missing CSV, or a
   timeout fails this gate.
3. **csv-shape** — for every scenario: the header matches the spec's
   `columns` exactly, row count is within [0.9, 1.1] × (duration/timestep
   + 1), t starts at 0, strictly increasing, last t ≥ 0.8 × duration, and
   every value parses as a finite float.
4. **oracle** — for every scenario, the trajectory meets the analytic rule:
   - drop: the first time the center reaches z = r, interpolated between
     bracketing rows, is within ±3 % of √(2(z₀−r)/g) (0.4401 s);
   - incline_stick: total travel along the slope < 2 cm in 1 s (stick);
   - incline_slide: the box moves (travel > 10 cm) and the acceleration
     fitted to the downhill coordinate (least squares on s = ½at² after
     5 cm of travel) is within ±5 % of g(sin θ − μ cos θ) (1.6088 m/s²);
   - pendulum: the mean period from upward zero-crossings of θ (centered
     on its mean) is within ±2 % of the finite-angle-corrected period
     T = 2π√(L/g)·(1 + θ₀²/16) (2.0073 s for θ₀ = 0.1 rad).
5. **agreement** — cross-engine agreement: the agent's trajectory is
   compared with the judge's own reference MuJoCo port (`judge/ref_sim.py`,
   same spec, judge-controlled seed). For each scenario the max pointwise
   deviation on the shared columns (z for drop; slope coordinate s for the
   inclines; θ for the pendulum, phase-aligned by first crossing) is at
   most 5 % of the scenario's spatial scale (see tolerances below).

Tolerances (stated once, used everywhere):

| quantity | tolerance |
|---|---|
| drop contact time | ±3 % of 0.4401 s (±13 ms) |
| incline_stick travel | < 0.02 m |
| incline_slide acceleration | ±5 % of 1.6088 m/s² |
| pendulum period | ±2 % of 2.0073 s |
| reference agreement | ≤ 5 % of per-scenario scale: 0.05 m (drop z), 0.05 m (incline s), 0.02 rad (pendulum θ) |

The tolerances are loose enough that a correct port in MuJoCo passes with
margin (measured: good port lands at +0.1 % on every oracle), tight
enough that every scripted mutant fails at least one gate.

## Acceptance oracle

The judge never trusts the artifact's own idea of correct. Correctness is
decided by closed-form Newtonian mechanics (free-fall time, static
friction criterion, sliding-with-friction acceleration, pendulum period
with finite-angle correction), plus an independent reference tool — the
judge's own MuJoCo port run under a judge-controlled seed — as the
cross-engine agreement check. An artifact that merely "runs" without
matching the oracles fails.

## Known-bad examples (self-test)

`judge/mutants.py` derives 8 known-bad artifacts from the known-good one
by scripted single edits:

| mutant | edit | gate that kills it |
|---|---|---|
| time_stretched | t column × 1.3 (the source's negative) | oracle (drop time +30 %) |
| wrong_gravity | gravity 9.81 → 3.71 (Mars) | oracle (all scenarios) |
| friction_ignored | μ 0.5 → 0.0 | oracle (stick slides, slide accel −31 %) |
| wrong_timestep | dt 0.001 → 0.02 | csv-shape (row count) + oracle |
| pendulum_length_off | link length × 1.1 | oracle (period +10 %) |
| incline_sign_flip | plane tilt sign flipped | oracle (stick slides, slide sticks) |
| plus a compile error and a hardcode rejection | | structure |

`judge/selftest.sh` grades the known-good (must pass) and every mutant
(each must fail ≥ 1 gate), prints the kill rate, and checks determinism
(two grades of the good artifact produce byte-identical verdicts except
the `timing` key). It exits non-zero unless the kill rate is ≥ 90 %.

## Determinism

MuJoCo is deterministic for a fixed model and initial state; the reference
port is seeded via `--seed`. Two grades of the same artifact give
byte-identical verdict JSON except `timing` — enforced by `selftest.sh`.

## Toolchain (pinned, sha256-checked)

`judge/setup.sh` installs into `$HOME/.venvs/sim-engine-arena/` exactly:
mujoco 3.8.1, numpy 2.5.3, and the small closure, every wheel pinned with
sha256 through pip's `--require-hashes` mode (`judge/requirements.lock`).
Wheels cover CPython 3.10–3.13 on x86-64 Linux; every pinned release
predates 2026-09-30 (nothing published in the two weeks before this demo
was built; numpy pinned to 2.5.3 because 2.5.4 is 2026-10-10, and mujoco
3.8.1 to match the GPU lease image, so the CPU judge and the GPU lane run
the same engine version).
`judge/VERSIONS.txt` records what setup actually installed.

## GPU lane (optional, never a gate)

`run.py --gpu` creates a 4 GiB VRAM slice lease over the agent-next REST
API (`POST /sandboxes {"accel":{"vram_gb":4,"reserve":"exec"}}`), uploads
the agent's four MJCF models (the good port writes them next to the CSVs),
replays each on the lease with mujoco_warp 3.8.1, scores the replays
against the same oracles, shows the results in the table, and always
`DELETE`s the lease in `finally`, confirming with `GET` → 404. The lease
image ships warp-lang 1.13.0 / mujoco 3.8.1 / mujoco-warp 3.8.1
preinstalled; setup for GPU jobs mostly validates those versions and
fails if they differ from this section.
