# SPEC — physx-drop-test

## Goal

Show an agent solving a real engineering problem in a disposable agent-next
sandbox: author a USD rigid-body scene (NVIDIA PhysX via the `ovphysx`
headless CPU wheel) against a written specification, and have a judge it
cannot fool decide — from an independent analytic oracle — whether the
scene obeys basic Newtonian mechanics: free fall under gravity, a bounce with
the authored restitution, and settling to the geometrically correct resting
height.

## Why a sandbox

The toolchain is a 139 MB manylinux wheel plus dependencies (~500 MB
installed) that no one wants on a workstation; a disposable sandbox with
2 vCPUs runs the whole simulation on CPU, headless, in seconds.

## Non-goals

- Rendering inside the judge (the pinned `ovphysx` wheel is simulation-only:
  it exposes no renderer; `media/` renders the judged trajectory
  headlessly with matplotlib — see `media/STORYBOARD.md`).
- GPU simulation, articulations, deformables, CCD.
- Contact-force or impulse measurement (positions/velocities only).

## The artifact

The agent authors **one file**: `scene.usda`, a USD ASCII stage containing:

1. Stage metadata: `metersPerUnit = 1`, `upAxis = "Y"`,
   `kilogramsPerUnit = 1`, a default prim.
2. A `PhysicsScene` prim with gravity direction `(0, -1, 0)` and magnitude
   `9.81` (m/s²).
3. A static ground: a `Cube`-based collider (or `Plane`) whose top surface is
   at **z = 0** with `PhysicsCollisionAPI` and **no** rigid-body API.
4. **Box**: dynamic rigid body, `PhysicsRigidBodyAPI` +
   `PhysicsMassAPI` (`physics:mass = 4.0` kg) + child `Cube` collider with
   `PhysicsCollisionAPI`, half-extent **0.10 m** (i.e. a 0.2 m cube), center
   dropped from height **h_box = 0.80 m**, spawned at rest, with a
   physics material of static friction **0.60**, dynamic friction **0.40**,
   restitution **0.50** bound to the collider.
5. **Ball**: dynamic rigid body, mass **1.0** kg, child `Sphere` collider of
   radius **0.10 m**, dropped from height **h_ball = 1.20 m**, at rest, same
   friction/restitution material (or its own with the same values).
6. Initial velocities zero; no kinematic flags.

The two bodies must not collide with each other during the test horizon
(lateral separation ≥ 0.6 m is enough and required).

### The dynamics contract (G7)

The artifact must be **one self-contained ASCII file that solves the task by
dynamics alone**: no `physics:kinematicEnabled`, no joint or other
constraint prims, no composition arcs that pull in other files
(`references` / `payload` / `subLayers` / `inherits` / `variants`), no
non-zero authored velocities, no drives. The judge re-derives these rules
from the artifact's own text (G7), so a scene that animates or scaffolds
its way to a passing trajectory — or that simulates perfectly while
secretly referencing outside content — is rejected by name even when every
physics gate passes.

## The judge oracle

The judge (`judge/grade.sh`) copies the artifact to a scratch dir, simulates
it headless on CPU with pinned `ovphysx` (step h = 1/240 s, 2400 steps = 10 s
simulated), reads back per-step positions/velocities of both bodies, and
compares against **closed-form mechanics** — no reference simulation, no
"the tool ran":

- **Free fall (both bodies):** before first ground contact, every sampled
  y(t) must satisfy `|y_sim(t) − (y0 − g t²/2)| ≤ 1 %` of the analytic value
  (plus a 0.5 mm absolute floor), with g = 9.81.
- **First contact time (both):** the first frame at which y begins to depart
  downward of the free-fall curve / the first detected upward velocity change
  must lie within **1 frame** (1/240 s) of the analytic contact time
  `t_c = sqrt(2 (y0 − y_rest) / g)` where y_rest is the resting center height.
- **Resting height (both):** after 10 s, the body center height must be within
  **1 mm** of the geometric resting height (half-extent 0.10 m for the box,
  radius 0.10 m for the ball).
- **Bounce apex (ball only):** the ball's first post-impact maximum center
  height must be within **10 %** of the analytic apex
  `y_rest + e² (h_ball − y_rest)` with e = 0.50, i.e. apex ≈ 0.10 + 0.25 ×
  1.10 = 0.375 m.
- **Energy monotonicity (both):** `E(t) = m g y(t) + ½ m v(t)²` sampled every
  frame must never increase by more than **0.5 %** of the initial potential
  energy between consecutive local segments (numerical-solver tolerance);
  overall E must be non-increasing to within 0.5 % of E₀ across the run.
