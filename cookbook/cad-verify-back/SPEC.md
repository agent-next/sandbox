# cad-verify-back: mechanical CAD with CadQuery, verified from delivered files

## Goal

An agent designs an **industrial adapter plate** with **CadQuery 2.7.0** (its
OCCT kernel) from a customer spec JSON, and delivers three files:

- `part.step` — the solid, STEP AP214,
- `part.stl` — a tessellated mesh for 3-D printing / downstream viewers,
- `part.dxf` — a 2-D drawing of the plate face with every hole as a circle.

A judge it cannot fool then **verifies what was delivered, never the
in-memory model**: it re-imports the STEP through OCCT and validates it with
`BRepCheck_Analyzer`, parses the STL with trimesh (watertightness, winding,
volume), reads the DXF with ezdxf, and compares the re-imported solid against
a reference solid rebuilt from the spec alone via a manifold3d boolean XOR.
Every expected number comes from closed-form analytic geometry derived only
from the spec JSON. The agent can also be asked to deliver `part.py` (the
CadQuery script); the judge ignores it — only the exported files are graded.

The point of using a sandbox: the agent installs a pinned CAD toolchain
(CadQuery/OCCT + ezdxf + apt graphics libraries), generates its own geometry,
and iterates against the judge in an isolated, disposable environment where
nothing it exports can touch the judge's oracle.

## Non-goals (explicitly out of scope)

- No photorealistic rendering, animation, or drawing title blocks; the DXF is
  geometry only (circles for every hole, a closed outline).
- No GD&T, tolerances beyond the numeric gates below, no threads, chamfers,
  fillets or drafting standards.
- No CAM, slicing, or FEA on the delivered geometry.
- No multi-part assemblies; exactly one solid per STEP file.
- No dependence on the agent's toolchain at grade time: geometry checks run
  on mature OSS (OCCT `BRepCheck_Analyzer`, trimesh, manifold3d, ezdxf) over
  the *delivered files*; only the spec rules remain as the judge's own code.

## Spec JSON (the customer drawing)

`judge/spec.json` is the single source of truth. The judge derives every
expected number from it in closed form; the agent may read it but never write
it.

| field | value (this demo) | meaning |
|---|---|---|
| `plate_l` | 120.0 mm | plate length (X) |
| `plate_w` | 80.0 mm | plate width (Y) |
| `plate_t` | 6.0 mm | plate thickness (Z) |
| `bore_d` | 24.0 mm | central through-bore diameter, on the plate centre |
| `boss_od` | 36.0 mm | raised boss outer diameter, concentric with the bore |
| `boss_h` | 5.0 mm | boss height above the top face |
| `bolt_n` | 6 | number of bolt holes |
| `bolt_d` | 7.0 mm | bolt hole diameter |
| `pcd` | 56.0 mm | bolt-hole pitch-circle diameter, centred on the plate |
| `min_edge` | 8.0 mm | minimum distance from any hole to the plate edge |
| `min_lig` | 6.0 mm | minimum ligament (solid web) between adjacent holes |

Bolt holes are evenly spaced on the PCD starting at angle 0° (along +X).
The plate is centred on the origin in X and Y; the bottom face is Z=0.
With these values the tightest measured design margins are 12.25 mm edge
distance (±60° holes, along Y) and 6.5 mm ligament (bolt hole to boss OD).

## Artifact

The agent delivers `part.step`, `part.stl` and `part.dxf`, produced by its
own `part.py` (CadQuery script; the good example is
`examples/good/part.py`). STEP is the primary deliverable; STL and DXF must
agree with it. The judge copies the three files into a scratch directory and
never runs the agent's Python.

## Judge gates (numeric pass rules)

The judge (`judge/grade.sh` → `judge/grade.py`) reads the spec, derives the
expected geometry analytically, and applies these gates. All are numeric,
deterministic and independent of the tool that produced the artifact.

