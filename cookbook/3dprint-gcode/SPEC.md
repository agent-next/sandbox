# FDM toolpath demo — OrcaSlicer G-code judged by an independent interpreter + Klipper

## Goal

Show an agent producing a real FDM 3D-print toolpath — a slicer profile plus
G-code from **OrcaSlicer** (the slicer people actually run; sliced with the
bundled *Bambu Lab A1 0.4 nozzle* system profile) — and having a judge it
cannot fool decide whether the result is right.

The agent writes a **slicer profile** (`profile.ini`, flat
`key = value` OrcaSlicer setting overrides) and produces
**G-code** (`part.gcode`) by slicing a fixed part STL shipped in the
`task/` directory. Two independent oracles grade it:

- `judge/interp.py` — a from-scratch G-code interpreter (Python stdlib only)
  replaying G0/G1/G28/G90/G91/G92/M82/M83/M104/M109/M140/M190 with
  absolute/relative positioning and E modes and G92 offsets. It measures
  every geometry/volume/temperature/time quantity the gates use. The
  slicer's own comments (`; filament used`, `; model printing time`) are
  parsed only to be *compared against* these measured values.
- **Klipper batch mode** — the real printer-firmware host stack
  (`klippy.py printer.cfg -i job.gcode -o out.serial -v -d out/klipper.dict`,
  pinned Klipper commit, MCU data dictionary built as Klipper's own test
  suite does). The artifact's G-code, normalized to Klipper-supported
  commands, must run to completion with no errors and no out-of-range or
  over-extrusion moves on a cartesian printer matching the spec bed.

## The task

`task/` holds:

| file | what |
|---|---|
| `make_stl.py` | generates `bracket.stl` and `cube.stl` deterministically (stdlib only) — run at grade time, STLs are never committed |
| `bracket.stl` | (generated) ASCII STL of an L-bracket, bounding box 40 x 20 x 15 mm, min corner at (20, 20, 0) |
| `cube.stl` | (generated) 25 mm calibration cube, min corner at (60, 60, 0) — cross-check oracle only |
| `spec.json` | the physical print spec, quoted below |

## The artifact the agent produces

The judge grades a **directory** (typically `examples/good/`):

```
<dir>/profile.ini    OrcaSlicer setting overrides, one "key = value" per line
<dir>/part.gcode     G-code for bracket.stl, sliced with that profile
```

The judge merges `profile.ini` on top of a fixed base preset
(`judge/orca-base.json`: Bambu Lab A1 0.4 nozzle machine, Bambu PLA Basic
filament, 0.20 mm process defaults, marlin flavor, absolute E, Klipper-safe
start/end G-code owned by the judge) and re-slices `bracket.stl` with
`orca-slicer --slice 0 --arrange 0 --orient 0`. The artifact's `part.gcode`
must match what the judge's re-slice produces, and the replayed G-code is
what is graded. An agent cannot hand-craft pretty G-code whose profile would
slice something else, and cannot ship a profile whose actual output would
fail — both are measured.

Placement: with `--arrange 0 --orient 0` the model prints at its native STL
coordinates, so the analytic footprint is computed directly from
`bracket.stl` with no translation step.

## Print spec (`task/spec.json`, the contract)

| key | value | meaning |
|---|---|---|
| `filament_diameter_mm` | 1.75 | filament diameter the nozzle is fed |
| `nozzle_diameter_mm` | 0.4 | nozzle orifice |
| `material` | PLA | hotend 180–230 °C, bed 35–70 °C |
| `layer_height_min_mm` / `layer_height_max_mm` | 0.10 / 0.30 | allowed steady layer height band |
| `first_layer_height_min_mm` / `first_layer_height_max_mm` | 0.10 / 0.30 | first layer Z above the bed |
| `max_first_layer_vs_nozzle` | 1.5 | first layer height <= 1.5 x nozzle |
| `bed_size_mm` | [250, 210] | usable bed in X/Y, origin corner |
| `brim_max_mm` | 10.0 | how far outside the part footprint extrusion may go (skirt/brim allowance) |
| `wall_loops_min` | 2 | perimeter loop count floor |
| `infill_pct_min` / `infill_pct_max` | 10 / 40 | allowed sparse infill density, per cent |
| `max_filament_g` | 12.0 | deposited filament mass ceiling |
| `max_print_time_s` | 5400 | print time ceiling (90 min) |
| `pla_density_g_cm3` | 1.24 | material density for the mass check |
| `volume_band_frac` | 0.30 | half-width of the analytic deposited-volume band |
| `skirt_allowance_mm3` | 300 | mm^3 allowed on top of the model for skirt/priming |
| `time_band_frac` | 0.25 | tolerance between judge- and slicer-estimated print time |

