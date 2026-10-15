# SPEC — `cookbook/solidcraft-cad/`

An agent does real parametric mechanical CAD inside a disposable agent-next
sandbox: it writes a [SolidCraft](https://github.com/bherbruck/solidcraft)
command script for a customer part, and a judge it cannot fool decides
whether the part that SolidCraft *delivers* (STEP and STL files) matches the
spec. The judge re-measures those files with a second, independent CAD kernel
(OpenCascade) and compares them with numbers it computes by hand from the spec.

## Goal

Model the NEMA 17 motor-mount adapter plate in `spec.json` as a parametric
SolidCraft design: a rounded-corner plate with a centre bore, a raised boss
around the bore and four bolt holes on a pitch circle, light enough to meet a
mass limit in 6061 aluminium. Changing the design's `thickness` parameter must
rebuild the part correctly.

## Non-goals

- Drawings, tolerances/GD&T, threads, surface finish, manufacturability.
- Any particular modelling style: sketch-and-cut, holes, patterns,
  `solid.box` + booleans are all fine as long as the delivered part is right.
- Assemblies, the desktop GUI, the web build.
- Proving SolidCraft correct in general (the project keeps its own oracle in
  `docs/oracle.md` upstream). The judge only checks this one part.

## Artifact

`design.json`: a SolidCraft command script, `{"commands": [{"command": ...,
"params": {...}}, ...]}`, the same commands the SolidCraft UI and MCP server
run (`solidcraft-cli commands` lists them). Requirements:

- It defines a parameter named `thickness` (by `parameters.change` or
  `parameters.add`, under that name or renamed to it) that drives the plate
  thickness and the height of everything above the plate.
- It only uses modelling commands: names starting `sketch.`, `solid.`,
  `construct.`, `timeline.`, `select.`, plus `parameters.change`,
  `parameters.add`, `material.assign`, `appearance.assign`, `body.rename`,
  `edit.undo`, `edit.redo`, `document.units`. File, document, import/export,
  DXF/SVG and diagnostics commands are refused before SolidCraft runs (the
  judge does its own export). Commands nested inside params obey the same
  list, and a `font` must name an installed family, never a file path.
- Coordinates: plate centred on the origin in XY, bottom face on Z = 0, boss
  on +Z; millimetres.

## The part (`spec.json`, read by the judge from the demo directory — never from the artifact's folder)

| item | value |
|---|---|
| plate | 60 × 50 × `thickness` = 6 mm, 4 vertical corner edges R5 |
| centre bore | Ø22 through plate and boss |
| boss | Ø32 outer, 3 mm tall, on top of the plate, concentric with the bore |
| bolt holes | 4 × Ø3.4 through, on PCD 31·√2 = 43.8406 mm, first at 45° (the NEMA 17 31 mm square pattern) |
| min edge distance | 5 mm from any bolt hole edge to the plate outline |
| material | 6061-T6 aluminium, 2.70 g/cm³; mass ≤ 52 g |
| parametric check | `thickness` + 2 mm |

## Analytic reference (computed by the judge from `spec.json`)

    A_net = L·W − (4 − π)·r² − π·(D_bore/2)² − N·π·(d/2)²
    V     = A_net·T + π·((D_boss/2)² − (D_bore/2)²)·H
    ΔV    = A_net·ΔT           (thickness T → T + ΔT; the boss rides on top)

For this spec: A_net = 2562.0903 mm², V = 16644.887 mm³, mass 44.94 g,
ΔV(+2 mm) = 5124.181 mm³; bounding box [−30, −25, 0] .. [30, 25, 9] mm.

## Judge gates (`judge/grade.sh design.json [--seed N] [--json out.json]`)

All numeric and deterministic; exit 0 only if every gate passes. The
artifact is copied to a temp dir and built there; the judge tree and
`spec.json` are checksummed before and after grading.

| gate | pass rule |
|---|---|
| **build** | valid JSON; only allowed commands; `solidcraft-cli run design.json --out part.step --out part.stl` exits 0 (a failing timeline feature fails the run) and both files are non-empty |
| **occt_shape** | OCCT reads `part.step`: exactly 1 solid, `BRepCheck_Analyzer` valid, bounding box within **0.01 mm** of the analytic box |
| **volume** | OCCT volume within **0.2 %** of the analytic V |
| **features** | from the STEP's cylindrical faces with a Z axis — exact cylinders, or B-spline faces whose sampled normals are horizontal and whose points fit one circle to 1e-4 mm (concave = hole, convex = boss/fillet): exactly 1 centre bore Ø22 ± 0.02 running z 0..T+H; exactly N = 4 bolt holes, Ø ± **0.02 mm**, centres on the PCD ± **0.05 mm**, angular spacing 90° ± **0.1°**, every nominal centre (first at 45°) within **0.05 mm** of a hole, each through the plate, edge distance ≥ 5 mm; boss Ø32 ± 0.02 spanning z T..T+H ± 0.01; exactly 4 convex R5 corner fillets at the plate's corners. Then **wall checks** (20 exact OCCT booleans): for every found cylinder, the part is intersected with a thin tube 0.01–0.02 mm either side of it over the depth the spec requires (corners over their outer quarter). The empty side — a pin through each hole, the space round the boss and the corners — must hold no material and the solid side must be full, both to 1e-4 of the tool volume, so a web blocking a hole (any thickness above ~1e-4 of the pin's length, i.e. about 1 µm), or a wall straying more than 0.01 mm over more than 1e-4 of the tube, fails |
| **mass** | OCCT volume × 2.70 g/cm³ ≤ 52 g |
| **cross_check** | `solidcraft-cli eval` reports 1 body whose volume and area agree with OCCT within **0.1 %** and centre of mass within **0.01 mm** (both kernels must agree) |
| **parametric** | the judge appends `parameters.change thickness = T + 2 mm` to a copy of the script and rebuilds; the rebuilt part is graded against the spec at the new thickness: 1 valid solid, whole bounding box within 0.01 mm, every **features** check including the wall checks, and an OCCT volume change within **0.2 %** of ΔV (a frozen, literal-dimension or rebuild-dependent design fails) |
| **stl** | `part.stl` is a closed, consistently oriented 2-manifold (every directed edge used once, its reverse once; the triangles round every vertex form one fan; no degenerate triangle) and its divergence-theorem volume is within **0.5 %** of the STEP volume |

`--seed` is accepted and recorded for the standard's interface; the judge
makes no random choices.

## Acceptance oracle (independent of "it ran")

1. **Analytic geometry**: volume, bounding box, hole pattern and the
   parametric volume delta are computed from `spec.json` by closed-form
   formulas, not by SolidCraft.
2. **Second kernel**: every geometric number is measured by OpenCascade 8.0.1
   (via `cadquery-ocp`) on the delivered STEP, so a SolidCraft bug or a
   mis-exported file shows up as a disagreement. SolidCraft's own numbers are
   used only in `cross_check`, which requires the two kernels to agree.
3. **Mesh check**: the STL is checked by a stdlib edge-manifold test and an
   independent volume integral.
4. **Self-test**: `judge/selftest.sh` first runs the stdlib unit tests in
   `tests/` (circle fit on short arcs, STL manifold cases, command checks incl.
   deep nesting, features on a modelled part incl. a 0.1 mm web and a bulging
   bore, run.py cleanup under transport faults). It
   grades every known-good design in `examples/good/` (must pass):
   `design.json` (sketch + extrude), `design-csg.json` (boxes and cylinders
   combined, written by the independent reproducing agent; SolidCraft exports
   its rotated cylinders as B-spline faces, which the features gate fits as
   circles) and `design-renamed.json` (the parameter is created as `stock`
   and renamed to `thickness`). It then grades 19 single-edit mutants from
   `judge/mutants.py` (each must fail): hole Ø3.1, one hole 0.28 mm off the
   PCD, one hole rotated 3°, the whole bolt pattern turned 10° (spacing and
   PCD intact), a missing hole, an extra hole, missing bore, plate 7.5 mm
   (mass/box), boss 4 mm, square corners, thickness written as a literal, a
   misspelled command, a `file.export` that tries to write outside the work
   dir, a `sketch.text` that reads a font file outside it, and on the CSG
   design a bore moved 0.3 mm off centre (same volume: only the B-spline
   feature check can see it), a missing corner round, a 0.5 mm web inside
   every bolt hole (+0.11 % volume), a 0.1 mm web at z 3.1–3.2 (+0.02 %), and a move that only happens when
   `thickness` changes. Kill rate must be ≥ 90 %; same-seed grades must be
   byte-identical outside `timing`.

Tolerances: two fresh-sandbox runs and an independent reproduction must give
the same pass/fail per gate and the same key numbers to 6 significant figures
(`r6` rounding in the verdict).

Coverage note: the `mass` gate is a guard for spec variants. With this spec
every way to break the mass limit also changes the bounding box, so the
self-test kills those mutants at `occt_shape` first.
