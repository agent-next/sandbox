# AI-CAD part design with FreeCAD + freecad-mcp — spec

## Goal

Show the real AI-CAD user flow: an agent works inside a disposable agent-next
sandbox, drives FreeCAD 1.0.1 through the freecad-mcp MCP server, and turns a
short text spec into delivered CAD files (STEP + STL, plus a DXF drawing for
the plate). A judge the agent cannot fool decides from the **delivered files
alone** — never from "the tool ran" — using analytic volumes, a reference
solid built from the spec, and mesh topology checks.

Three parts of rising difficulty:

| part | features |
|---|---|
| `bushing` | flanged bushing: bore, hub, flange (2D-revolution class) |
| `plate` | adapter plate: central bore, 6-hole bolt circle, DXF drawing |
| `bracket` | L-bracket: base + upright, inner fillet R8, two hole sets |

## Fixed problem statement (judge constants, all mm, origin at part datum)

**bushing** — axis +Z through origin. Through bore Ø20 over the full height.
Hub Ø36 × 40 high (z 0→40). Flange Ø60 × 8 thick at the bottom (z 0→8).

**plate** — plate 100 × 80 × 10 centred on origin (x ±50, y ±40, z ±5).
Central through bore Ø30. Six through holes Ø5.5 on a bolt circle of R35
centred on the origin in the XY plane, first hole at 0° from +X, then every
60°.

**bracket** — base plate x 0→80, y 0→50, z 0→10; upright x 70→80, y 0→50,
z 0→60; inner fillet R8 tangent to the base top face (z = 10) and the upright
inner face (x = 70). Two Ø10 through holes in the base, axes +Z at (25, 25)
and (55, 25). Two Ø12 through holes in the upright, axes +X at y = 15 and
y = 35, z = 45.

Analytic solid volumes (judge computes these itself):

- `V_bushing = pi·(18²·40 − 10²·40 + (30² − 18²)·8)`
- `V_plate   = 100·80·10 − pi·15²·10 − 6·pi·2.75²·10`
- `V_bracket = 80·50·10 + 10·50·50 + 8²·(1 − pi/4)·50 − 2·pi·5²·10 − 2·pi·6²·10`

## Non-goals

- no assemblies, sheet metal, drafts, threads or tolerances on the drawing
- no FEM/CAM; the DXF is a 2-D entity drawing, not an annotated drawing sheet
- the agent does not choose dimensions — the three parts above are fixed;
  the demo shows the loop (spec → tool → delivered files → judge), not design
  freedom
- GPU/media work is out of scope for this task

## Tooling (pinned, run not vendored)

| tool | version / pin | licence |
|---|---|---|
| FreeCAD | 1.0.1 conda Linux x86_64 AppImage, sha256 `5a3fc4…0f6e` (full digest in `judge/setup.sh`), run `--appimage-extract`, GUI under Xvfb for the RPC addon, `freecadcmd` for headless rebuilds | LGPL-2.1+ |
| freecad-mcp | git `78bf0230a03324b56c9a0b7f55150fb5be2a0d42` (addon 0.1.27) | MIT |
| judge stack | trimesh 4.6.6, manifold3d 3.1.1, cadquery 2.5.2 (OCP), ezdxf 1.4.0, numpy 2.2.6 — exact pins in `judge/requirements.txt` | per package |

GPL/LGPL tools are executed from upstream release artifacts; nothing GPL is
vendored into this repo.

## Artifact

Per part, a directory of delivered files:

- `<part>.step` — AP214 STEP export of the solid (judge re-imports it)
- `<part>.stl` — binary STL of the same solid
- `<part>.dxf` — plate only: top-view drawing (outline + circles)
- `build.py` — the agent's FreeCAD build script (provenance; the judge never
  executes it)

`examples/good/` holds one known-good artifact per part, produced by the
checked-in agent scripts through the real MCP pipeline.

## Judge gates (all must pass; numeric)

Let `V_a` be the analytic volume, `V_ref` the judge-built CadQuery reference
solid volume, tol_rel the relative tolerance.

1. **files** — all required files for the part exist and parse.
2. **brep** — STEP re-imports via CadQuery/OCP as exactly 1 solid,
   `BRepCheck_Analyzer` reports valid, and OCP's own volume matches the
   analytic volume within **0.5 %**.
3. **bbox** — STEP solid bounding box matches the spec box on every axis
   within **0.05 mm**.
4. **stl_topology** — trimesh: `is_watertight` and `is_winding_consistent`
   are true; STL mesh volume within **0.5 %** of `V_a`.
5. **xor_reference** — judge tessellates the reference solid (deflection
   0.02 mm) and the delivered STL, takes the manifold3d boolean XOR; its
   volume must be **<= 1 % of V_ref**.
6. **features** — cylindrical faces read from the STEP via OCP, matched by
   radius within **0.05 mm**: bushing has faces of radius {10, 18, 30} on the
   Z axis; plate has 1 × R15 + 6 × R2.75 with centres on R35 at 0°, 60°, …,
   300° ±0.1°; bracket has 2 × R5 + 2 × R6 + 1 × R8 fillet. Plane count
   reported.
7. **min_wall** — manufacturability: min wall thickness measured from the STL
   by inward-ray chords over ≥ 2000 seeded surface samples must be
   **>= 1.2 mm** (spec min wall 1.5 mm + measurement allowance). The plate's
   tightest wall is 2.25 mm, the bracket's 4 mm.
8. **dxf** (plate only) — ezdxf `audit()` reports zero errors; entity graph
   holds 7 CIRCLEs (1 × R15 + 6 × R2.75 at the bolt-circle positions) and a
   4-vertex rectangular outline 100 × 80 centred on the origin.

Gate 6 is the spec-specific rule (hole counts, diameters, angular spacing,
fillet radius) written for this demo; every other gate leans on the pinned
open-source libraries listed above.

## Acceptance oracle

Independent of the tool under test (FreeCAD produced the artifact; the judge
uses CadQuery/OCP + trimesh + manifold3d + ezdxf instead):

- analytic volume formulas above (closed form, hand-checkable);
- a reference solid rebuilt from the spec constants by the judge with
  CadQuery, compared by manifold3d XOR symmetric-difference volume;
- OCCT `BRepCheck_Analyzer` for B-rep validity;
- trimesh watertight/winding/topology predicates for the STL;
- ezdxf audit + entity read for the DXF.

## Self-test

`judge/mutants.py` writes scripted single-edit mutants of the good build
scripts and delivered meshes:

| mutant | edit | killed by |
|---|---|---|
| `bushing_bore_22` | bore Ø20 → Ø22 | features, volume, xor |
| `bushing_no_flange` | flange thickness 8 → 0 | bbox, volume, xor |
| `plate_hole_count_5` | 6 bolt holes → 5 | features (count) |
| `plate_hole_drift` | first hole 0° → 3° | features (angular position) |
| `plate_scale_25_4` | all dims × 25.4 | bbox, volume, xor |
| `bracket_no_fillet` | fillet R8 → 0 | features (R8), volume, xor |
| `bushing_stl_gap` | drop 4 facets from the good STL | stl_topology |
| `bushing_stl_flip` | flip 3 facets' winding | stl_topology |

`judge/selftest.sh` requires: the good artifacts pass; every mutant fails at
least one gate (kill rate 100 % >= 90 %); two grades of a good artifact with
the same `--seed` give byte-identical verdict JSON apart from the `timing`
key; checksums of `judge/` are unchanged by grading.
