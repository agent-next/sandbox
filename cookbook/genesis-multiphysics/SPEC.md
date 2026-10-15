# SPEC: Genesis multiphysics — granular column collapse over a rigid peg

## Goal

Demonstrate a popular open-source multiphysics simulator —
[Genesis](https://github.com/Genesis-Embodied-AI/genesis-world),
`genesis-world` 1.4.3 on PyPI (Apache-2.0) — solving a non-robot
multiphysics scene **entirely on the CPU backend** (`gs.init(backend=gs.cpu)`)
inside a disposable agent-next sandbox, graded by a judge that reads only
the simulator state (never pixels).

The scene is a classical **granular column collapse**:

- a rectangular column of MPM elasto-plastic particles (a von Mises sand
  model) is created at rest above a rigid box standing on the floor, in
  **zero gravity; gravity is switched on at t = 0**. The column
  free-falls — pure ballistics the judge can compare against g·t²/2
  exactly — strikes the obstacle, collapses around it and settles into a
  heap.
- free-fall ballistics, mass conservation, non-penetration, final heap
  geometry and bit-exact determinism are all checked numerically.

The whole grade (two simulation runs + every gate) must finish in under
**10 minutes wall time on 2 vCPU / 4 GB RAM**.

## Non-goals

- GPU backends (CUDA/Vulkan), robotics (articulated bodies, grippers, IK).
- Rendering as a gate: the judge never reads pixels. (Real frames are
  rendered separately for the media step.)
- SPH fluids, cloth, or coupling between more than two solvers — one MPM
  material plus rigid bodies (floor plane + one box) is the declared scope.
- Genesis versions other than the pinned one; any physics after settle.

## Artifact

A single Python file, the **scenario**, containing a *scene spec* the judge
executes itself. The artifact declares constants; the judge builds the
scene, runs it, and measures — so a scenario cannot pass by shipping cached
positions.

```
examples/good/scenario.py     # known-good scenario (one SCENARIO dict)
```

A scenario file **must** define exactly one module-level dict named
`SCENARIO` with these keys (all required, all plain numbers/lists):

| key | type | meaning |
|---|---|---|
| `gravity` | float | gravitational acceleration in m/s² (down is negative), switched on at t = 0; the reference uses −9.81 |
| `dt` | float | time advance per `scene.step()` frame, s; judged range 5e-4 ≤ dt ≤ 2e-3 with dt/substeps ≤ 5e-4 (MPM stability) |
| `substeps` | int | subdivisions per frame; 1 ≤ substeps ≤ 10 |
| `steps` | int | frames simulated; 600 ≤ steps ≤ 4000, total time steps·dt ≤ 4 s |
| `seed` | int | seed passed to `gs.init` (the judge's `--seed` overrides it) |
| `particle_size` | float | MPM particle pitch, m; 0.008 ≤ size ≤ 0.03 |
| `grid_density` | int | MPM grid cells per metre; 32 ≤ g ≤ 64 |
| `domain_lower`, `domain_upper` | [x,y,z] | MPM domain, m; must contain the column, the obstacle and ≥ 3·column_height of headroom |
| `column_size` | [sx, sy, sz] | column side lengths, m; 0.06 ≤ each ≤ 0.5 |
| `column_pos` | [x, y, z] | centre of the column bottom face, m; must clear the obstacle top |
| `E` | float | Young's modulus, Pa; 1e4 ≤ E ≤ 1e7 |
| `nu` | float | Poisson ratio; 0.0 ≤ nu ≤ 0.45 |
| `rho` | float | density, kg/m³; 500 ≤ rho ≤ 3000 |
| `yield_stress` | float | von Mises yield stress, Pa; 100 ≤ σy ≤ 1e5 |
| `obstacle_size` | [sx, sy, sz] | rigid box standing on the floor, m |
| `obstacle_pos` | [x, y, z] | obstacle centre, m |
| `friction` | float | Coulomb friction of the rigid bodies; 0.1 ≤ f ≤ 1.5 |

The judge (`judge/grade.sh <scenario.py> [--seed N] [--json out.json]`)
imports the artifact read-only into its own runner script (the artifact
never executes sim code itself), builds the scene with Genesis, runs it
twice, applies the gates below, and prints one JSON verdict. `judge/` is
sha256-checksummed before and after every grade.

## Gates (numeric pass rules)

Time convention: frame `i` of the run corresponds to simulated time
`t = i · dt` (gravity is switched on before the first frame). All gates
must pass.

### Gate 1 — completes within budget, no NaN
- Each of the two runs finishes all `steps` frames in ≤ 480 s wall time.
- Final particle positions and velocities are all finite
  (`numpy.isfinite`); final max |v| ≤ 50 m/s (a blow-up trips this even
  before NaN appears).

### Gate 2 — mass conservation
- Particle count at the end equals the count right after build (exact
  integer equality — no deleted or split particles).
- The scenario's domain bounds contain every particle at every sampled
  frame (a particle that leaves the domain is failing mass conservation
  in spirit and trips this gate).

### Gate 3 — free-fall phase matches ballistics
- The judge samples the column centre of mass `z_com(t)` every frame over
  `[t1, t2] = [2·dt, 0.5·t_fall]`, where `t_fall =
  sqrt(2·(z_bottom0 − z_obstacle_top)/|gravity|)` is the analytic time
  for the column bottom face to reach the obstacle top, computed from the
  spec geometry.
- Least-squares quadratic fit `z_com(t) ≈ z0 + v0·t + ½·a·t²` over that
  interval (≥ 20 samples); require `|(a − g)/g| ≤ 0.02` and
  `|v0| ≤ 0.05 m/s`.
- The window ends at 0.5·t_fall so no particle is anywhere near contact
  during the fit; MPM internal stress at rest in zero-g is exactly zero
  at t=0, so the cloud is in pure free fall and its CoM must follow
  ballistics to integrator accuracy.

### Gate 4 — no penetration
- At every sampled frame, with `tol = max(1.5·particle_size,
  1.5·grid_cell)` where `grid_cell = 1/grid_density` (MPM rigid contact is
  resolved at grid nodes, so a particle *centre* may legitimately sit
  within about one grid cell of a surface; this tolerance accepts
  numerical contact, not interpenetration — a real pass-through is many
  cells deep):
  - no particle z below `floor_z − tol` (floor_z = 0);
  - no particle strictly inside the obstacle AABB by more than tol, i.e.
    for `q = centre − pos`, `pen = min(|q| − size/2)` component-wise max
    must stay ≤ tol... precisely: `max_i min_axes(d)` ≤ 0 + tol where `d`
    is the standard signed distance to the box (negative inside).

### Gate 5 — material behaviour: heap spreads within a band
- Measured on the final frame of run 1:
  - the basal spread radius `r95` about the column axis (smallest radius
    containing 95 % of particles, in the horizontal plane) satisfies
    `r95 ∈ [1.4·s, 6.0·s]` with `s = max(sx, sy)/2` the column footprint
    half-width (band justified under Acceptance oracle);
  - mean final particle speed < 0.05 m/s (settled, not jittering);
  - final CoM height < 0.6·(initial CoM height) (it actually collapsed).

### Gate 6 — deterministic at a fixed seed
- The judge runs the scenario twice in fresh processes with the same seed
  and compares all sampled particle positions: max absolute deviation
  must be exactly 0.0 (bit-identical) on the CPU backend with
  `n_threads=1`.

## Known-bad mutants (`judge/mutants.py`)

Single-edit mutants of `examples/good/scenario.py`, regenerated into
`examples/bad/` by the script:

1. `gravity_flipped` — gravity = +9.81 (points up): fails gate 3.
2. `gravity_off` — gravity = 0.0 (typo'd constant): fails gates 3/5.
3. `dt_blowup` — `substeps = 1` with `dt = 2e-3`: substep dt of 2e-3 is
   above the MPM stability limit for this grid: fails gate 1 or 3.
4. `no_obstacle` — obstacle shrunk to 1e-3 m cube at the floor: column
   lands flat instead of wrapping the peg: fails gate 5's spread band
   (spread now matches an unimpeded deposit with a different r95) — and
   the guard "obstacle must affect the flow" (gate 4 shape checks) may
   catch it too.
5. `too_few_steps` — steps = 350: the column is still mid-collapse at the
   end: fails gate 5 (settle speed / collapse height).
6. `wrong_material` — E = 1e8, yield_stress = 1e6: effectively rigid
   chunks, the column bounces without flowing: fails gate 5's r95 band
   and collapse height.

The self-test must kill ≥ 90 % of these (each mutant must fail ≥ 1 gate).

## Acceptance oracle

- **Gate 3** oracle is the closed-form ballistic solution z(t) = z0 +
  ½·g·t² with g taken from the scenario (so gate 3 also pins the gravity
  *value*: a wrong g fails the (a − g)/g check against the fitted a… no —
  the fit is compared to the spec's own `gravity`, and the *reference
  physics* g = −9.81 is enforced by the band in gates 3+5 together: a
  flipped or zero gravity cannot produce the required settled heap below
  the collapse-height threshold).
- **Gate 4** oracle is the analytic geometry of the floor plane and the
  obstacle AABB.
- **Gate 5** oracle: granular-column collapse benchmarks (Lajeunesse et
  al. 2005, *Phys. Fluids* 17, 103302; and standard MPM validation cases
  that ship with several codes) place the final runout radius at ≈ 1.5×–4×
  the column half-width for frictional granular materials; the band
  `[1.4, 6.0]·s` brackets that with margin while excluding both "never
  flowed" (< 1.4·s) and "behaved like a liquid" (> 6·s). The settle-speed
  and collapse-height thresholds are threshold physics: a pile still
  moving or a column that never fell is not a collapsed granular heap.
- **Gate 6** oracle: determinism is a binary property of the simulator on
  the CPU backend with one thread; bit-identity is the check.

Nothing passes because "Genesis ran" — every gate compares a number
against an independent target.