## Acceptance oracle

Nothing the slicer says about its own output is trusted. Four independent
oracles:

1. **The judge's own G-code interpreter** (`judge/interp.py`) — a
   from-scratch replay per the RepRap convention. It measures every
   quantity the gates use: extrusion length from E-word deltas in whichever
   mode the file selects, positions after all offsets, layer Z sequence,
   temperatures in order, and a constant-velocity time lower bound.
2. **Analytic STL model** — the judge computes the part's volume, bounding
   box and per-layer slice polygons from `bracket.stl` alone (polyhedron
   volume by signed tetrahedra; slice rasterisation at the extrusion width).
   Expected deposited volume per layer is
   `area x layer_h x (shell_fraction + (1 - shell_fraction) x infill)`,
   where `shell_fraction` is the fraction of the slice cells lying within
   `wall_loops x line_width` of the boundary — the pass band is
   +-`volume_band_frac` around that expectation plus `skirt_allowance_mm3`;
   the mass ceiling is the hard wall.
3. **Klipper batch mode** — independent firmware-level check: the G-code
   (normalised to Klipper-supported commands only) is replayed through
   klippy's motion planner on a cartesian printer with the spec bed and
   A1-class kinematic limits (`judge/printer.cfg`). Any klippy error —
   unknown structure, move out of range, over-extrusion, shutdown — fails.
4. **The calibration-cube cross-check** — `cube.stl` is sliced with the
   same profile and the judge's deposited volume must land inside the
   cube's analytic band. This gate fails the judge, not the agent, if the
   interpreter's arithmetic or the band derivation is wrong.
5. **Judge-directory checksums** — sha256 of every file under `judge/` is
   taken before and after grading; any change fails the run.

## Gates

The judge prints exactly one verdict JSON object; exit 0 only if every gate
passes. `P` = measured, `R` = rule.

| # | gate | measured | pass rule |
|---|---|---|---|
| 1 | `slice_clean` | OrcaSlicer exit code slicing `bracket.stl` with `<dir>/profile.ini` | exit 0 **and** non-empty G-code |
| 2 | `artifact_matches_profile` | judge-re-sliced G-code vs `<dir>/part.gcode`, comment lines stripped, whitespace-normalised | identical content hash (proves profile and G-code belong together) |
| 3 | `moves_inside_bed` | every extruding move endpoint and segment | 0 <= x <= 250, 0 <= y <= 210, z >= 0 |
| 4 | `moves_near_part` | every extruding move at z <= 15.6 (part top) | distance from XY segment to part footprint <= `brim_max_mm` |
| 5 | `layer_z_sequence` | measured Z of every extrusion layer | Z non-decreasing between extrusion layers (dip > 0.05 mm fails); first layer Z in [0.10, 0.30] and <= 1.5 x nozzle; every steady layer height in [0.10, 0.30] and <= 0.8 x nozzle |
| 6 | `volume_matches_model` | deposited volume = sum(dE) x pi x (1.75/2)^2 vs analytic model from gate geometry | within +-30 % band + skirt allowance, and mass <= 12 g |
| 7 | `cube_crosscheck` | same volume measurement on judge-sliced `cube.stl` | inside the cube's analytic band (judge self-consistency) |
| 8 | `pla_temperatures` | M104/M109/M140/M190 set points in order | every nozzle set point in [180, 230] °C while extrusion follows; every bed set point in [35, 70] °C; first bed heat command precedes first extrusion |
| 9 | `time_estimate_consistent` | interpreter feedrate integration (constant-velocity lower bound) vs slicer's `model printing time` comment | within +-25 % band and <= `max_print_time_s` |
| 10 | `klipper_batch` | klippy exit code + log scan on the normalized G-code | exit 0, zero ERROR/WARNING lines outside the benign whitelist |
| 11 | `profile_contract` | `wall_loops`, `sparse_infill_density` (and filament/nozzle fields) parsed from `profile.ini` | wall_loops >= 2, infill in [10 %, 40 %], nozzle diameter 0.4, filament diameter 1.75 |
| 12 | `judge_intact` | sha256 over `judge/` before vs after | identical |

