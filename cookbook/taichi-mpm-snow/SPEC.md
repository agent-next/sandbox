# SPEC: MLS-MPM snow with Taichi (CPU backend)

## Goal

Demonstrate an agent-next sandbox running a real, widely used open-source
simulation stack — [Taichi](https://github.com/taichi-dev/taichi)
(MIT license, v1.7.4, pinned exactly and sha256-checked) — to solve a
canonical material point method (MPM) problem: an elastoplastic
**snowball** (Stomakhin-style hardening) thrown at an angle into the
domain wall, where it shatters and splashes across the floor, while a
soft **jelly cube** free-falls and bounces for material contrast.

The agent's artifact is a pair of files — `sim.py` + `params.json` —
that run an MLS-MPM simulation on Taichi's **CPU backend**
(`ti.init(arch=ti.cpu)`), deterministic for a fixed `--seed`, writing a
metrics file and rendered RGB frames headless.

A judge the agent cannot fool decides whether the result is real,
conservative MPM — every gate compares numbers the judge extracts from
the artifact's own log against physical invariants, not against the
agent's claims.

## Non-goals

- 3D simulations (the judge runs 2D; a 3D artifact is out of scope).
- GPU backends (`ti.cuda`, `ti.vulkan`, …); the whole demo is CPU-only.
- Coupling to a mesh-based solver; solid materials other than the
  `snow`/`jelly`/`fluid` types in the artifact's `materials` table.
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
  `frame_stride` (rendered particle positions at `img_size`).

`params.json` follows this schema (all numbers MKS, seconds, metres):

```jsonc
{
  "dim": 2,
  "n_grid": 128,            // grid resolution per side
  "dt": 4e-4,               // seconds per step
  "steps": 2000,            // total steps
  "frame_stride": 4,        // one PNG every this many steps
  "seed": 0,                // default seed; --seed overrides
  "gravity": -9.81,
  "domain": [1.0, 1.0],     // lower-left corner at (0,0)
  "bound": 3,               // boundary layer width in grid cells
  "img_size": 1080,         // frame width/height in pixels
  "materials": [
    { "name": "snow",  "type": "snow",  "E": 6.0e3, "nu": 0.2,
      "rho": 400, "hardening": 5.0, "jp_min": 0.9, "jp_max": 1.2,
      "color": "#eef4ff",
      "disc": { "center": [0.22, 0.68], "r": 0.11 },
      "v0": [2.6, -0.3],
      "ppc": 16 },
    { "name": "jelly", "type": "jelly", "E": 5.0e3, "nu": 0.35,
      "rho": 1000, "hardening": 0.0, "jp_min": 0.9, "jp_max": 1.2,
      "color": "#2e6fb7",
      "box": { "lo": [0.58, 0.42], "hi": [0.70, 0.54] },
      "v0": [0.0, 0.0],
      "ppc": 16 }
  ]
}
```

- `type` is one of `snow` (fixed-corotated + Stomakhin hardening),
  `jelly` (fixed-corotated, no hardening, i.e. purely elastic) or
  `fluid` (volume penalty only, no deviatoric stress).
- Each material gives exactly one shape: `box` (`lo`/`hi` corners) or
  `disc` (`center`/`r`); particles fill the shape on a lattice with
  spacing `dx/sqrt(ppc)`.
- `v0` is the uniform initial velocity `[vx, vy]` of that material
  (absent means `[0, 0]`).

The judge reads `params.json` to derive expected values; the gates are
numeric on the artifact's own `metrics.jsonl`.

## Metrics

Every per-step row must carry: `step`, `time`, `mass_particles`,
`mass_grid_after_p2g`, `mass_by_material` (list, aligned with
`params.materials`), `px`, `py`, `ke` (total kinetic energy), `v_max`,
`com_x`, `com_y`, `vel_com_x`, `vel_com_y`, `x_min`, `y_min`, `x_max`,
`y_max`, `snow_x_min`, `snow_y_min`, `snow_x_max`, `snow_y_max`,
`jp_min`, `jp_max`, `jp_frac_lt_09`, `jp_frac_gt_11`, and
`snow_height` (the y-extent of the snow-material particles).

`metrics.jsonl` is parsed as the longest finite prefix: a row that is
unparsable, missing a field, or non-finite ends the prefix.  Every
gate below is evaluated on that prefix, so a solver that crashes at
step k still owes the invariants of the rows it wrote — a blow-up is
killed by its physics gate(s) *and* by Gate 1, not by the crash alone.

## Gates (numeric pass rules)

### Gate 1 — completion and sanity
- `sim.py` exits 0 within the wall budget (`SPEC_WALL_S`, default
  1800 s).
- `metrics.jsonl` has exactly `steps + 1` finite rows (step 0 … steps)
  and nothing else.

### Gate 2 — mass conservation and grid-vs-particle agreement
- `|mass_particles[t] - mass_particles[0]| / mass_particles[0] <= 1e-12`
  for every step t (particles do not gain or lose mass).
- `|mass_grid_after_p2g[t] - mass_particles[t]| / mass_particles[0] <=
  1e-6` for every step t (P2G conserves mass to round-off).  A P2G
  stencil bug fails this on the very first finite rows.

### Gate 3 — ballistic free flight before first contact
- `gravity` must be negative (things fall down).
- `t_contact` = the first step whose **snow** bounding box reaches the
  boundary layer on any side (`snow_*_min <= (bound+2)*dx` or
  `snow_*_max >= domain - (bound+2)*dx`).  The run must contain one
  (the snowball must actually land).
- For every step with `skip < t < t_contact` (`skip = 20` rows, where
  round-off dominates):
  `|vel_com_y[t] - (v0y + gravity * time[t])| / |v0y + gravity *
  time[t]| <= 0.01` and `|vel_com_x[t] - v0x| <= 0.02`, where
  `v0x = px[0]/mass`, `v0y = py[0]/mass` are the measured initial
  centre-of-mass velocities.

### Gate 4 — boundary condition
- For every finite step t: `x_min[t] >= dx` and `y_min[t] >= dx` and
  `x_max[t] <= domain[0] - dx` and `y_max[t] <= domain[1] - dx`.
  Checked on every row of the finite prefix, so a missing boundary is
  detected at the first penetrating step, well before any blow-up.

### Gate 5 — plastic deformation on impact
- Final-row snowball squash in at least one dimension:
  `min(snow_height/h0, snow_width/w0) <= 0.93` with
  `snow_width = snow_x_max - snow_x_min`.
- Plasticity engaged: `jp_frac_lt_09[t_final] + jp_frac_gt_11[t_final]
  >= 0.05`.

### Gate 6 — horizontal momentum
- `|px[0] - px_expected| / mass <= 0.02` where
  `px_expected = sum_i mass_by_material[i] * v0[i][0]` — the
  initial momentum must be the one `params.json` declares.
- `|px[t] - px[0]| / mass <= 0.02` for every step `t < t_contact`
  (momentum is conserved while the snowball is in free flight).

### Gate 7 — mechanical-energy bound (stability)
- Let `E[t] = ke[t] + mass * |gravity| * com_y[t]` and `E0 = E[0]`.
  For every finite step: `E[t] <= E0 * 1.15`.  An explicit integrator
  with too large a `dt` injects energy every step after contact, so a
  blow-up is caught tens of steps before the first NaN.

### Gate 8 — judge integrity
- `sha256` of every file in `judge/` is identical before and after
  grading (the artifact cannot modify the judge).

## Acceptance oracle

Every gate compares a measured number from the artifact's own log
against a physical invariant of MPM:

- Gate 2 oracle: mass conservation of MPM (P2G is a partition-of-unity
  scattering; grid mass after P2G must equal particle mass to
  round-off).
- Gate 3 oracle: Newton's second law for a body in free flight,
  `vy = v0y + g*t`, and momentum conservation `vx = const`.
- Gate 4 oracle: the boundary condition is part of the algorithm (grid
  velocities are zeroed inside the boundary layer; particles cannot
  cross).
- Gate 5 oracle: Stomakhin hardening gives plastic compression under
  impact; det Jp != 1 is the signature of plastic flow.
- Gate 6 oracle: linear momentum is exactly conserved by P2G/G2P
  transfers; only the boundary and gravity may change it.
- Gate 7 oracle: explicit MLS-MPM is dissipative — mechanical energy
  can only decrease once integration is stable; growth means the
  scheme is unstable.

Nothing passes because "the solver ran" — every gate is a measured
number against an independent physical target.
