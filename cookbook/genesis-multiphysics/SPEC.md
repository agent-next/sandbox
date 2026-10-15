# SPEC: Genesis multiphysics — granular column collapse over a rigid peg

## Goal

Demonstrate a popular open-source multiphysics simulator —
[Genesis](https://github.com/Genesis-Embodied-AI/genesis-world),
`genesis-world` 1.4.3 on PyPI (Apache-2.0) — solving a non-robot
multiphysics scene **entirely on the CPU backend** (`gs.init(backend=gs.cpu)`)
inside a disposable agent-next sandbox, graded by a judge that reads only
the simulator state (never pixels).

The scene is a classical **granular column collapse**:

- a rectangular column of ~20k MPM elastic particles (sand-like material)
  is released at height, falls under gravity, strikes a rigid box obstacle
  standing on the floor, spreads, and settles into a heap;
- the free-fall phase (centre of mass ≈ g·t²/2), mass conservation,
  non-penetration, and the final heap geometry are all checked numerically.

The whole grade (simulation + every gate) must finish in under **10 minutes
wall time on 2 vCPU / 4 GB RAM**, single-threaded-deterministic with a fixed
seed.

## Non-goals

- GPU backends (CUDA/Vulkan), robotics (articulated bodies, grippers, IK).
- Rendering as a gate: the judge never reads pixels. (Real frames are
  rendered separately for the media step.)
- SPH fluids, cloth, coupling between solvers — one material (MPM elastic)
  plus one rigid body is the declared scope.
- Genesis versions other than the pinned one; any physics after settle time.

## Artifact

A single Python file, the **scenario**, containing a *scene spec* the judge
executes itself. The artifact declares parameters; the judge builds the
scene, runs it, and measures — so a scenario cannot pass by shipping cached
positions.

```
examples/good/scenario.py     # known-good scenario (constants only, no solver control flow beyond the spec API)
```

A scenario file **must** define exactly one module-level dict named
`SCENARIO` with these keys (all required, all plain numbers/strings):

| key | type | meaning |
|---|---|---|
| `gravity` | float | gravitational acceleration, m/s², downward is negative; expected −9.81 |
| `dt` | float | substep time step, s; must satisfy 5e-5 ≤ dt ≤ 5e-4 |
| `steps` | int | total substeps to simulate; 2000 ≤ steps ≤ 30000 |
| `column_size` | [sx, sy, sz] | column side lengths, m; 0.05 ≤ each ≤ 0.5 |
| `column_pos` | [x, y, z] | centre of column bottom face, m; drops onto the obstacle |
| `particle_size` | float | MPM particle pitch, m; 0.005 ≤ size ≤ 0.03 |
| `E` | float | Young's modulus, Pa; 1e4 ≤ E ≤ 1e7 |
| `nu` | float | Poisson ratio; 0.0 ≤ nu ≤ 0.45 |
| `rho` | float | density, kg/m³; 500 ≤ rho ≤ 3000 |
| `obstacle_size` | [sx, sy, sz] | rigid box obstacle on the floor, m |
| `obstacle_pos` | [x, y, z] | obstacle centre bottom face, m |
| `friction` | float | Coulomb friction coefficient, 0.1 ≤ f ≤ 1.5 |
| `seed` | int | seed passed to the simulator |

The judge (`judge/grade.sh <scenario.py> [--seed N] [--json out.json]`)
imports the artifact read-only in a sandboxed copy, builds the scene with
Genesis, runs it, applies the gates below, and prints one JSON verdict.
`judge/` is sha256-checksummed before and after every grade.

## Gates (numeric pass rules)

Gate numbering is stable; the JSON verdict lists each with its measured
numbers. All gates must pass.

### Gate 1 — completes within budget, no NaN
- The simulation runs all `steps` substeps without raising, in ≤ 600 s
  wall time.
- After the run, every particle position and velocity is finite
  (`numpy.isfinite`). Max |v| over all particles ≤ 50 m/s (a blow-up
  trips this even before NaN appears).

### Gate 2 — mass conservation
- Particle count at the end equals the count right after scene build
  (exact integer equality; neither deletion nor spurious splitting).
- Total MPM particle mass equals its initial value to relative error < 1e-6.

### Gate 3 — free-fall phase matches ballistics
- Sample the column centre of mass `z_com(t)` over the interval
  `[t1, t2] = [0.05·t_fall, 0.5·t_fall]`, where `t_fall =
  sqrt(2·(z_bottom0 − z_obstacle_top)/|g|)` is the analytic time for the
  column bottom to reach the obstacle top, computed from the *spec*
  geometry.
- Fit `z_com(t)` to `z0 + v0·t + ½·a·t²` (least squares over ≥ 20 samples);
  require `|(a − g)/g| ≤ 0.02` and fitted `v0 ≤ 0.05 m/s`.
- Rationale: before contact, MPM stress is ~zero, so the cloud is in free
  fall; the accelerator must equal gravity within 2 %.

### Gate 4 — no penetration
- At every sampled frame (every 20 substeps), no particle's z is below
  `floor_z − tol` and the vector distance from any particle to the
  obstacle's axis-aligned box interior stays ≥ −tol, with
  `tol = 1.5·particle_size` (MPM kernel support is ≈ 1 particle pitch).

### Gate 5 — material behaviour: heap spreads within a band
- After settle (the final frame), compute the basal spread radius
  `r_95`: the smallest radius about the column axis containing 95 % of
  particle mass, in the horizontal plane.
- Require `r_95 ∈ [1.4·s, 6.0·s]` where `s = max(sx, sy)` is the column
  footprint half-width... (see Acceptance oracle; band justified there:
  inside 1.4·s the "material" never flowed; beyond 6·s it behaved like a
  liquid.) Also require mean final speed < 0.05 m/s (settled, not
  jittering) and the final CoM height below 40 % of the initial
  column-top height (it actually collapsed).

### Gate 6 — deterministic at a fixed seed
- The judge runs the scenario **twice** in fresh processes with the same
  `--seed` and compares all sampled particle positions: max absolute
  deviation must be exactly 0.0 (bit-identical) on the CPU backend with
  `n_threads=1`. This gate double-runs the scenario, so the wall budget
  in gate 1 applies per run.

## Known-bad mutants (`judge/mutants.py`, ≥ 5)

Single-edit mutants of `examples/good/scenario.py`, regenerated by the
script into `examples/bad/`:

1. `gravity_flipped` — gravity points up (+9.81): fails gates 3/5.
2. `dt_blowup` — dt = 2e-3 (above the stable range): fails gate 1/3.
3. `no_obstacle` — obstacle shrunk to zero volume: column falls through
   where the peg was; fails gate 4/5 shape band.
4. `low_gravity_moon` — gravity −1.62 (wrong spec): fails gate 3 (a = g
   check compares against the *expected* −9.81).
5. `too_few_steps` — steps cut to 800: nothing settles; fails gate 5
   (mean speed / not collapsed).
6. `wrong_material` — E = 1e8 with nu = 0.49 (nearly incompressible
   rubber): fails gate 5 spread band.

The self-test must kill ≥ 90 % of these.

## Acceptance oracle

- **Gate 3** oracle is the closed-form ballistic solution z(t) = z0 +
  ½·g·t² — independent of the simulator.
- **Gate 4** oracle is the analytic geometry of the floor plane and the
  obstacle AABB.
- **Gate 5** oracle: for granular collapse, published MPM/elastic-collapse
  benchmarks (e.g. the granular-column literature following
  Lajeunesse et al. 2005, *Phys. Fluids* 17, 103302) show final runout
  radius between ≈ 1.5× and ≈ 4× the column footprint for friction angles
  of 20–40°; the band [1.4, 6.0]·s brackets that behaviour with margin
  and excludes both "did not flow" (< 1.4·s) and "behaved like liquid"
  (> 6·s). The settle-speed and collapse-height checks are threshold
  physics: a heap that never stopped moving or never fell is not a
  collapsed column.
- **Gate 6**: determinism is a property of the simulator on CPU with one
  thread; bit-identity is the oracle.

Nothing passes because "Genesis ran" — every gate compares a number
against an independent target.
