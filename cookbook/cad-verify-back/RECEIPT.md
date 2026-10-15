# RECEIPT — cookbook/cad-verify-back

Real command output from this demo's verification runs. Environment: 2 vCPU,
~3 GB RAM, Debian 12 (bookworm), Python 3.12.15, pip 25.0.1. All runs below
were executed against the working branch
(`sbx/demo-cad-verify-back-hm`, tip `2c2842c`) — the same sequence
`run.py` sends to `sbx exec`: `judge/setup.sh` → `judge/selftest.sh` →
`python3 examples/good/part.py` → `judge/grade.sh examples/good`.
The judge after this change: STL checks use trimesh 5.1.1
(is_watertight / is_winding_consistent / volume), the re-imported STEP is
validated with OCCT `BRepCheck_Analyzer`, and a manifold3d 3.5.4 boolean
XOR compares the delivered solid against a reference rebuilt from
`judge/spec.json` (≤ 1 % of the reference volume). The judge's own code is
now the closed-form oracle and the spec rules only; the hand-written STL
parser (`judge/stl.py`) is deleted.

## `bash judge/setup.sh` (from nothing: every pinned wheel uninstalled first)

```
[setup] installing pinned python wheels (cadquery 2.7.0, ezdxf 1.4.4, trimesh 5.1.1, manifold3d 3.5.4, occt via cadquery-ocp)
Defaulting to user installation because normal site-packages is not writeable
Collecting aiohappyeyeballs==2.7.1 ... (43 pinned wheels, all sha256-verified by pip --require-hashes)
  Using cached cadquery_ocp-7.8.1.1.post1-cp312-cp312-manylinux_2_31_x86_64.whl (70.3 MB)
  Using cached casadi-3.8.1-cp311-abi3-manylinux_2_28_x86_64.whl (89.4 MB)
  Using cached vtk-9.3.1-cp312-cp312-manylinux_2_17_x86_64.whl (92.2 MB)
  ...
Successfully installed aiohappyeyeballs-2.7.1 aiohttp-3.14.5 aiosignal-1.4.0 attrs-26.1.0 cadquery-2.7.0 cadquery-ocp-7.8.1.1.post1 casadi-3.8.1 contourpy-1.4.0 cycler-0.12.1 ezdxf-1.4.4 fonttools-4.67.0 frozenlist-1.8.0 idna-3.20 kiwisolver-1.5.1 manifold3d-3.5.4 matplotlib-3.11.2 more-itertools-11.2.0 msgpack-1.2.3 multidict-7.1.0 multimethod-1.12 nlopt-2.11.0 numpy-2.5.4 packaging-26.3 path-17.1.1 pillow-12.3.0 propcache-0.5.4 pyparsing-3.3.3 python-dateutil-2.9.0.post0 pyyaml-6.0.3 runtype-0.5.3 six-1.17.0 trame-4.0.0 trame-client-4.1.4 trame-common-1.2.9 trame-components-2.5.0 trame-server-4.1.0 trame-vtk-2.11.17 trame-vuetify-3.3.0 trimesh-5.1.1 typing-extensions-4.16.0 vtk-9.3.1 wslink-2.6.0 yarl-1.25.1
[setup] installed:
  cadquery 2.7.0
  cadquery-ocp 7.8.1.1.post1
  ezdxf 1.4.4
  trimesh 5.1.1
  manifold3d 3.5.4
[setup] import check OK (headless)
[setup] done.

real    0m38.710s
user    0m29.508s
sys     0m6.522s
setup exit=0
```

All 43 wheels report "Collecting … Using cached" with zero
"Requirement already satisfied" lines — a true from-nothing install of the
pinned set (38.7 s with pip's HTTP cache warm from earlier resolution; the
first fully cold install with network download of ~300 MB took ~4.5 min in
this sandbox). Idempotent re-run prints
`[setup] cadquery 2.7.0 + ezdxf 1.4.4 + trimesh 5.1.1 + manifold3d 3.5.4
already installed`, exit 0.

## `bash judge/selftest.sh`

