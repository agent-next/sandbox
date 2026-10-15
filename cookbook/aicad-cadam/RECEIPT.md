# RECEIPT — aicad-cadam

Real output from the disposable Debian sandbox this demo was built in
(2 vCPU, ~3 GB RAM, sudo + internet). Everything below is pasted from
actual runs on 2026-10-15 (UTC), after `git clone` of this branch. The
two setup+selftest+grade runs were back-to-back with `~/.venvs/aicad`
wiped between them; a third grade pass reproduced the verdicts
byte-identically modulo the `timing` key (checked with a JSON compare,
not by eye).

## Toolchain that `judge/setup.sh` installed (`judge/VERSIONS.txt`)

```
# written by judge/setup.sh 2026-10-15T00:29:40Z
openscad: OpenSCAD version 2021.01
openscad-deb: 2021.01-6
cadquery-ocp: 7.7.2
ezdxf: 1.3.0
fonttools: 4.67.0
manifold3d: 3.0.1
numpy: 1.26.4
pyparsing: 3.3.3
trimesh: 4.3.2
typing_extensions: 4.16.0
python: Python 3.12.15
```

All 8 pip wheels are sha256-pinned in `judge/requirements.txt`
(`pip install --require-hashes`); the OpenSCAD deb is sha256-checked in
`setup.sh` against `judge/package-sha256.txt`
(`openscad_2021.01-6_amd64.deb d3f24936…470e3c01`).

## `bash judge/setup.sh` (fresh venv — wiped `~/.venvs/aicad` first)

Exit code **0**, wall **19 s**:

```
[setup] openscad 2021.01-6 already installed
[setup] Creating judge venv at /home/user/.venvs/aicad...

[notice] A new release of pip is available: 25.0 -> 26.2.1
[notice] To update, run: python3 -m pip install --upgrade pip
[setup] wrote /home/user/w/cookbook/aicad-cadam/judge/VERSIONS.txt
[setup] done
```

(Second run after another wipe: exit 0, 20 s, identical output. The
OpenSCAD deb install path with the sha256 check was exercised earlier
in the build session — the deb was fetched with `apt-get download
openscad=2021.01-6`, hash-matched, and installed; here it was already
present, which is the idempotent path.)

## `bash judge/selftest.sh`

Exit code **0**, wall **126 s** (≈2 min). Full pasted output:

```
[selftest] Regenerating mutants...
[mutants] bushing_bore_d12_to_15 <- bushing (part.scad, part.stl)
[mutants] bushing_inch_scale <- bushing (part.scad, part.stl)
[mutants] bushing_missing_flange <- bushing (part.scad, part.stl)
[mutants] plate_bolt_d6_to_7 <- plate (part.scad, part.stl)
[mutants] plate_bolt_circle_r24_to_27 <- plate (part.scad, part.stl)
[mutants] plate_hole_count_6_to_5 <- plate (drawing.scad, drawing.dxf)
[mutants] bracket_missing_fillet <- bracket (part.scad, part.stl)
[mutants] bracket_fillet_r6_to_3 <- bracket (part.scad, part.stl)
[mutants] bushing_flipped_facet <- bushing (part.stl)
[mutants] bracket_nonwatertight <- bracket (part.stl)
[mutants] plate_corrupt_step <- plate (part.step)
[mutants] 11 mutants in /home/user/w/cookbook/aicad-cadam/examples/bad

[selftest] Known-good cases (must PASS):
[selftest]   good/bushing  PASS  (5s)
[selftest]   good/plate  PASS  (19s)
[selftest]   good/bracket  PASS  (4s)

[selftest] Determinism (same case twice, verdict JSON minus 'timing'):
[selftest]   bushing  deterministic

[selftest] Known-bad mutants (must FAIL):
[selftest]   bracket_fillet_r6_to_3  killed (failed: volume_stl)
[selftest]   bracket_missing_fillet  killed (failed: volume_stl,xor_reference,volume_step)
[selftest]   bracket_nonwatertight  killed (failed: stl_watertight,volume_stl,volume_step)
[selftest]   bushing_bore_d12_to_15  killed (failed: volume_stl,xor_reference,volume_step)
[selftest]   bushing_flipped_facet  killed (failed: stl_winding,volume_stl,volume_step)
[selftest]   bushing_inch_scale  killed (failed: bbox,volume_stl,xor_reference,volume_step)
[selftest]   bushing_missing_flange  killed (failed: bbox,volume_stl,xor_reference,volume_step)
[selftest]   plate_bolt_circle_r24_to_27  killed (failed: xor_reference)
[selftest]   plate_bolt_d6_to_7  killed (failed: volume_stl,xor_reference,volume_step)
[selftest]   plate_corrupt_step  killed (failed: step_reimport,volume_step,cyl_faces,planar_min_wall,case_features)
[selftest]   plate_hole_count_6_to_5  killed (failed: dxf_features)

[selftest] ============================================
[selftest] good cases passed : 3/3
[selftest] kill rate         : 11/11 (100 %)
[selftest] ============================================
```

Kill rate **11/11 (100 %)** ≥ the required 90 %. An earlier full run
(after a separate venv wipe) gave the same 3/3 and 11/11 in 123 s.

## `bash judge/grade.sh examples/good/<artifact> --json /tmp/v.json`

| case | exit | gates passed | wall |
|---|---|---|---|
| bushing | 0 | 12/12 | 5 s (judge `total_s` 4.0) |
| plate   | 0 | 14/14 | 17 s (judge `total_s` 15.7) |
| bracket | 0 | 12/12 | 5 s (judge `total_s` 3.6) |

