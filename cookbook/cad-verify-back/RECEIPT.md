# RECEIPT — cookbook/cad-verify-back

Real command output from this demo's verification runs. Environment: 2 vCPU,
~4 GB RAM, Debian 12 (bookworm), Python 3.12.15, pip 25.0.1. All runs below
were executed against the pushed branch
(`sbx/demo-cad-verify-back`, commit `bcd6368`) cloned fresh to
`/tmp/cvb-runsim3/sandbox` — the same sequence `run.py` sends to `sbx exec`.

Fresh-sandbox run 1 (below) is that fresh clone + from-nothing toolchain
install. Fresh-sandbox run 2 is a second fresh clone (`/tmp/cvb-runsim2`,
branch commit `8181047`, before the `grade.sh` `__pycache__` fix) and gave
the same verdict numbers; its `grade.sh` integrity-check failure is recorded
under Deviations and is fixed in the final commit.

## `bash judge/setup.sh` (from nothing: pip packages uninstalled first)

```
[setup] installing pinned python wheels (cadquery 2.7.0, ezdxf 1.4.4, occt via cadquery-ocp)
Defaulting to user installation because normal site-packages is not writeable
Collecting aiohappyeyeballs==2.7.1 ... (41 pinned wheels, all sha256-verified by pip --require-hashes)
  Using cached cadquery_ocp-7.8.1.1.post1-cp312-cp312-manylinux_2_31_x86_64.whl (70.3 MB)
  Using cached casadi-3.8.1-cp311-abi3-manylinux_2_28_x86_64.whl (89.4 MB)
  ...
[setup] installed:
  cadquery 2.7.0
  cadquery-ocp 7.8.1.1.post1
  ezdxf 1.4.4
[setup] import check OK (headless)
[setup] done.

real    0m34.500s
user    0m26.245s
sys     0m5.406s
setup exit=0
```

Note: 34.5 s is with pip's HTTP cache warm from the earlier resolution; the
first fully cold run in this sandbox (download of ~300 MB of wheels over the
network + install) took ~4.5 min. Idempotent re-run (`already installed`
path): 15.7 s, exit 0.

## `bash judge/selftest.sh`

```
selftest: known-good PASS
selftest: mutant KILLED: bore_off (step_volume: volume 56118.1500 vs closed-form 56327.6550 (rel err 0.371940% > 0.1000%))
selftest: mutant KILLED: boss_missing (step_bbox: bbox (120.0000, 80.0000, 6.0000) vs expected [120.0, 80.0, 11.0], component errors ...)
selftest: mutant KILLED: dxf_missing_hole (dxf_circles: 7 CIRCLE entities, expected 8 (bore + boss OD + 6 bolt holes))
selftest: mutant KILLED: edge_violation (step_pcd: bolt centre radial error up to 2.1910 mm (> 0.02); radii=[25.865, 28.111, 25.865 ...)
selftest: mutant KILLED: scale_inch_mm (step_bbox: bbox (3048.0000, 2032.0000, 279.4000) vs expected [120.0, 80.0, 11.0], component ...)
selftest: mutant KILLED: stl_not_watertight (stl_watertight: edge (-60.0, -40.0, 6.0)->(-60.0, 40.0, 0.0) shared by 1 facets (need 2); edge ...)
selftest: mutant KILLED: wrong_bolt_count (step_volume: volume 56558.5620 vs closed-form 56327.6550 (rel err 0.409936% > 0.1000%))
selftest: mutant KILLED: wrong_pcd (step_pcd: bolt centre radial error up to 5.0000 mm (> 0.02); radii=[33.0, 33.0, 33.0, 33.0])
selftest: kill rate 8/8 (100%)
selftest: determinism PASS (same seed -> identical verdict)
selftest: PASS

real    1m35.260s
user    0m26.245s   (user/sys from this run: 1m26.640s / 7.431s)
selftest exit=0
```

Kill rate **8/8 = 100 %** (required ≥ 90 %): wrong_bolt_count, wrong_pcd,
bore_off, boss_missing, scale_inch_mm, stl_not_watertight, dxf_missing_hole,
edge_violation — each failed by the gate shown.

