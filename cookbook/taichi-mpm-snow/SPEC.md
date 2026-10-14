# SPEC: MLS-MPM snow with Taichi (CPU backend)

## Goal

Demonstrate an agent-next sandbox running a real, widely used open-source
simulation stack — [Taichi](https://github.com/taichi-dev/taichi)
(MIT license, v1.7.4, pinned exactly and sha256-checked) — to solve a
canonical material point method (MPM) problem: an elastoplastic
**snowball** (Stomakhin-style hardening) dropped onto the ground,
splashing against a second, weaker material for visual contrast.

The agent's artifact is a pair of files — `sim.py` + `params.json` —
that run an MLS-MPM simulation on Taichi's **CPU backend**
(`ti.init(arch=ti.cpu)`), deterministic for a fixed `--seed`, writing a
metrics file and stacked RGB frames headless (Taichi GUI with
`show_gui=False` or numpy -> PNG).

A judge the agent cannot fool decides whether the result is real,
conservative MPM — every gate compares numbers the judge extracts from
the artifact's own log against physical invariants, not against the
agent's claims.

## Non-goals

- 3D simulations (the judge runs 2D; a 3D artifact is out of scope).
- GPU backends (`ti.cuda`, `ti.vulkan`, …); the whole demo is CPU-only.
- Rendering beyond stacked RGB particle plots (the video is a separate
  media task; this demo only saves frames).
- Coupling to a mesh-based solver; solids materials other than the two
  in the artifact's `materials` table.
- Any taichi version other than the pinned 1.7.4 wheel.

## Artifact

One directory holding **input files only**:

```
<artifact>/
├── sim.py        # the simulation entry point
└── params.json   # numeric parameters (see schema below)
```

`sim.py` must be runnable as

```
python3 sim.py --params params.json --out <run_dir> --seed <int> \
    --steps <int>
```

and must write into `<run_dir>`:

- `metrics.jsonl` — one JSON object per step (see Metrics);
- `frames/frame_0000.png`, `frame_0001.png`, … at the configured
  `frame_stride` (stacked RGB particle plots).

`params.json` follows this schema (all numbers MKS, seconds, metres):

```jsonc
{
  "dim": 2,
  "n_grid": 64,             // grid resolution per side
  "dx": 0.015625,           // 1 / n_grid
  "dt": 2e-4,               // seconds per step
  "steps": 5000,            // total steps
  "frame_stride": 40,       // one PNG every this many steps
  "seed": 0,                // default seed; --seed overrides
  "gravity": -9.81,
  "domain": [1.0, 1.0],     // lower-left corner at (0,0)
  "bound": 3,               // boundary layer width in grid cells
  "materials": [
    { "name": "snow",  "type": "snow",  "E": 1.4e4, "nu": 0.2,
      "rho": 400, "hardening": 10.0, "jp_min": 0.6, "jp_max": 1.6,
      "color": "#ffffff",
      "box": { "lo": [0.40, 0.60], "hi": [0.60, 0.75] },
      "ppc": 4 },
    { "name": "jelly", "type": "fluid", "E": 5.0e3, "nu": 0.4,
      "rho": 1000, "hardening": 0.0, "jp_min": 0.6, "jp_max": 1.6,
      "color": "#4fb3ff",
      "box": { "lo": [0.45, 0.45], "hi": [0.55, 0.60] },
      "ppc": 4 }
  ]
}
```

`type` is one of `snow` (fixed-corotated + Stomakhin hardening),
`fluid` (volume penalty only, no deviatoric stress) or `jelly`
(fixed-corotated, no hardening, i.e. purely elastic). The judge reads
`params.json` to derive expected values; the gates are numeric on the
artifact's own `metrics.jsonl`.

## Gates (numeric pass rules)

All gates are computed from the artifact's own `metrics.jsonl`. Every
per-step row must carry: `step`, `time`, `mass_particles`,
`mass_grid_after_p2g`, `px`, `py`, `com_x`, `com_y`, `vel_com_x`,
`vel_com_y`, `x_min`, `y_min`, `x_max`, `y_max`, `jp_min`, `jp_max`,
`jp_frac_lt_09`, `jp_frac_gt_11`, and `snow_height` (the y-extent of the snow-material
particles).  A row missing a field, or a step
whose values are not finite, fails Gate 1.

### Gate 1 — completion and sanity
- `sim.py` exits 0 within the wall budget (`SPEC_WALL_S`, default
  1800 s).
- `metrics.jsonl` has exactly `steps + 1` rows (step 0 … steps).
- Every numeric field of every row is finite (no NaN or Inf).

### Gate 2 — mass conservation and grid-vs-particle agreement
- `|mass_particles[t] - mass_particles[0]| / mass_particles[0] <= 1e-12`
  for every step t (particles do not gain or lose mass).
- `|mass_grid_after_p2g[t] - mass_particles[t]| / mass_particles[0] <=
  1e-6` for every step t (P2G conserves mass to round-off).

### Gate 3 — free-fall before first contact
- From `metrics.jsonl`, find `t_contact` = the first step whose
  `y_min <= ymin_contact` with `ymin_contact = bound * dx + 2*dx` (the
  boundary layer plus one cell). All steps before `t_contact` must have
  `|vel_com_y[t] - gravity * time[t]| / (|gravity| * time[t]) <= 0.01`
  for every `t` with `time[t] >= 20 * dt` (skip the first few rows where
  round-off dominates), and the same step's `vel_com_x` must satisfy
  `|vel_com_x[t]| <= 0.02`.

### Gate 4 — boundary condition
- For every step t: `x_min[t] >= dx` and `y_min[t] >= dx` and
  `x_max[t] <= domain[0] - dx` and `y_max[t] <= domain[1] - dx`.
  (Grid velocities are zeroed in the `bound`-cell-wide boundary layer;
  with quadratic B-spline weights a particle can penetrate at most
  into that layer and can never reach the outermost cell; one cell is
  the physical invariant.)

### Gate 5 — plastic deformation on impact
- Final-frame bounding-box height of the snow material only:
  `snow_height[t_final] / snow_height[0] <= 0.93` (the good artifact
  settles to ~0.89).
- Plasticity engaged: `jp_frac_lt_09[t_final] + jp_frac_gt_11[t_final]
  >= 0.05` (at least 5 % of snow particles deviate from Jp = 1 by 10 %
  or more; the good artifact settles at ~0.62).

### Gate 6 — horizontal momentum (symmetric drop)
- `|px[t]| / mass_particles[0] <= 0.02` for every step t.

### Gate 7 — judge integrity
- `sha256` of every file in `judge/` is identical before and after
  grading (the artifact cannot modify the judge).

## Acceptance oracle

Every gate compares a measured number from the artifact's own log
against a physical invariant of MPM:

- Gate 2 oracle: mass conservation of MPM (P2G is a partition-of-unity
  scattering; grid mass after P2G must equal particle mass to
  round-off).
- Gate 3 oracle: Newton's second law for a free-falling rigid body
  before contact, `vy = g * t`.
- Gate 4 oracle: the boundary condition is part of the algorithm (grid
  velocities are zeroed inside the boundary layer; particles cannot
  cross).
- Gate 5 oracle: Stomakhin hardening gives plastic compression under
  impact; det Jp != 1 is the signature of plastic flow.
- Gate 6 oracle: momentum conservation of a symmetric drop (no
  horizontal forcing).

Nothing passes because "the solver ran" — every gate is a measured
number against an independent physical target.