| gate | check on the delivered files | pass rule |
|---|---|---|
| G1 `step_solid` | STEP re-imported through OCCT (CadQuery `importers.importStep`) | exactly 1 solid; not null; volume > 0 |
| G1b `step_valid` | re-imported solid checked with OCCT `BRepCheck_Analyzer` | the B-rep is valid (no errors reported) |
| G2 `step_bbox` | bounding box of the re-imported solid vs spec | each dimension ≤ 0.01 mm from `plate_l × plate_w × (plate_t + boss_h)` |
| G3 `step_volume` | OCCT volume vs closed-form analytic volume from the spec | relative error ≤ 0.1 % |
| G4 `step_holes` | cylindrical through-holes found in the solid: central bore + `bolt_n` bolt holes, by axis position and radius, grouped from face centres with matching radii at top and bottom | count = `bolt_n + 1`; bore diameter within 0.01 mm of `bore_d`, centred within 0.01 mm; bolt diameters within 0.01 mm of `bolt_d` |
| G5 `step_pcd` | bolt-hole centres from G4 | every centre within 0.02 mm of the PCD circle radius `pcd/2` and of the analytic PCD positions |
| G6 `angular_spacing` | angular steps between consecutive bolt-hole centres from G4 | every step within 0.05° of `360°/bolt_n` |
| G7 `step_xor` | manifold3d boolean XOR (symmetric difference) of the tessellated re-imported solid vs a reference solid built from the spec alone | XOR volume ≤ 1 % of the reference volume |
| G8 `stl_watertight` | STL parsed with trimesh | `is_watertight` and `is_winding_consistent` both true |
| G9 `stl_orient` | trimesh mesh volume | positive (outward-facing facets) |
| G10 `stl_volume` | trimesh volume of the STL mesh | within 1 % of the STEP (OCCT) volume |
| G11 `dxf_circles` | DXF read with ezdxf: CIRCLE entities | exactly `bolt_n + 2` circles (bore, boss OD, bolt holes); each diameter within 0.01 mm of its spec value; centres within 0.02 mm of the analytic positions |
| G12 `dxf_outline` | DXF outline (LINE and/or ARC entities, or one closed POLYLINE/LWPOLYLINE) | a closed rectangle `plate_l × plate_w` centred on the origin, corners within 0.01 mm |
| G13 `design_rules` | from the STEP-derived hole geometry | min hole-edge distance ≥ `min_edge` − 0.01 mm; min ligament between adjacent holes ≥ `min_lig` − 0.01 mm |

The judge never runs the artifact's Python and never imports the artifact's
modules; geometry is verified with OCCT / trimesh / manifold3d / ezdxf over
the delivered files, against expected numbers derived in closed form from
the spec alone.

## Acceptance oracle

The oracle is **closed-form analytic geometry from the spec**: expected bbox
`plate_l × plate_w × (plate_t + boss_h)`; expected volume
`V = l·w·t + π/4·boss_od²·boss_h − π/4·bore_d²·(t + boss_h) − bolt_n·π/4·bolt_d²·t`
(solid boss annulus, bore drilled through plate and boss, bolts through plate
only); expected hole positions `(pcd/2·cos θᵢ, pcd/2·sin θᵢ)` with
`θᵢ = 360°·i/bolt_n`; DXF circle positions; and design-rule margins computed
from the analytic hole centres (edge distance of each hole to the nearest
plate edge minus its radius; ligaments between adjacent bolt holes, between
the bore and bolt holes, and between the boss OD and bolt holes). The judge
writes these numbers into the verdict JSON so a pass can be checked by hand.

## Self-test (mandatory)

`judge/selftest.sh`:

1. the known-good example (`examples/good/`) must pass every gate;
2. every scripted single-edit mutant from `judge/mutants.py` must fail at
   least one gate: wrong bolt count, wrong PCD, bore diameter off by 0.5 mm,
   boss missing, inch/mm scale error (×25.4), one STL facet with reversed
   winding, non-watertight STL (one facet dropped), DXF missing a hole, hole
   violating the edge-distance rule, and one bolt hole drifted 0.5 mm along
   the PCD (STEP and DXF agree, radial error 0 — only the angular-spacing
   gate catches it). The self-test prints **every** failing gate per mutant
   and refuses a "kill" whose verdict contains only skipped gates (no gate
   failed on its own evidence);
3. determinism: same seed → identical verdict JSON (except the `timing` key);
4. kill rate must be ≥ 90 %.

## Tools (pinned by the judge)

| tool | version | how pinned |
|---|---|---|
| CadQuery | 2.7.0 | pip wheel, sha256 checked by setup.sh |
| ezdxf | 1.4.4 | pip wheel, sha256 checked by setup.sh |
| trimesh | 5.1.1 | pip wheel, sha256 checked by setup.sh |
| manifold3d | 3.5.4 | pip wheel, sha256 checked by setup.sh |
| OCCT | 7.8.1 (wheel `cadquery-ocp==7.8.1.1.post1`, the CadQuery 2.7.0 constraint `>=7.8.1,<7.9`) | pip wheel, sha256 of the wheel checked by setup.sh |
| Python | 3.12 (system) | system |
| libgl1, libglu1-mesa, libxrender1, libxkbcommon0, libegl1 | Debian 12 bookworm versions | apt; exact recorded versions in `judge/VERSIONS.txt` |

No tool is fetched with `latest`. Geometry checks use the pinned OSS
libraries above; the judge's own code is the closed-form oracle and the
spec rules only.
