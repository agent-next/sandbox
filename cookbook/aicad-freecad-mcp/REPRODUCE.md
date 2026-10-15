# REPRODUCE — aicad-freecad-mcp

**Reproducer:** SWE-2 High (Cognition Devin), a different agent — not the
builder. Recorded 2026-10-15.

**Source:** branch `sbx/v0-aicad-freecad-mcp` at `0f48f78`, checked out in
place. Followed only the local steps README.md gives: `judge/setup.sh`,
`judge/selftest.sh`, and `judge/grade.sh` on `examples/good/` with `--json`.
No files were edited during the run.

**Environment:** fresh Debian 12 sandbox, 2 vCPU, ~4 GB RAM, Python 3.12.15,
nothing CAD-related preinstalled. Notably `xvfb-run` was present but `xauth`
was missing — the exact image gap documented in RECEIPT.md — and the current
`judge/setup.sh` installed it via apt as designed.

## Commands, exit codes, wall times

Run from the repository root on the checked-out branch:

| command | exit | wall |
|---|---|---|
| `bash cookbook/aicad-freecad-mcp/judge/setup.sh` | 0 | 217 s (cold: judge venv, 809 MB AppImage download + sha256 verify + extract, freecad-mcp venv, xvfb + **xauth** apt install) |
| `bash cookbook/aicad-freecad-mcp/judge/selftest.sh` | 0 | 169 s |
| `bash cookbook/aicad-freecad-mcp/judge/grade.sh examples/good/bushing --json /tmp/repro_verdict_bushing.json` | 0 | 17 s |
| `bash cookbook/aicad-freecad-mcp/judge/grade.sh examples/good/plate --json /tmp/repro_verdict_plate.json` | 0 | 12 s |
| `bash cookbook/aicad-freecad-mcp/judge/grade.sh examples/good/bracket --json /tmp/repro_verdict_bracket.json` | 0 | 9 s |

setup.sh tail:

```
[setup] installing xvfb + xauth (FreeCAD GUI needs an X server for the RPC addon)
[setup] versions recorded in judge/VERSIONS.txt
[setup] setup complete
SETUP_EXIT=0 wall=217s
```

selftest.sh output:

```
== selftest: known-good artifacts ==
  good/bushing PASS (volume 42625.13 mm^3)
  good/plate PASS (volume 71505.92 mm^3)
  good/bracket PASS (volume 61853.98 mm^3)
== selftest: known-bad mutants ==
  bracket_no_fillet killed by: brep,features,stl_topology,xor_reference
  bushing_bore_22 killed by: brep,features,stl_topology,xor_reference
  bushing_stl_flip killed by: stl_topology
  bushing_stl_gap killed by: stl_topology
  plate_hole_count_5 killed by: features,xor_reference
  plate_hole_drift killed by: features
  plate_scale_25_4 killed by: bbox,brep,stl_topology
kill rate: 7/7 = 100%
== selftest: determinism ==
  two grades identical (excluding timing)
  judge/ unchanged
selftest OK
SELFTEST_EXIT=0 wall=169s
```

## Key numbers vs RECEIPT.md

All three verdict JSONs are **identical** to the committed
`media/data/good_*.json` apart from the `timing` block, per-gate `_s`
fields, and the `artifact` path field — the judge is deterministic, so
matching is exact, well inside every SPEC.md gate tolerance.

| item | RECEIPT.md | this run | result |
|---|---|---|---|
| selftest exit / kill rate | 0 / 7/7 = 100 % | 0 / 7/7 = 100 % | match |
| killed-by gate sets per mutant | (7 lines, RECEIPT Run 2) | identical lines, verbatim | match |
| bushing STEP volume (rel err ≤ 0.5 %) | 42625.1291 mm³, rel 0.0 | 42625.1291 mm³, rel 0.0 | match |
| plate STEP volume | 71505.9189 mm³, rel 0.0 | 71505.9189 mm³, rel 0.0 | match |
| bracket STEP volume | 61853.9828 mm³, rel 0.0 | 61853.9828 mm³, rel 0.0 | match |
| xor fractions (limit ≤ 1 %) | 3.61e-4 / 1.37e-4 / 1.7e-4 | 3.61e-4 / 1.37e-4 / 1.7e-4 | match |
| bushing min wall (limit ≥ 1.2 mm) | 7.9974 mm (2400 samples, seed 20261015) | 7.9974 mm (same seed) | match |
| plate min wall | 6.94 mm (rim sample) | 6.9399 mm | match |
| bracket min wall | 8.06 mm | 8.0604 mm | match |
| plate features | 6 holes at ρ = 35.000, 0/60/…/300° | same | match |
| plate DXF | 0 audit errors, 7 CIRCLEs, 100 × 80 centred | same | match |
| bracket features | R5 ×2 + R6 ×2 + R8 fillet | same | match |
| determinism | two same-seed grades identical excl. `timing` | same, checked by selftest | match |
| tool versions (VERSIONS.txt) | FreeCAD 1.0.1 r39285, trimesh 4.6.6, manifold3d 3.1.1, cadquery 2.5.2, ezdxf 1.4.0, numpy 2.2.6, OCP 7.7.2, freecad-mcp 78bf023, addon 0.1.27 | identical line for line | match |

Wall times differ as expected (different sandbox, SPEC.md treats timing as
non-deterministic): setup 277 s → 217 s, selftest 143 s → 169 s,
grades 19.0 / 8.4 / 10.7 s → 17 / 12 / 9 s.

## Not reproduced / notes

- `run.py` end-to-end (`sbx create → … → sbx kill`) was not exercised: no
  `sbx` CLI or API key inside this sandbox — the same limitation RECEIPT.md
  records. Only README.md's local steps were run, per this task.
- `judge/setup.sh` rewrote `judge/VERSIONS.txt` with a new `recorded:`
  timestamp and otherwise identical content (restored after the run).
- `python3 cookbook/tools/video_gate.py cookbook/aicad-freecad-mcp/media/demo.mp4`
  re-run on the checked-in video: `passed: true`, all 16 checks green
  (1920×1080 @ 30 fps, h264 yuv420p, 33.4 s, 3.33 MiB, faststart,
  cuts 1.8/10 s, motion 0.3305, static end card), exit 0.
- Nothing failed; no doc or script fixes were needed for the reproduction.