```
selftest: known-good PASS
selftest: mutant KILLED: bore_off (step_volume, step_holes, dxf_circles)
    FAILED step_volume: volume 56118.1500 vs closed-form 56327.6550 (rel err 0.371940% > 0.1000%)
    FAILED step_holes: no cylinder of diameter 24.0 at the origin (found: [7.0, 7.0, 7.0, 36.0, 7.0, 7.0, 7.0, 24.5])
    FAILED step_pcd: skipped: no bolt centres from G4
    FAILED angular_spacing: skipped: no bolt centres from G4
    FAILED dxf_circles: no DXF circle of diameter 24.0 mm at the origin
    FAILED design_rules: skipped: no bolt centres from G4
selftest: mutant KILLED: boss_missing (step_bbox, step_volume, step_holes, step_xor, dxf_circles)
    FAILED step_bbox: bbox (120.0000, 80.0000, 6.0000) vs expected [120.0, 80.0, 11.0], component errors [0.0, 0.0, 5.0]
    FAILED step_volume: volume 53500.2216 vs closed-form 56327.6550 (rel err 5.019618% > 0.1000%)
    FAILED step_holes: bore cylinder spans z 0.000..6.000, expected 0..11.000 (not through)
    FAILED step_pcd: skipped: no bolt centres from G4
    FAILED angular_spacing: skipped: no bolt centres from G4
    FAILED step_xor: XOR symmetric-difference volume 2826.26 mm^3 (5.017% of the 56328.18 mm^3 reference solid) > 1%
    FAILED dxf_circles: 7 CIRCLE entities, expected 8 (bore + boss OD + 6 bolt holes)
    FAILED design_rules: skipped: no bolt centres from G4
selftest: mutant KILLED: dxf_missing_hole (dxf_circles)
    FAILED dxf_circles: 7 CIRCLE entities, expected 8 (bore + boss OD + 6 bolt holes)
selftest: mutant KILLED: edge_violation (step_pcd, angular_spacing, step_xor, dxf_circles)
    FAILED step_pcd: bolt centre radial error up to 2.1910 mm (> 0.02); radii=[25.865, 28.111, 25.865, 28.111, 30.191, 30.191]
    FAILED angular_spacing: angular steps ['57.2707', '55.2542', '57.2707', '62.3321', '65.5401', '62.3321'] deg vs expected 60.0 deg; max deviation ...
    FAILED step_xor: XOR symmetric-difference volume 1232.41 mm^3 (2.188% of the 56328.18 mm^3 reference solid) > 1%
    FAILED dxf_circles: no DXF circle of diameter 7.0 mm at (28.000, 0.000)
selftest: mutant KILLED: scale_inch_mm (step_bbox, step_volume, step_holes, step_xor, dxf_circles, dxf_outline)
    FAILED step_bbox: bbox (3048.0000, 2032.0000, 279.4000) vs expected [120.0, 80.0, 11.0], component errors [2928.0, 1952.0, 268.4 ...
    FAILED step_volume: volume 923044887.0501 vs closed-form 56327.6550 (rel err 1638606.400000% > 0.1000%)
    FAILED step_holes: no cylinder of diameter 24.0 at the origin (found: [177.8, 177.8, 914.4, 177.8, 177.8, 177.8, 177.8, 609.6])
    FAILED step_pcd: skipped: no bolt centres from G4
    FAILED angular_spacing: skipped: no bolt centres from G4
    FAILED step_xor: XOR symmetric-difference volume 923109822.48 mm^3 (1638806.342% of the 56328.18 mm^3 reference solid) > 1%
    FAILED dxf_circles: no DXF circle of diameter 24.0 mm at the origin
    FAILED dxf_outline: outline corners [(np.float64(-1524.0), np.float64(-1016.0)), ...] vs expected ...
    FAILED design_rules: skipped: no bolt centres from G4
selftest: mutant KILLED: stl_flipped_facet (stl_watertight)
    FAILED stl_watertight: mesh winding is inconsistent between adjacent faces
    FAILED stl_orient: skipped: STL did not pass the trimesh checks (stl_watertight)
    FAILED stl_volume: skipped: STL did not pass the trimesh checks (stl_watertight)
selftest: mutant KILLED: stl_not_watertight (stl_watertight)
    FAILED stl_watertight: mesh is not watertight (trimesh is_watertight=False, euler_number=-13)
    FAILED stl_orient: skipped: STL did not pass the trimesh checks (stl_watertight)
    FAILED stl_volume: skipped: STL did not pass the trimesh checks (stl_watertight)
selftest: mutant KILLED: tangential_hole_drift (step_pcd, angular_spacing, dxf_circles)
    FAILED step_pcd: bolt centre positions off by up to 0.5000 mm from analytic PCD positions
    FAILED angular_spacing: angular steps ['60.0000', '61.0231', '58.9769', '60.0000', '60.0000', '60.0000'] deg vs expected 60.0 deg; max deviation 1.0231 > 0.05 deg
    FAILED dxf_circles: no DXF circle of diameter 7.0 mm at (-14.000, 24.249)
selftest: mutant KILLED: wrong_bolt_count (step_volume, step_holes, step_xor, dxf_circles)
    FAILED step_volume: volume 56558.5620 vs closed-form 56327.6550 (rel err 0.409936% > 0.1000%)
    FAILED step_holes: feature count: 5 bolt-diameter through-holes found, expected 6
    FAILED step_pcd: skipped: no bolt centres from G4
    FAILED angular_spacing: skipped: no bolt centres from G4
    FAILED step_xor: XOR symmetric-difference volume 2005.79 mm^3 (3.561% of the 56328.18 mm^3 reference solid) > 1%
    FAILED dxf_circles: 7 CIRCLE entities, expected 8 (bore + boss OD + 6 bolt holes)
    FAILED design_rules: skipped: no bolt centres from G4
selftest: mutant KILLED: wrong_pcd (step_pcd, step_xor, dxf_circles, design_rules)
    FAILED step_pcd: bolt centre radial error up to 5.0000 mm (> 0.02); radii=[33.0, 33.0, 33.0, 33.0, 33.0, 33.0]
    FAILED step_xor: XOR symmetric-difference volume 2284.68 mm^3 (4.056% of the 56328.18 mm^3 reference solid) > 1%
    FAILED dxf_circles: no DXF circle of diameter 7.0 mm at (33.000, 0.000)
    FAILED design_rules: min edge distance 4.751 mm < spec 8.0 mm
selftest: kill rate 10/10 (100%)
selftest: determinism PASS (same seed -> identical verdict)
selftest: PASS

real    1m37.918s
user    1m36.304s
sys     0m7.216s
selftest exit=0
```