- **Dynamics contract (G7):** the artifact itself must obey the contract
  above. The judge re-reads the same scratch copy of the scene the
  simulator stepped and rejects kinematic flags, constraint prims,
  composition arcs, authored velocities and drives by name.

Every judged quantity is re-derived by the judge from the simulator's own
output files (traj.npz/meta.json) plus that scratch copy — nothing the
artifact can influence. The artifact also never runs in the judge's
process: the simulator is a separate `python -I` invocation over a scratch
copy, and the `judge/` directory is sha256-checksummed before and after
every grade so a scene that tried to modify the judge fails loudly.

Numeric pass rules: every gate is a number or fails; `grade.sh` prints one
JSON verdict and exits 0 only if all gates pass. Deterministic: fixed step
count, CPU, single-threaded PhysX (`num_threads = 1`), no randomness (a
`--seed` flag is accepted and recorded but nothing samples it).

## Gates summary (numeric)

| # | Gate | Rule | Body |
|---|------|------|------|
| G1 | loads | both dynamic bodies sampled every step, mass read back within 0.1 % of the authored value | both |
| G2 | free fall | ≤ 1 % rel (+0.5 mm) vs z0 − g t²/2 on all pre-contact samples | both |
| G3 | contact time | within 1 frame (4.17 ms) of sqrt(2 Δh/g) | both |
| G4 | resting height | within 1 mm of 0.10 m after settle | both |
| G5 | bounce apex | within 10 % of 0.375 m | ball |
| G6 | energy | no sample-to-sample increase > 0.5 % of E₀; total ≤ E₀ + 0.5 % E₀ | both |
| G7 | contract | artifact text obeys the dynamics contract (no kinematic flags, joints, composition arcs, authored velocities/drives) | scene |

## Known-bad mutants (self-test)

Single-edit mutants of the good scene. Each must be **killed by a judge
gate** — a mutant that crashes the simulator before the gates run is a
broken mutant and fails the self-test. The kill rate counts gate-kills
only and must be ≥ 90 % (10/10 here → 100 %).

1. `gravity-flip` — gravity direction `(0, 1, 0)` → fails G2 (rises) / G3.
2. `mass-zero` — `physics:mass = 0` → PhysX substitutes a default-density
   mass instead of failing to load; fails G1 (mass read back ≠ authored 4.0).
3. `no-rigidbody` — `PhysicsRigidBodyAPI` removed from Box's apiSchemas →
   collider never simulated → G1 (body not sampled).
4. `no-ground-collision` — remove `PhysicsCollisionAPI` from ground → falls
   through, G3/G4.
5. `spawn-inside-ground` — box spawn y = 0.05 < 0.10 → G3/G4.
6. `restitution-over-unity` — e = 1.20 → energy gain, G5/G6.
7. `cm-units` — `metersPerUnit = 0.01` (cm) with same numbers → G2/G4.
8. `kinematic-cheat` — ball switched to `kinematicEnabled` (animation
   instead of dynamics) → G7 names it; the physics gates also fail.
9. `joint-scaffold` — box welded to the ground with a `PhysicsFixedJoint`:
   every physics gate still passes; only G7 kills it.
10. `hidden-reference` — scene prepends
    `references = @./not-in-this-repo.usda@`: physics is unchanged and
    passes; only G7 (self-contained artifact rule) kills it.

## Acceptance oracle

Analytic free-fall/bounce mechanics, independent of any physics engine:

```
y_pre(t)  = y0 − ½ g t²          (free fall)
t_contact = sqrt(2 (y0 − y_rest) / g)
apex      = y_rest + e² (y0 − y_rest)
E(t)      = m g y(t) + ½ m v(t)²   (monotone non-increasing with e ≤ 1)
```

## Toolchain (pinned, sha256-checked)

- `ovphysx` 0.6.3 (PyPI wheel, manylinux x86_64, released 2026-09-16) —
  NVIDIA Omniverse PhysX headless CPU SDK;
  https://github.com/NVIDIA-Omniverse/PhysX.  The newest wheel
  (0.6.4.72118723, 2026-10-09) is too new to pin: nothing published in the
  two weeks before 2026-10-15 may be used.
- `newton-usd-schemas` 0.5.0 (PyPI) — Newton USD schema registration.
- Exact pins of the ovphysx dependency wheel and transitives (`ovstage`
  0.2.0.377349, `warp-lang` 1.17.0, `numpy` 2.2.6, `packaging` 23.2), all
  sha256-recorded in `judge/requirements.txt`; `judge/VERSIONS.txt`
  records what `setup.sh` actually installed.
- Python 3.10+ from the sandbox image; pinned exact versions, nothing from
  "latest", nothing published in the last two weeks.
