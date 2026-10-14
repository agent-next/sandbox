# Standing the RoboParty RP1 humanoid in MuJoCo

## Goal

Show an agent writing a real robot controller — a PD tracker with a simple
balance law on a free-floating humanoid — and having a physics judge it
cannot fool decide whether the result is right.

The agent produces **`controller.py`**, a Python module (standard library
plus `numpy` and the pinned `mujoco` wheel only) that drives the
[RoboParty RP1](https://github.com/Roboparty/RP1) open-source humanoid for
10 s of flat-ground standing in MuJoCo, surviving a 30 N lateral push at
t = 5 s.

## The robot

The robot model is the upstream
[rp1_description](https://github.com/Roboparty/rp1_description) repository
at commit `84529a55649b5c9796d49093c266208c879f9f29` (2026-08-20):
`mjcf/rp1_flat.xml` (scene: floor + include), `mjcf/robot_24dof.xml`
(the 24-dof robot), `urdf/rp1_24dof.urdf` (the URDF it was converted
from).

Note that at this SHA, upstream's `rp1_flat.xml` includes `robot.xml`
(the 30-dof variant), not `robot_24dof.xml`. The judged model is the
24-dof one, so the judge builds the scene locally: it copies
`mjcf/` + `meshes/` into a scratch directory and rewrites the scene's
`<include file="robot.xml"/>` to `<include file="robot_24dof.xml"/>`.
That scene — not the upstream include graph — is what is compiled and
compared against `urdf/rp1_24dof.urdf`.

**Licence:** the upstream robot-model repository carries no licence file.
This demo therefore never copies its files into this repository;
`judge/setup.sh` clones it at the pinned SHA into `$HOME` at run time.

Key model facts (pinned revision):

| fact | value |
|---|---|
| actuated joints | 24 hinge joints (6 per leg, 2 waist, 5 per arm) |
| base | `base_link`, floating, initial pelvis height 0.78 m |
| inertial tags | 24 moving bodies + `base_link`, explicit `<inertial>` on each |
| actuator limits | hips/knees/waist ±141.7 N·m, ankles ±70.6, arms ±35.3 (MuJoCo `ctrlrange`) |
| joint ranges | per-joint `range` in the MJCF; note two **upstream sign quirks** below |
| URDF `effort` | hips/knees/waist 141.7, ankles 70.6, arms 35.3 N·m |
| URDF joints | all 24 `revolute`, with `lower`/`upper` on every joint |
| floor | infinite plane, `friction="0.9 0.2 0.2"`, `condim=4`, `solref="0.01 1"` |

Two **upstream mirror-sign quirks** the model gate must accept (they are
consistent between URDF and MJCF; they are findings about the upstream
model, not failures of the artifact):

- `right_hip_roll_joint` range is `[-2.6, 0.74]` (left is `[-0.74, 2.6]`)
- `right_knee_joint` range is `[-0.06, 2.83]` (left is `[-2.83, 0.06]`)

## What the agent writes

A single file, `controller.py`, imported by the judge's simulation loop.
Contract:

```python
import mujoco, numpy as np

class Controller:
    """10 s flat-ground stand; 30 N lateral push at t=5 s for 0.2 s."""
    def __init__(self, model: mujoco.MjModel, data: mujoco.MjData,
                 params: dict): ...
    def compute_ctrl(self, t: float) -> np.ndarray:
        """mu = 24 actuator commands, already inside each actuator's
        ctrlrange.  `t` is data.time at the call instant."""
        ...
```

- `params` is the dict from `judge/params.json` (joint map, home pose,
  push profile, limits). The controller may use `model`, `data`, `params`;
  nothing else from `mujoco`.
- The judge runs the physics loop itself (fixed 0.5 ms, 2 kHz, decimated
  to the model's 5 ms as needed) and calls `compute_ctrl` once per control
  step (5 ms). The controller sees the *full* simulator state through
  `data` — this is a simulation demo, not a hardware estimator demo.
- The controller may not write files, open sockets, read the filesystem
  outside its own directory, or import anything but the Python stdlib,
  `numpy` and `mujoco`. The runner enforces this with a file-access audit.

## Non-goals

- Not a walking or locomotion demo; the feet never leave the floor.
- Not a hardware demo: no latency, no torque ripple, no IMU noise. The
  model's sensor tags carry `noise=`/`cutoff=` but the judge reads the
  true state.
- Not a learning demo: no training loop, no checkpoint, nothing downloaded
  at run time beyond the pinned tools in `judge/setup.sh`.
- No rendering: headless, CPU-only, no meshes are needed for physics
  (collision geoms are capsules; mesh geoms are `contype=0`).
- Not a benchmark: wall time is reported, not graded.

## The judge's copy of the world

`judge/setup.sh` installs the pinned `mujoco` wheel (exact version,
sha256-checked) into `$HOME/.rp1-mujoco-tools/` and clones
`rp1_description` at `84529a55649b5c9796d49093c266208c879f9f29` into
`$HOME/.rp1-mujoco-tools/rp1_description`. The judge assembles its scene
by loading `mjcf/rp1_flat.xml` from that clone. Nothing from the artifact
is placed on the model's path.

The judge monkey-patches nothing in the artifact's process; instead the
artifact is imported into the judge's own simulator process and its file
accesses are audited (Python `sys.addaudithook`): any `open` outside the
artifact's own directory and the site-packages of `numpy`/`mujoco`, or any
socket/connect DNS call, is a fail (`integrity` gate).

## Acceptance oracle

The judge never trusts the artifact to report about itself. Four
independent oracles:

1. **Two parsers of the same robot** — MuJoCo compiles `rp1_flat.xml`;
   the judge independently parses `rp1_24dof.urdf` with the Python
   standard library and compares total mass, per-link masses, joint
   names and joint ranges. MuJoCo and a hand-rolled URDF walker agree,
   or they do not.
2. **Physics** — the simulator itself: a controller that does not balance
   falls, and the fall is measured from `mjData`, not from anything the
   artifact reports.
3. **Statics** — with the artefact removed (zero-torque oracle) the
   vertical contact impulse on the feet at the queried static instant
   must equal total weight `m·g` within 2 %. This pins down mass,
   gravity and contact normals without trusting the artifact.
4. **Checksums of `judge/`** before and after the run, plus the
   file-access audit, so the artifact cannot rewrite its own exam.

## Gates

The judge prints exactly one verdict JSON object. All gates must pass for
exit code 0. `P` = measured value, `R` = rule.

### Gate list

| # | gate | what is measured | pass rule |
|---|---|---|---|
| 1 | `model_loads` | `mujoco.MjModel.from_xml_path(rp1_flat.xml)` | compiles without exception; `nq=31`, `nv=30`, `nu=24` |
| 2 | `mass_match` | per-link masses, MJCF vs URDF | every inertial link within 1 % of URDF mass; total within 1 % |
| 3 | `joint_match` | joint names + ranges, MJCF vs URDF | same 24 hinge names, same order; every range endpoint within 1e-4 rad |
| 4 | `effort_match` | actuator `ctrlrange` vs URDF `effort` | every actuator's `max|ctrlrange|` within 1 % of the URDF `effort` |
| 5 | `gravity_statics` | zero-torque run, vertical contact force vs `m·g` | at least one contact instant with feet loaded; `|ΣFz − m·g| / (m·g) <= 0.02` at that instant |
| 6 | `stand` | pelvis height, torso quaternion, contacts over t ∈ [0, 10) s | pelvis z >= 0.9 × its t=0 value for all t; |roll|,|pitch| ≤ 10° for all t; no non-foot body touches the floor |
| 7 | `push` | same signals over t ∈ [5.0, 10) s, push applied t ∈ [5.0, 5.2) s | `stand` rules hold for all t in the window *and* |roll|,|pitch| ≤ 5° by t = 7.0 s and held to t = 10 s |
| 8 | `limits` | `qpos`, `qvel`, `ctrl`, `actuator_force` over the run | no hinge beyond its [range] by more than 1e-3 rad; no |ctrl| beyond `ctrlrange`; no |applied actuator force| beyond `ctrlrange` by more than 1 N·m |
| 9 | `effort` | reported, not gated | energy ´∫|τ·q̇|dt`, peak |τ|, RMS |τ| per joint; always `verdict:"info"` |
| 10 | `integrity` | sha256 of every file under `judge/`, audit hook log | identical before vs after; zero forbidden `open`/`connect` events from the artifact |

Numeric constants. `grade.sh` takes only `--seed` and `--json` on the
command line; the values below live in `judge/params.json` (and are copied
into the verdict):

| constant | value | meaning |
|---|---|---|
| `dt_ctrl` | 0.005 s | control period (matches model timestep) |
| `t_total` | 10.0 s | full episode |
| `push_t0` | 5.0 s | push start |
| `push_t1` | 5.2 s | push end |
| `push_force` | 30 N | lateral (world +Y) force on `waist_yaw_link` |
| `push_recover_s` | 2.0 s | recovery window after `push_t0` |
| `stand_tilt_rad` | 0.1745 rad (10°) | stand-gate tilt limit |
| `push_tilt_rad` | 0.0873 rad (5°) | push-gate recovery tilt limit |
| `pelvis_frac` | 0.9 | pelvis height floor as a fraction of its t=0 value |
| `mass_tol` | 0.01 | per-link and total mass tolerance |
| `joint_tol` | 1e-4 rad | joint range endpoint tolerance |
| `gravity_tol` | 0.02 | statics tolerance |
| `seed` | CLI only, default 20261014 | sensor-noise / contact seed (no RNG otherwise) |

### Judged trajectory

`grade.sh` copies `controller.py` into a scratch dir, imports it under an
audit hook, and runs `run_one(controller_cls)`:

```
model = mujoco.MjModel.from_xml_path(<clone>/mjcf/rp1_flat.xml)
data  = mujoco.MjData(model)
ctrl  = Controller(model, data, params)
for k in range(int(t_total / dt_ctrl)):
    t = data.time
    if push_t0 <= t < push_t1:
        data.xfrc_applied[body_waist_yaw, 1] = push_force   # world +Y
    else:
        data.xfrc_applied[body_waist_yaw, :] = 0
    data.ctrl[:] = ctrl.compute_ctrl(t)
    mujoco.mj_step(model, data)
    <record pelvis z, base quat, contacts, qpos, qvel, ctrl, actuator_force>
```

The zero-torque oracle (`gravity_statics`) is the same run with
`compute_ctrl` replaced by `lambda t: zeros(24)`, stopped at the first
instant where both feet have contact force, and the vertical total
compared with `m·g`.

## Known-bad artifact family

`judge/mutants.py` generates ≥ 5 single-edit mutants of
`examples/good/controller.py` by exact line edit:

| mutant | edit | gate that must fail |
|---|---|---|
| `zero_gains` | `KP = KP * 0.0` after the gain table | `stand` |
| `sign_flip_knee` | `kp["left_knee_joint"] = -kp["left_knee_joint"]` | `stand` |
| `gains_100x` | `KP = KP * 100.0` | `limits` |
| `wrong_joint_order` | `order = order[::-1]` in the index map | `stand` |
| `no_balance` | balance term line deleted | `push` |
| `clamp_1pct` | `u = np.clip(u, -0.01*lim, 0.01*lim)` | `stand` |

Every mutant must fail at least one gate. `judge/selftest.sh` reports the
kill rate split into physics kills (a `stand`/`push`/`limits` gate fired)
and oracle kills (`gravity_statics`, `model_*`, integrity), and requires
the physics kill rate to be at least 90 %.

## What this demo does not prove

- Nothing about the real RP1: no latency, no backlash, no stiction, no
  IMU noise model against the robot's datasheet — MuJoCo is not the
  robot.
- `condim=4` torsional friction and capsule feet are a choice of the
  upstream model, not a statement about real soles.
- The push is a perfectly horizontal, perfectly lateral, perfectly known
  force at a known body. A pass does not certify the same controller
  against pushes it has not seen.
- One initial pose, one push. The gates are a spec, not a coverage claim.