Kill rate **10/10 = 100 %** (required ≥ 90 %). Every mutant is killed by a
named gate (a FAIL verdict containing only skipped gates now fails the
self-test outright):

| mutant | killed by (named gates) |
|---|---|
| wrong_bolt_count | `step_holes` (feature count: 5 vs 6), `step_volume`, `step_xor`, `dxf_circles` |
| wrong_pcd | `step_pcd`, `step_xor`, `dxf_circles`, `design_rules` |
| bore_off | `step_volume`, `step_holes`, `dxf_circles` |
| boss_missing | `step_bbox`, `step_volume`, `step_holes`, `step_xor`, `dxf_circles` |
| scale_inch_mm | `step_bbox`, `step_volume`, `step_holes`, `step_xor`, `dxf_circles`, `dxf_outline` |
| stl_flipped_facet | `stl_watertight` (trimesh: winding inconsistent) |
| stl_not_watertight | `stl_watertight` (trimesh: not watertight) |
| dxf_missing_hole | `dxf_circles` |
| edge_violation | `step_pcd`, `angular_spacing`, `step_xor`, `dxf_circles` |
| tangential_hole_drift | `angular_spacing` (max deviation 1.0231° > 0.05°), `step_pcd`, `dxf_circles` |

The two mutants added in this change: `stl_flipped_facet` (one binary-STL
facet's winding reversed — topologically closed, so only trimesh's
winding-consistency check catches it) and `tangential_hole_drift` (one bolt
hole slid 0.5 mm along the PCD in STEP, STL and DXF alike — radial error
stays 0, volume and XOR stay inside tolerance, so the angular-spacing gate
is what kills it).

## `bash judge/grade.sh examples/good --json /tmp/cvb-verdict.json`

```
grade: PASS (all gates; judge integrity verified)

real    0m9.061s
user    0m6.875s
sys     0m0.869s
grade exit=0
```

Verdict JSON (`/tmp/cvb-verdict.json`, seed 20261014, abridged to the
pass/fail lines and key numbers; all 14 gates pass):

