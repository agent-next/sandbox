# cad-to-usd — CAD to OpenUSD conversion round-trip — spec

## Goal

Convert real CAD parts from a public repository to OpenUSD `.usda` files
with correct scene units and up-axis, inside a disposable agent-next
sandbox. The agent produces the conversion command and configures the
converter; the judge checks the result against an independent CAD oracle
(OpenCASCADE via `cadquery-ocp`) and a USD reader (`usd-core`) — never
just "the tool ran".

## Fixed problem statement (judge constants)

| quantity | value |
|---|---|
| source repo | https://github.com/NVIDIA-Omniverse/RC-Car-CAD |
| pinned commit | `407bd553ee57668ceb58d81ffd7f4d617dee3dfa` |
| parts (3, fetched at run time) | `Servo Futaba S3003 v6.step`, `ShockTowerFront/_ShockTowerFront.stp`, `Servo Futaba S3003 v6.iges` |
| converter | `usd-convert-cad` pip wheel, exact pin in `judge/setup.sh` |
| required scene units | millimeters: `metersPerUnit = 0.001` (i.e. 0.001 m per 1 scene unit) |
| required up-axis | `upAxis = "Z"` |
| output format | `.usda` (ASCII USDA) per part |

## Non-goals

- modifying, repairing or re-authoring the CAD geometry — conversion only
- material fidelity, lighting, cameras, animations
- any CAD format other than STEP/IGES inputs from the pinned repo above
- performance tuning of the converter; one grade must run in minutes
- the agent does not choose the source parts, the units, or the up-axis —
  they are fixed above

## Artifact

A directory containing, per part (named after the part's stem):

1. `<part>.usda` — the converted USDA stage for that part.
2. `convert.sh` — the conversion script that produced it: one
   `usd-convert-cad -i <src> -o <part>.usda` invocation per part, with
   any converter flags the agent chose to set (e.g. `--up-axis Z`), plus
   the pinned tool version. The judge re-runs `convert.sh` on fresh
   copies of the source files and grades the USDA files it regenerates, so
   the artifact is reproducible from the script alone.

## Judge gates (all must pass)

1. **file_set** — all three `<part>.usda` files exist and parse as USDA;
   the artifact is not a copy of another part's output (per-part file
   sizes and checksums must differ across parts).
2. **stage_meta** — for every part: `metersPerUnit = 0.001` (within
   1e-9), `upAxis = "Z"`, and the default prim resolves.
3. **geometry_counts** — for every part: `prim count > 0` and
   `mesh count > 0` in the parsed stage.
4. **bbox_match** — for every part: mesh bounding box from the USD,
   converted to source (mm) units, agrees with the OpenCASCADE oracle
   bounding box on the same STEP source within **1%** per axis (relative
   to the oracle extent; a flat axis uses an absolute 0.1 mm floor).
5. **area_match** — for every part: total triangle area of the USD mesh,
   converted to source (mm) units, agrees with the OpenCASCADE oracle
   total face area within **3%**.
6. **conversion_script** — `convert.sh` exists, is executable, and
   re-running it on fresh copies of the pinned sources reproduces the
   same three parts (each regenerated part is itself graded by gates
   2–5).

## Acceptance oracle

Independent of the converter under test:

- **OpenCASCADE** (`cadquery-ocp` wheel, exact pin in `judge/setup.sh`)
  reads the same STEP/IGES source and computes the exact analytic
  bounding box (via `Shape.BoundingBox()`) and exact total surface area
  (sum of `Face.Area()` over `Shape.Faces()`). This is the reference
  geometry.
- **usd-core** (the `usd-core` pip wheel — NOT the converter's bundled
  `pxr`, which conflicts in-process) reads the USD stage and computes the
  mesh bounding box and total triangle area by walking every `Mesh` prim
  and reading its `points`, `extent`, `faceVertexCounts` and
  `faceVertexIndices` attributes.

Validation happens before any comparison: a part whose USDA is missing,
unparseable, has wrong scene metadata, or whose USD bbox/area disagree
with the oracle beyond tolerance fails every gate.

## Self-test

`judge/mutants.py` writes scripted single-edit mutants of `examples/good`
(wrong units `metersPerUnit = 1`, Y/Z axis swap via an authored transform,
a dropped mesh, a decimated mesh beyond the area tolerance, an empty
stage, the garbage STEP as input, a missing part file, a copy of another
part's output). Each mutant and the gate that kills it is listed in
`examples/bad/README.md`.

`judge/selftest.sh` requires the good artifact to pass, >= 90 % of the
mutants to fail at least one gate, and two grades of the good artifact
with the same `--seed` to give byte-identical verdict JSON except the
`timing` key.

## Third-party sources

| source | version / pin | licence |
|---|---|---|
| RC-Car-CAD repo (STEP/IGES inputs) | commit `407bd553ee57668ceb58d81ffd7f4d617dee3dfa` | MIT (https://github.com/NVIDIA-Omniverse/RC-Car-CAD/blob/main/LICENSE) |
| usd-convert-cad wheel | exact pin in `judge/setup.sh` | NVIDIA Omniverse Licensing Terms |
| cadquery-ocp wheel | exact pin in `judge/setup.sh` | Apache-2.0 |
| usd-core wheel | exact pin in `judge/setup.sh` | Apache-2.0 (NVIDIA-maintained OpenUSD) |
