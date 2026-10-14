# Text-to-CAD: three machined parts from short text specs

## Goal

Show an agent using the **text-to-cad** tool
([earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad), MIT
licence, most-starred AI-CAD project; the `cadgen` PyPI package it publishes is
what this demo installs) inside a disposable agent-next sandbox to turn short
text specs into machined parts, and a judge it cannot fool deciding whether the
**delivered files** — the STEP and STL the tool writes — are the part the spec
asked for.

The tool needs no LLM key for its model-execution step: a model is a plain
Python script (build123d geometry under the tool's `@step`/`@stl` decorators)
and the tool's CLI/python runtime executes it into STEP + STL files. So the
demo is deterministic: the agent's *output* (the model script) is checked in,
and `run.py` exercises the tool for real by executing that script in the
sandbox. The README's **Ask your agent** section shows the full agent loop,
where the agent writes the model script itself from the same specs.

## The three specs (rising difficulty)

| part | text spec asks for | why it is harder |
|---|---|---|
| `bushing` | flanged bushing: Ø 20 bar × 32 long on an Ø 36 × 8 flange, Ø 10 through bore | cylinders only, one hole |
| `adapter_plate` | 60 × 60 × 8 plate, Ø 12 centre bore, 4 × Ø 6.5 holes on a Ø 44 bolt circle at 45/135/225/315° | hole count, diameters, bolt-circle radius and angular spacing |
| `bracket` | L-bracket 50 wide × 60 tall × 40 deep, legs 10 thick, 2 × Ø 5 mounting holes per leg, R 5 fillet on the inner corner | fillet presence/radius, hole positions, min-wall rule |

All dimensions millimetres. Exact numbers live in `judge/spec.json`; that file
is written from this spec **by hand** and never derived from an artifact.
`judge/spec.json` is the contract.

### Hard numbers (also repeated in `judge/spec.json`)

- `bushing`: shaft Ø 20 × 32 above the flange; flange Ø 36 × 8; bore Ø 10
  through all 40. Analytic volume `π(10²−5²)·32 + π(18²−5²)·8 = 4792π mm³`.
  Bounding box 36 × 36 × 40. Cylindrical faces: shaft Ø 20, flange Ø 36,
  bore Ø 10. Min wall (bore to shaft OD) 5 mm.
- `adapter_plate`: plate 60 × 60 × 8, centred on the Z axis; centre bore Ø 12
  through; 4 through holes Ø 6.5 on bolt-circle diameter 44, first hole at 45°.
  Analytic volume `60·60·8 − π·6²·8 − 4·π·3.25²·8`. Bounding box 60 × 60 × 8.
  Cylindrical faces: 1 × Ø 12, 4 × Ø 6.5. Min wall (centre bore to bolt hole)
  12.75 mm.
- `bracket`: L cross-section bounded by (0,0),(50,0),(50,10),(10,10),(10,60),
  (0,60), extruded 40 in Y; legs 10 thick. Two Ø 5 holes through the Y depth
  per leg: vertical-leg holes axis at (x=5, z=35) and (x=5, z=55);
  horizontal-leg holes at (x=25, z=5) and (x=45, z=5). One R 5 fillet on the
  re-entrant inner corner along Y. Analytic volume
  `40000 − 4·π·2.5²·40 + 40·5²·(1−π/4)`. Bounding box 50 × 40 × 60.
  Min wall (hole edge to outside face) 2.5 mm.

## Non-goals

- Not a benchmark of model quality or generation speed; wall time is reported,
  not graded.
- The LLM step (turning the text spec into the model script) is not run
  unattended: it needs no extra key in text-to-cad, but it is the user's agent
  that does it. The demo judges what the **delivered files** are, whoever
  wrote the script; README shows the agent doing it live.
- No GD&T, no surface finish, no real machining simulation. The
  manufacturability gate is one plain min-wall rule, not a DfM suite.
- STEP file upload to fabrication services, drawings, GLB viewer: all out.

## The artifact

`grade.sh` takes one part directory (e.g. `examples/good/bushing/`):

| file | role |
|---|---|
| `spec.txt` | the short text spec the agent was given (checked in) |
| `model.py` | the agent-written text-to-cad model script that delivers the part (checked in) |
| `model.step`, `model.stl` | what the tool wrote when the agent executed `model.py` (checked in for `examples/good/`; small, < 120 KB each) |

The judge copies the artifact into a temp dir, re-executes `model.py` with the
pinned tool, requires the regenerated STEP/STL to equal the delivered files
byte for byte (the tool's exports are deterministic for identical inputs), and
then judges **the delivered files** — so judging proves the tool ran, and a
delivered file the tool would not have produced fails.

## Acceptance oracle

The judge never trusts the artifact to describe itself. Four independent
sources of truth:

1. **The CAD kernel** (OCP 7.9.3.1.1, via pinned `cadquery-ocp-novtk`)
   — STEP re-import, `BRepCheck_Analyzer` validity, exact B-rep volume, exact
   bounding box, cylindrical-face radii/axes/positions.
2. **trimesh 4.12.2** — STL watertightness, winding consistency, mesh volume,
   mesh bounds.
3. **manifold3d 3.5.2** — a reference solid built from `judge/spec.json` alone
   (no tool code involved): boolean XOR symmetric-difference volume between
   the delivered STEP (tessellated by the kernel) and the reference.
4. **`judge/spec.json`** — hand-written from this SPEC.md; every numeric gate
   compares against it; checksums of `judge/` before and after prove the
   artifact did not edit its own judge.

ezdxf is part of the tool's pinned install (it is a cadgen dependency) and is
recorded in VERSIONS.txt; the 3D parts judged here have no 2D drawing, so no
gate is DXF-based.

## Gates

`grade.sh <part-dir> [--seed N] [--json out.json]` prints exactly one verdict
JSON and exits 0 only if every gate passes. `V` = measured, `R` = rule, both
reported in the gate detail.

| # | gate | measure | pass rule |
|---|---|---|---|
| 1 | `tool_runs` | pinned `cadgen` executes the artifact's `model.py` in a copy of the part dir | exit 0 **and** it wrote `model.step` and `model.stl` |
| 2 | `delivery_matches` | sha256 of delivered `model.step`/`model.stl` vs the fresh regeneration | byte-identical (the tool's exports are deterministic: cadgen pins the STEP header timestamp) |
| 3 | `step_valid` | OCP STEP re-import | import succeeds **and** `BRepCheck_Analyzer` valid **and** exactly one solid |
| 4 | `stl_valid` | trimesh | `is_watertight` **and** `is_winding_consistent`, one body |
| 5 | `bbox` | OCP STEP bounds and trimesh STL bounds vs spec | every axis extent within **0.05 mm** of spec; STEP vs STL agree within the STL chord tolerance |
| 6 | `volume_analytic` | OCP STEP volume vs analytic volume from spec dims | relative error ≤ **0.5 %** |
| 7 | `xor_volume` | manifold3d symmetric-difference volume, delivered STEP (kernel tessellation) vs reference solid built from spec | ≤ **1.0 %** of reference volume |
| 8 | `features` | cylindrical faces via OCP: per-class count, radius, centre | counts/radii exactly as spec; hole centres within **0.05 mm** of spec position; bolt-circle angular spacing **90° ± 0.5°** |
| 9 | `min_wall` | mesh-proximity wall thickness between hole surfaces and other faces (seeded sampling) | ≥ `spec.min_wall_mm − 0.1 mm` |
| 10 | `judge_intact` | sha256 of every file under `judge/` before vs after | identical |

Constants are environment-overridable (`JUDGE_TIME` budget etc. recorded in
the verdict); the only command-line inputs are the part dir, `--seed` and
`--json`. Gate 8's rules are the only home-grown checks; they implement this
SPEC.md and nothing else (count holes, read radii/axes off kernel cylinders,
check their angular spacing).

### Why each mutant class dies

| planned failure | gates that must catch it |
|---|---|
| wrong hole count | features, xor_volume, volume_analytic |
| wrong hole diameter | features, volume_analytic (ΔV ≈ 1.6 % on the plate) |
| missing feature (fillet) | features, xor_volume |
| scale × 25.4 on one dimension | bbox, xor_volume |
| non-watertight export | stl_valid, xor_volume |
| flipped facet | stl_valid (winding), xor_volume |
| tangential hole drift | features (angular spacing), xor_volume |

## Known-bad family

`judge/mutants.py` generates ≥ 5 mutants, each a **single edit** of the good
artifact — an edit of one line of `model.py` (geometry mutants, regenerated
with the tool) or of the delivered STL (mesh mutants):

| mutant | part | edit | gates that kill it |
|---|---|---|---|
| `plate-hole-count` | adapter_plate | `4 → 3` in the hole-count loop | features (+ volume, xor) |
| `plate-hole-diameter` | adapter_plate | `3.25 → 2.5` hole radius | features (+ volume) |
| `bracket-missing-fillet` | bracket | replace the fillet arc with its chord | features (+ volume_analytic; the XOR gate is deliberately insensitive below 1 %) |
| `bushing-scale-25_4` | bushing | `SHAFT_D = 20.0 → 20.0 * 25.4` (inch slip) | bbox (+ xor) |
| `bushing-non-watertight` | bushing | delete one triangle from the delivered STL | stl_valid |
| `plate-flipped-facet` | adapter_plate | flip one facet's winding in the delivered STL | stl_valid (winding) |
| `plate-hole-drift` | adapter_plate | first-hole angle `45 → 53` (tangential drift) | features (spacing) |
| `bracket-fillet-radius` | bracket | fillet radius `5 → 2` | features (radius) |

`judge/selftest.sh` regenerates each mutant with the tool, grades it, and
requires the good part to pass, every mutant to fail ≥ 1 gate, kill rate
≥ 90 %; it also grades the good artifact twice with the same seed and requires
byte-identical verdict JSON excluding the `timing` key.

## Seed and determinism

Kernel tessellation of the delivered STEP for the XOR gate and the min-wall
sampling use `numpy.random.PCG64(seed)`; `--seed` fixes them. Every other
number comes from exact B-rep evaluation or deterministic library code. Two
same-seed grades of the same artifact produce byte-identical verdict JSON
excluding the `timing` key; selftest.sh proves it.

## What this demo does not prove

- Passing gates mean the files are the specified geometry, not that the part
  is good engineering (no stress, tolerance-stack or fixturing analysis).
- The min-wall gate is a single geometric rule measured on the mesh, with a
  0.1 mm allowance; it is not a machinist's DfM review.
- The judge tests geometry, not provenance: it proves the delivered files
  match both the spec and a fresh run of the checked-in `model.py`, nothing
  about who typed what.