Steady layer height is measured between consecutive extrusion-layer Zs,
excluding the first layer (which gets its own band). Retraction and Z-hop
are recognised: a `G1 Z` move without extrusion inside a layer does not
start a new layer.

`grade.sh` takes only `--seed` and `--json`. The seed is recorded in the
verdict; the interpreter, slicer and Klipper run are deterministic so the
verdict (minus the `timing` key) is byte-identical across same-seed runs.

## Known-bad family

`judge/mutants.py` generates single-edit mutants of `examples/good/`. Each
edits either `profile.ini` (one value) or `part.gcode` (one class of edit)
exactly once. The mutants the self-test runs:

| mutant | edit | gate(s) that must fail |
|---|---|---|
| `filament-diameter-2.85` | `filament_diameter = 2.85` in profile | `volume_matches_model` (E deltas sized for 2.85 mm filament under-read on the 1.75 contract — deposited volume drops out of band) |
| `petg-temps` | nozzle 240, bed 85 in profile | `pla_temperatures` |
| `layer-height-0.35` | `layer_height = 0.35` on a 0.4 nozzle | `layer_z_sequence` (0.35 > 0.8 x 0.4) |
| `scale-off-bed` | post-edit G-code: shift all X moves +150 | `moves_inside_bed` **and** `moves_near_part` |
| `first-layer-z-zero` | post-edit G-code: first layer `G1 Z0.000` | `layer_z_sequence` |
| `relative-e-mixup` | post-edit G-code: insert `M83` mid-print in an absolute-E file | `volume_matches_model` (each absolute E number re-read as a delta) |
| `infill-100` | `sparse_infill_density = 100` in profile | `volume_matches_model` **and** `profile_contract` |
| `nozzle-cold` | post-edit G-code: first `M109 S170` | `pla_temperatures` |
| `bed-heats-late` | post-edit G-code: move first `M140`/`M190` after the first extruding move | `pla_temperatures` |
| `travel-cuts-part` | post-edit G-code: one extruding move 60 mm outside footprint+brim at mid-height | `moves_near_part` |

Every mutant is a one-spot edit from the good artifact; `mutants.py` writes
each as a fresh directory holding a complete `profile.ini` + `part.gcode`.
Mutants that edit the profile are re-sliced by gate 2 itself; mutants that
edit the G-code diverge from the profile and therefore also fail
`artifact_matches_profile`, but each must *additionally* fail the
behavioural gate named in its row — the self-test classifies kills and
requires every target gate to fire.

## Non-goals

- Not a printer demo: nothing is printed; Klipper runs in batch
  (motion-planning) mode, not on hardware. The interpreter validates the
  toolpath, not the plastic.
- Not a slicer shootout: OrcaSlicer is the slicer, one version is pinned,
  no tuning advice. (Fallback slicers Bambu Studio / PrusaSlicer are
  documented in `judge/setup.sh` comments but not used.)
- No acceleration/jerk model in the interpreter, no pressure advance, no
  cooling model: the time gate is a constant-velocity lower bound
  cross-checked against the slicer's own estimate with a stated band.
- Supports, multi-material, sequential printing, modifiers: out of scope.
- The judge is not a security boundary: `grade.sh` runs the slicer with the
  artifact's profile, so a hostile profile that injects a post-processing
  script could influence the verdict. The judge-owned base preset clears
  `post_process`, but grade untrusted artifacts in a disposable sandbox.

## What this demo does not prove

- That the part would print well: layer adhesion, warping, ringing,
  stringing and surface quality are physics neither oracle models.
- That OrcaSlicer is right: the judge can only catch paths that violate
  the numeric spec; a subtly bad but in-spec path passes.
- Anything about nozzle wear, filament moisture, or machine calibration.

## Tolerances for reproduction

- Verdict JSON minus `timing` must be byte-identical across same-seed runs
  on any amd64 Debian 12 host with the pinned toolchain.
- `deposited_volume_mm3` and `stl_volume_mm3` must match a reproduction run
  exactly (deterministic sums over the same inputs).
- Wall-clock fields under `timing` drift; nothing else may.
