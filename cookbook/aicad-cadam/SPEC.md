# SPEC: AI-CAD with CADAM's kernel (text-to-CAD part design, judged)

## Goal

Show an agent-next sandbox running a real text-to-CAD pipeline: the agent
designs mechanical parts from short text specs as OpenSCAD source — the
format [CADAM](https://github.com/Adam-CAD/CADAM) (GPL-3.0, pinned commit
`eb216809c04fc353a58c3806e01e8b6676ee8488`) emits from its LLM step and
compiles with its vendored OpenSCAD engine — and a judge that the agent
cannot fool decides, from the delivered files alone, whether each part
matches its spec to micrometre-level CAD tolerances.

CADAM's generation pipeline is: text prompt → LLM-authored OpenSCAD source
→ OpenSCAD engine (its vendored `openscad-wasm`, upstream OpenSCAD 2021.01)
→ STL / SCAD / DXF export. The LLM step needs a key the sandbox does not
have, so this demo runs the deterministic half of the pipeline headless:
the pinned **native OpenSCAD 2021.01** CLI (same upstream version as the
tool's wasm engine) compiles the checked-in agent-authored `.scad` inputs.
`README.md` documents the full agent loop including the LLM step.

Three specs of rising difficulty:

1. **bushing** — flanged bushing.
2. **plate** — adapter plate with a bolt circle (plus a 2D DXF drawing).
3. **bracket** — L-bracket with a concave and a convex fillet.

The judge uses four independent oracles — analytic volumes, a
reference solid built from the spec by OCCT (via OCP), tessellation-XOR
against that reference (manifold3d), and feature readback from the
delivered B-rep and DXF — so no single tool's say-so can pass a part.

## Non-goals

- No LLM calls: CADAM's LLM step is documented, not executed (no key).
- No CADAM web UI in the graded loop (UI serving is a documented README
  step for the screenshot, which is out of scope for this change).
- No mesh→B-rep conversion: the STEP deliverable is authored, never
  derived from the STL, so the two representations cross-check each other.
- No OpenSCAD version other than Debian bookworm's `2021.01-6`.
- No media generation in this change (see RECEIPT.md Deviations).

## Artifact

One directory per case under `examples/good/<case>/` (mutants mirror it):

| file | what | produced by |
|---|---|---|
| `case.json` | `{"case": "bushing"}` — names the spec the judge grades against | agent |
| `part.scad` | parametric OpenSCAD source of the part (CADAM's LLM-target format) | agent |
| `part.stl` | binary STL exported from `part.scad` by the pinned OpenSCAD CLI | tool |
| `part.step` | AP214 STEP B-rep with analytic (cylindrical/planar) faces | agent, via OCP |
| `drawing.scad` (plate only) | 2D top-view drawing: outline + bore + bolt holes | agent |
| `drawing.dxf` (plate only) | DXF exported from `drawing.scad` by the pinned OpenSCAD CLI | tool |

The judge never trusts a shipped output: `grade.sh` re-exports `part.stl`
and `drawing.dxf` from the shipped `.scad` sources in a scratch copy and
gates the shipped files against them, so a result cannot pass by
committing someone else's mesh.

## Part specs (mm — the single source of truth for every gate)

### bushing
- Body: cylinder OD Ø30, z ∈ [0, 25].
- Flange: cylinder OD Ø50, z ∈ [25, 30].
- Bore: Ø12 through everything, axis = z at (0, 0).
- Analytic volume: `π/4·[(50²−12²)·5 + (30²−12²)·25]` = 24096.0157 mm³.
- STEP cylindrical face radii (sorted): `[6.0, 15.0, 25.0]`.

### plate
- Plate: 80 (x) × 60 (y) × 8 (z), origin at a corner.
- Center bore: Ø20 through, axis z at (40, 30).
- Bolt holes: 6 × Ø6 through, centers on bolt circle R24 about (40, 30),
  at angles 0°, 60°, …, 300° (CCW from +x).
- Analytic volume: `80·60·8 − π/4·20²·8 − 6·π/4·6²·8` = 34529.56 mm³.
- STEP cylindrical face radii (sorted): `[3,3,3,3,3,3,10]`.
- DXF top view: outline rectangle 80×60, bore circle R10, 6 hole circles
  R3 on R24 at 60° spacing.

### bracket
- Base: 60 (x) × 40 (y) × 6 (z), z ∈ [0, 6].
- Upright: x ∈ [54, 60], y ∈ [0, 40], z ∈ [6, 46].
- Concave fillet: R6 along the inner edge at (x=54, z=6), full depth 40.
- Convex fillet: R4 along the outer top edge at (x=60, z=46), full depth.
- Analytic volume:
  `60·40·6 + 6·40·40 + 6²(1−π/4)·40 − 4²(1−π/4)·40` = 24171.68 mm³.
- STEP cylindrical face radii (sorted): `[4.0, 6.0]`.

## Gates (numeric pass rules)

All gates run per artifact; `grade.sh` exits 0 only if every gate passes.
Measured values are rounded to 1e-3 before comparison (determinism).

| # | gate | rule |
|---|---|---|
| 1 | `scad_export` | pinned OpenSCAD re-exports `part.stl` from the shipped `part.scad` (exit 0, non-empty STL) |
| 2 | `stl_matches_scad` | manifold3d XOR volume of shipped vs re-exported STL ≤ 0.1 % of reference volume |
| 3 | `stl_watertight` | trimesh `is_watertight` == True |
| 4 | `stl_winding` | trimesh `is_winding_consistent` == True |
| 5 | `bbox` | per-axis extents vs analytic extents, ≤ 0.05 mm; bbox origin within 0.05 mm |
| 6 | `volume_stl` | `|V_stl − V_analytic| / V_analytic` ≤ 0.5 % |
| 7 | `xor_reference` | manifold3d XOR volume of shipped STL vs the OCCT reference solid tessellated at 0.01 mm deflection ≤ 1 % of V_ref |
| 8 | `step_reimport` | STEP re-imports via OCP and `BRepCheck_Analyzer.IsValid` == True |
| 9 | `volume_step` | re-imported B-rep volume vs analytic ≤ 0.5 %; also vs shipped STL ≤ 1 % (representations must agree) |
| 10 | `cyl_faces` | cylindrical face count and radius multiset of the re-imported STEP match the spec table within 0.05 mm |
| 11 | `planar_min_wall` | minimum distance between anti-parallel planar face pairs of the STEP (pairs whose projections overlap) ≥ 2.0 mm |
| 12 | `case_features` | spec-specific rules (our own code, all others are library results): bushing radial wall `r_body − r_bore` ≥ 2.0 mm; plate bore-to-hole ligament `(R24 − r3) − r10` ≥ 2.0 mm and hole-to-edge ligament `30 − R − r3` ≥ 2.0 mm; bracket fillet radii present |
| 13 | `dxf_valid` (plate) | ezdxf reads and audits the re-exported DXF with 0 errors; shipped DXF matches it (entity count equal, circle fits within 0.05 mm) |
| 14 | `dxf_features` (plate) | loops from LINE chains: outline extents within 0.05 mm; circular loops: count 7, radii within 0.05 mm, centers on bolt circle R24 ± 0.05 mm at 60° ± 0.05° spacing, bore at (40, 30) ± 0.05 mm |

## Acceptance oracle

- Analytic volumes above (closed form from the spec table).
- Reference solids rebuilt by the judge from the spec table with OCCT
  primitives via OCP (cadquery-ocp 7.7.2) — independent of anything the
  artifact ships — used for the XOR gate and cross-checked against the
  analytic volume to 0.1 % before any verdict is issued.
- Known-bad mutants (judge/mutants.py): ≥ 5 single-edit mutants of the
  good inputs; self-test kill rate ≥ 90 %.

## Determinism

No randomness anywhere; `--seed N` is accepted and recorded but unused.
OpenSCAD output geometry is deterministic though vertex ordering is not —
every gate compares volumes, bboxes, radii and angles (order-insensitive),
rounded to 1e-3. `selftest.sh` grades a good case twice and requires
byte-identical verdict JSON modulo the `timing` key.

## Toolchain (pinned, sha256-checked; `judge/VERSIONS.txt` records reality)

| tool | version | role | licence |
|---|---|---|---|
| OpenSCAD (Debian bookworm deb) | 2021.01-6 | CADAM's engine generation, run headless | GPL-3.0 |
| cadquery-ocp (OCCT bindings) | 7.7.2 (cp312 manylinux wheel, hash-pinned) | STEP re-import, BRepCheck, reference solids | Apache-2.0 |
| trimesh | 4.3.2 | STL watertight/winding/bbox/volume | MIT |
| manifold3d | 3.0.1 | boolean XOR symmetric difference (composed: `(A−B) ∪ (B−A)`) | Apache-2.0 |
| ezdxf | 1.3.0 | DXF audit + entity read | MIT |

CADAM itself is cited, not installed: URL + commit above, GPL-3.0, run —
never vendored — per repo policy.
