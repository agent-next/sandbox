# RECEIPT — cookbook/cad-verify-back

Real command output from this demo's verification runs. Environment: 2 vCPU,
~4 GB RAM, Debian 12 (bookworm), Python 3.12.15, pip 25.0.1. The commands are
the same sequence `run.py` sends to `sbx exec`: `judge/setup.sh` →
`judge/selftest.sh` → `python3 examples/good/part.py` →
`judge/grade.sh examples/good`. All outputs below are from the fixed judge
(after the independent-review fixes).

## `bash judge/setup.sh` (from-nothing install output)

```
[setup] installing apt graphics libs (libgl1 libglu1-mesa libxrender1 libxkbcommon0 libegl1)
Setting up libopengl0 (1.6.0-1) ...
Setting up libegl1:amd64 (1.6.0-1) ...
[setup] installing pinned python wheels (cadquery 2.7.0, ezdxf 1.4.4, trimesh 5.1.1, manifold3d 3.5.4, occt via cadquery-ocp)
Collecting aiohappyeyeballs==2.7.1 ... (43 pinned wheels, all sha256-verified by pip --require-hashes)
Successfully installed aiohappyeyeballs-2.7.1 aiohttp-3.14.5 aiosignal-1.4.0 attrs-26.1.0 cadquery-2.7.0 cadquery-ocp-7.8.1.1.post1 casadi-3.8.1 contourpy-1.4.0 cycler-0.12.1 ezdxf-1.4.4 fonttools-4.67.0 frozenlist-1.8.0 idna-3.20 kiwisolver-1.5.1 manifold3d-3.5.4 matplotlib-3.11.2 more-itertools-11.2.0 msgpack-1.2.3 multidict-7.1.0 multimethod-1.12 nlopt-2.11.0 numpy-2.5.4 path-17.1.1 pillow-12.3.0 propcache-0.5.4 pyparsing-3.3.3 python-dateutil-2.9.0.post0 pyyaml-6.0.3 runtype-0.5.3 six-1.17.0 trame-4.0.0 trame-client-4.1.4 trame-common-1.2.9 trame-components-2.5.0 trame-server-4.1.0 trame-vtk-2.11.17 trame-vuetify-3.3.0 trimesh-5.1.1 vtk-9.3.1 wslink-2.6.0 yarl-1.25.1
[setup] installed:
  cadquery 2.7.0
  cadquery-ocp 7.8.1.1.post1
  ezdxf 1.4.4
  trimesh 5.1.1
  manifold3d 3.5.4
[setup] import check OK (headless)
[setup] done.
```

The from-nothing run installed all 43 wheels and the five apt GL libraries,
exit 0. An idempotent re-run prints
`[setup] cadquery 2.7.0 + ezdxf 1.4.4 + trimesh 5.1.1 + manifold3d 3.5.4
already installed` and exits 0 (measured `real 0m46.0s` — the version probe
imports CadQuery four times).

## `bash judge/selftest.sh`

```
selftest: known-good PASS
selftest: artifact cannot inject python (no PWNED_* markers written)
selftest: mutant KILLED: bore_off (step_volume, step_holes, dxf_circles)
selftest: mutant KILLED: boss_missing (step_bbox, step_volume, step_holes, step_xor, dxf_circles)
selftest: mutant KILLED: dxf_missing_hole (dxf_circles)
selftest: mutant KILLED: dxf_outline_bowtie (dxf_outline)
selftest: mutant KILLED: dxf_outline_bulge (dxf_outline)
selftest: mutant KILLED: edge_violation (step_pcd, angular_spacing, step_xor, dxf_circles)
selftest: mutant KILLED: scale_inch_mm (step_bbox, step_volume, step_holes, step_xor, dxf_circles, dxf_outline)
selftest: mutant KILLED: stl_box_same_volume (stl_volume)
selftest: mutant KILLED: stl_flipped_facet (stl_watertight)
selftest: mutant KILLED: stl_not_watertight (stl_watertight)
selftest: mutant KILLED: tangential_hole_drift (angular_spacing, dxf_circles)
selftest: mutant KILLED: wrong_bolt_angles (angular_spacing)
selftest: mutant KILLED: wrong_bolt_count (step_volume, step_holes, step_xor, dxf_circles)
selftest: mutant KILLED: wrong_pcd (step_pcd, step_xor, dxf_circles, design_rules)
selftest: wrong_bolt_angles fails ONLY the angular_spacing gate
selftest: pass-case PASS: dxf_outline_lines
selftest: pass-case PASS: dxf_outline_shift
selftest: kill rate 14/14 (100%)
selftest: determinism PASS (same seed -> identical verdict)
selftest: PASS

real    13m2.918s
selftest exit=0
```

Kill rate **14/14 = 100 %** (required ≥ 90 %) plus **2/2 pass-cases**
surviving. Every mutant is killed by a named gate; a FAIL verdict containing
only skipped gates fails the self-test outright. `wrong_bolt_angles` is
additionally asserted to fail **only** `angular_spacing`, and the injection
case proves no `cadquery.py`/`ezdxf.py`/`trimesh.py` shipped next to the
artifact can run during grading (`python3 -I` from a scratch cwd).