```
verdict: pass
  step_solid:      PASS  (solids=1, volume_mm3=56327.655)
  step_valid:     PASS  (OCCT BRepCheck_Analyzer: valid B-rep)
  step_bbox:      PASS  (measured [120.0, 80.0, 11.0] vs expected [120.0, 80.0, 11.0], max_err_mm=0.0)
  step_volume:    PASS  (volume 56327.655 mm^3 vs closed-form 56327.655, rel err 5.2e-16)
  step_holes:     PASS  (bore_d=24.0, bolt_d=7.0, 6 bolt centres)
  step_pcd:       PASS  (max radial err 0.0 mm; max pos err 0.0 mm)
  angular_spacing: PASS (steps [60.0 x 6] deg, max deviation 0.0)
  step_xor:       PASS  (XOR volume 0.0 mm^3 vs reference 56328.18 mm^3, rel err 0.0)
  stl_watertight: PASS  (trimesh: watertight=True, winding_consistent=True, 4040 vertices, 8104 faces)
  stl_orient:     PASS  (signed volume 56327.79 > 0)
  stl_volume:     PASS  (stl 56327.787 vs step 56327.655 mm^3, rel err 2.3e-06)
  dxf_circles:    PASS  (count=8, diameters [7.0, 24.0, 36.0])
  dxf_outline:    PASS  (corners [(60,40), (-60,40), (-60,-40), (60,-40)])
  design_rules:   PASS  (min_edge 12.2513 mm >= 8.0; min ligament 6.5 mm >= 6.0)
timing: {wall_s: 3.56}
```

(The wall-clock inside the JSON is grade.py only; the 9.1 s real time adds
shell startup, the two judge-directory checksums and the verdict print.)

## Fresh-sandbox comparison

| run | setup | selftest | grade (good) | verdict |
|---|---|---|---|---|
| this branch, from-nothing (`sbx/demo-cad-verify-back-hm`, `2c2842c`) | exit 0, 38.7 s (warm wheel cache), all 43 wheels installed | exit 0, kill 10/10, 97.9 s | exit 0, 9.1 s, all 14 gates | pass |
| previous lead run (`sbx/demo-cad-verify-back`, `bcd6368`, stdlib STL parser) | exit 0, 34.5 s | exit 0, kill 8/8, 95 s | exit 0, 15.7 s, all 11 gates | pass |

Identical key numbers across the parser change: volume 56327.655 mm^3,
bbox (120, 80, 11) mm, 8104 STL triangles, 8 DXF circles, min edge
12.25 mm, min ligament 6.5 mm — the trimesh gates measure the same mesh
the stdlib parser did.

## Deviations

- **Media:** not done — a later task builds `media/` for this demo (per the
  task brief: "Do NOT do media in this task").
- **REPRODUCE.md:** not done — needs a second agent (different model family)
  to follow README.md in a fresh sandbox; not possible from inside this
  build sandbox within budget.
- **Two local runs, not two sbx-cloud runs:** `sbx` sandboxes cannot be
  created from inside this sandbox (no `SBX_API_KEY` here). The runs above
  execute the exact command sequence `run.py` sends to `sbx exec`, in this
  disposable build sandbox with the pinned toolchain installed from
  nothing; `run.py` itself is verified by `python3 -m py_compile` plus the
  lead's previous end-to-end execution (PASS: EXIT 0, 192 s, kill 8/8 at
  `bcd6368`). The lead's end-to-end `run.py` execution against this branch
  will produce the true two-sandbox RECEIPT entries.
- **Setup timing:** 38.7 s is with pip's HTTP cache warm; the first fully
  cold install in this sandbox class (network download of ~300 MB of
  wheels) took ~4.5 min.
- **Suppressed trimesh warning:** grading the good example made trimesh
  emit `RuntimeWarning: invalid value encountered in divide` from its
  `center_mass` on the empty XOR result (identical meshes). The judge now
  filters that warning inside `xor_volume_mm3` — output is otherwise
  identical.
- **stl_orient evidence:** verified directly that a fully inverted mesh
  (all facet windings reversed) stays watertight and winding-consistent but
  reports a negative trimesh volume — so the `stl_orient` gate catches
  inside-out STL exports, not just the single flipped facet.
- The lead's earlier brief specified `boss_od` 40 mm / `pcd` 100 mm; those
  values put bolt holes outside an 80 mm plate width, so the example spec
  uses `boss_od` 36 mm / `pcd` 56 mm (12.25 mm edge, 6.5 mm ligament).
  SPEC.md records this (unchanged from the previous RECEIPT).
- OCCT version: CadQuery 2.7.0 resolves `cadquery-ocp 7.8.1.1.post1`
  (OCCT 7.8.1), not 7.7.x; SPEC.md and VERSIONS.txt record the actual pin.