## `bash judge/grade.sh examples/good --json /tmp/v.json`

```
grade: PASS (all gates; judge integrity verified)

real    0m15.731s
grade exit=0
```

Verdict JSON (`/tmp/v.json`, abridged to the pass/fail lines and key numbers):

```
verdict: pass
  step_solid:    PASS  (solids=1, volume_mm3=56327.655)
  step_bbox:     PASS  (measured [120.0, 80.0, 11.0] vs expected [120.0, 80.0, 11.0], max_err_mm=0.0)
  step_volume:   PASS  (volume 56327.655 mm^3 vs closed-form 56327.655, rel err 5.2e-16)
  step_holes:    PASS  (bore_d=24.0, bolt_d=7.0, 6 bolt centres)
  step_pcd:      PASS  (angular steps [60.0 x 6] deg)
  stl_watertight:PASS  (triangles=8104, every edge shared by exactly 2)
  stl_orient:    PASS  (signed volume > 0)
  stl_volume:    PASS  (stl 56327.787 vs step 56327.655 mm^3, rel err 2.3e-06)
  dxf_circles:   PASS  (count=8, diameters [7.0, 24.0, 36.0])
  dxf_outline:   PASS  (corners [(60,40), (-60,40), (-60,-40), (60,-40)])
  design_rules:  PASS  (min_edge 12.2513 mm >= 8.0; min ligament 6.5 mm >= 6.0)
timing: {wall_s: 5.06}
```

(The wall-clock inside the JSON is grade.py only; the 15.7 s real time adds
shell startup, the two judge-directory checksums and the verdict print.)

## Fresh-sandbox comparison

| run | setup | selftest | grade (good) | verdict |
|---|---|---|---|---|
| fresh clone 1 (`/tmp/cvb-runsim3`, commit `bcd6368`) | exit 0, 34.5 s (warm wheel cache) | exit 0, kill 8/8, 95 s | exit 0, 15.7 s, all 11 gates | pass |
| fresh clone 2 (`/tmp/cvb-runsim2`, commit `8181047`) | exit 0 | not run at that commit | all 11 gates pass; then integrity-check false failure (fixed in `bcd6368`) | pass (grade logic) |

Both runs produced identical gate-level numbers: volume 56327.655 mm^3,
bbox (120, 80, 11) mm, 8104 STL triangles, 8 DXF circles, min edge 12.25 mm,
min ligament 6.5 mm.

## Deviations

- **Media:** not done — a later task builds `media/` for this demo (per the
  task brief: "Do NOT do media in this task").
- **REPRODUCE.md:** not done — needs a second agent (different model family)
  to follow README.md in a fresh sandbox; not possible from inside this
  build sandbox within budget.
- **Two sandbox runs, not two sbx-cloud runs:** `sbx` sandboxes cannot be
  created from inside this sandbox (no `SBX_API_KEY` here). Both fresh runs
  are fresh local clones of the pushed branch with the same commands
  `run.py` sends to `sbx exec`; `run.py` itself is verified by
  `python3 -m py_compile` plus executing its exact in-sandbox command
  sequence directly. The lead's end-to-end `run.py` execution will produce
  the true two-sandbox RECEIPT entries.
- The setup timing above is with pip's wheel cache warm; the first fully
  cold install in this sandbox (network download included) took ~4.5 min.
- The lead's brief specified `boss_od` 40 mm / `pcd` 100 mm; those values
  put bolt holes outside an 80 mm plate width (hole centres at y = ±43.3 mm
  vs half-width 40 mm), so the example spec uses `boss_od` 36 mm /
  `pcd` 56 mm to make the geometry valid with margins (12.25 mm edge,
  6.5 mm ligament). SPEC.md records this.
- OCCT version: CadQuery 2.7.0 resolves `cadquery-ocp 7.8.1.1.post1`
  (OCCT 7.8.1), not 7.7.x; SPEC.md and VERSIONS.txt record the actual pin.