| mutant | killed by (named gates) |
|---|---|
| wrong_bolt_count | `step_holes` (feature count 5 vs 6), `step_volume`, `step_xor`, `dxf_circles` |
| wrong_pcd | `step_pcd`, `step_xor`, `dxf_circles`, `design_rules` |
| bore_off | `step_volume`, `step_holes`, `dxf_circles` |
| boss_missing | `step_bbox`, `step_volume`, `step_holes`, `step_xor`, `dxf_circles` |
| scale_inch_mm | `step_bbox`, `step_volume`, `step_holes`, `step_xor`, `dxf_circles`, `dxf_outline` |
| stl_flipped_facet | `stl_watertight` (trimesh: winding inconsistent) |
| stl_not_watertight | `stl_watertight` (trimesh: not watertight) |
| stl_box_same_volume | `stl_volume` (bbox/XOR vs STEP tessellation) |
| dxf_missing_hole | `dxf_circles` |
| dxf_outline_bowtie | `dxf_outline` (self-crossing vertex order) |
| dxf_outline_bulge | `dxf_outline` (no straight-edge outline) |
| edge_violation | `step_pcd`, `angular_spacing`, `step_xor`, `dxf_circles` |
| tangential_hole_drift | `angular_spacing` (max deviation 1.0231° > 0.05°), `dxf_circles` |
| wrong_bolt_angles | `angular_spacing` only (asserted) |

## `bash judge/grade.sh examples/good --json /tmp/cvb-verdict.json`

```
grade: PASS (all gates; judge integrity verified)

real    0m39.306s
grade exit=0
```

Verdict JSON (seed 20261014, abridged; all 14 gates pass):

```
verdict: pass
  step_solid:      PASS  (solids=1, volume_mm3=56327.655)
  step_valid:      PASS  (OCCT BRepCheck_Analyzer: valid B-rep)
  step_bbox:       PASS  (measured [120.0, 80.0, 11.0] vs expected [120.0, 80.0, 11.0])
  step_volume:     PASS  (volume 56327.655 mm^3 vs closed-form 56327.655, rel err 5.2e-16)
  step_holes:      PASS  (bore_d=24.0, bolt_d=7.0, 6 bolt centres)
  step_pcd:        PASS  (max radial err 0.0 mm; max pos err 0.0 mm)
  angular_spacing: PASS  (steps [60.0 x 6] deg, max deviation 0.0, max angle err 0.0)
  step_xor:        PASS  (XOR volume 0.0 mm^3 vs reference 56328.18 mm^3, rel err 0.0)
  stl_watertight:  PASS  (trimesh: watertight=True, winding_consistent=True, 4040 vertices, 8104 faces)
  stl_orient:      PASS  (signed volume 56327.79 > 0)
  stl_volume:      PASS  (stl 56327.787 vs step 56327.655 mm^3, rel err 2.3e-06;
                          bbox err 0.0 mm; STL/STEP XOR 3.559 mm^3 = 0.006% ≤ 1%)
  dxf_circles:     PASS  (count=8, diameters [7.0, 24.0, 36.0])
  dxf_outline:     PASS  (4 corners matched, max_corner_err_mm=0.0)
  design_rules:    PASS  (min_edge 12.2513 mm >= 8.0; min ligament 6.5 mm >= 6.0)
timing: {wall_s: 21.98}
```

(The wall-clock inside the JSON is grade.py only; the 39.3 s real time adds
shell startup, the isolated dependency probe, and the two judge-directory
checksums.)

## Deviations

- **`REPRODUCE.md` is absent.** Independent reproduction by a different agent
  (DEMO-STANDARD.md:42) remains outstanding; nothing here fakes it.
- **`run.py` was not exercised end-to-end in this environment** (no `sbx`
  CLI/API key here). Its in-sandbox script is the same command sequence run
  above; the `--ref` commit-SHA fallback (`git fetch --depth 1 origin <sha>`
  + `git checkout FETCH_HEAD`) and `python3 -m py_compile` were verified
  directly.
- **`python3 -I` needs the pinned wheels in a site-packages it honours.**
  Isolated mode excludes the per-user site (`~/.local/lib/...`), so on a
  non-root install `setup.sh` must place the wheels in system site-packages
  (or run as root, as the sbx sandbox does); otherwise the grade.sh probe
  reports the toolchain as missing. This is the documented behaviour of
  `python3 -I`, kept deliberately so the artifact dir can never reach
  sys.path.
- **Wall times are longer than the earlier RECEIPT's.** The self-test now
  builds and grades 14 mutants + 2 pass-cases + the injection case + the
  determinism pair (13.0 min total; mutant generation dominates), and
  `stl_volume` adds a second tessellation + manifold3d XOR (~10 s per
  grade).
- **Suppressed trimesh warning:** grading the good example makes trimesh
  emit `RuntimeWarning: invalid value encountered in divide` from
  `center_mass` on the empty XOR result (identical meshes). The judge
  filters that warning inside `xor_volume_mm3`; output is otherwise
  identical.
- OCCT version: CadQuery 2.7.0 resolves `cadquery-ocp 7.8.1.1.post1`
  (OCCT 7.8.1), not 7.7.x; SPEC.md and VERSIONS.txt record the actual pin.