Pasted verdict JSON for the plate (the full 14-gate case):

```
{
 "case": "plate",
 "gates": [
  { "detail": "openscad 2021.01 exit 0", "gate": "scad_export", "passed": true },
  { "gate": "stl_matches_scad", "limit_mm3": 34.53, "measured_mm3": 0.0, "passed": true },
  { "gate": "stl_watertight", "passed": true },
  { "gate": "stl_winding", "passed": true },
  { "gate": "bbox", "limit_mm": 0.05, "measured_max_dev_mm": 0.0, "passed": true },
  { "analytic_mm3": 34529.558, "gate": "volume_stl", "limit": 0.005,
    "measured_mm3": 34531.108, "passed": true, "rel": 0.0 },
  { "gate": "xor_reference", "limit_mm3": 345.3, "measured_mm3": 1.193,
    "passed": true, "ref_volume_mm3": 34529.959 },
  { "detail": "BRepCheck_Analyzer on re-imported STEP", "gate": "step_reimport", "passed": true },
  { "gate": "volume_step", "limit_analytic": 0.005, "limit_stl": 0.01,
    "measured_mm3": 34529.558, "passed": true, "rel_vs_analytic": 0.0, "rel_vs_stl": 0.0 },
  { "expected_radii": [3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 10.0],
    "gate": "cyl_faces", "measured_radii": [3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 10.0],
    "passed": true, "tol_mm": 0.05 },
  { "gate": "planar_min_wall", "limit_mm": 2.0, "measured_mm": Infinity, "passed": true },
  { "bolt_circle_r": [24.0, 24.0, 24.0, 24.0, 24.0, 24.0], "bolt_count": 6,
    "bore_ligament_mm": 11.0, "edge_ligament_mm": 3.0, "gate": "case_features",
    "limit_mm": 2.0, "passed": true,
    "spacing_deg": [60.0, 60.0, 60.0, 60.0, 60.0, 60.0] },
  { "audit_errors": 0, "gate": "dxf_valid", "passed": true,
    "regenerated_lines": 900, "shipped_lines": 900 },
  { "bolt_circle_r": [24.0, 24.0, 24.0, 24.0, 24.0, 24.0], "bore_count": 1,
    "gate": "dxf_features", "hole_count": 6,
    "hole_radii": [3.0, 3.0, 3.0, 3.0, 3.0, 3.0], "passed": true,
    "spacing_deg": [60.0, 60.0, 60.0, 60.0, 60.0, 60.0] }
 ],
 "passed": true,
 "seed": 0,
 "timing": { "total_s": 15.704 }
}
```

Key numbers, bushing and bracket (identical across both receipt runs
and the third grade pass; `rel` fields round to 0.0 at 3 decimals):

```
bushing: volume_stl 24086.338 mm³ vs analytic 24096.016 (0.045 %, limit 0.5 %)
         xor_reference 9.548 mm³ (limit 240.935) vs judge-built OCCT ref 24093.519
         cyl_faces radii [6.0, 15.0, 25.0] = expected; radial wall 9.0 mm (limit 2.0)
bracket: volume_stl 24171.933 mm³ vs analytic 24171.681 (0.001 %, limit 0.5 %)
         xor_reference 0.506 mm³ (limit 241.717) vs OCCT ref 24171.747
         cyl_faces radii [4.0, 6.0] = expected (fillet r=6, edge r=4)
```

Determinism across runs: all three verdict JSONs (bushing, plate,
bracket) compared equal between run 1, run 2 and run 3 after removing
the `timing` key — a scripted JSON compare, exit 0. (OpenSCAD's STL
bytes are not run-to-run identical — vertex ordering varies — so every
gate is order-insensitive and the JSON is rounded to 1e-3.)

## run.py

- `python3 -m py_compile run.py` — exit 0.
- (not done: end-to-end `python3 run.py` — this build sandbox has no
  `sbx` CLI or SBX_API_KEY, so creating agent-next sandboxes from here
  was not possible. The exact command sequence run.py sends to
  `sbx exec` was executed manually against a fresh `git clone --depth 1`
  of the pushed branch — `judge/setup.sh` exit 0, `judge/selftest.sh`
  exit 0 with 11/11 kills, `judge/grade.sh` on all three good cases
  exit 0 — which is the receipt above. The lead runs `run.py` itself
  end-to-end before merge.)

## Deviations

- `media/` (screenshots, diagram) — (not done: this task excludes
  media). CADAM's web UI is consequently not served here either; the
  graded flow is the headless OpenSCAD pipeline (see README).
- REPRODUCE.md (a *different* agent model family reproducing the demo
  from the README prompt) — (not done: no second model available in
  this session; required before merge per `cookbook/DEMO-STANDARD.md`).
- Both receipt runs ran in this same disposable build sandbox (the
  venv wiped between them), not in two separate agent-next sandboxes —
  no `sbx` access here, as above. The sandbox did match the target
  shape (disposable Debian, 2 vCPU, sudo, internet).
- The judge venv lives at `$HOME/.venvs/aicad` inside whichever
  sandbox runs it; nothing outside `cookbook/aicad-cadam/` is written
  by the demo except that venv and apt's own package state.
- `examples/bad/` mutants are regenerated by `selftest.sh` into a
  gitignored directory — they are deliberately not committed.
