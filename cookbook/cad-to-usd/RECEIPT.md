# RECEIPT — cad-to-usd

Real output from a fresh 2 vCPU / 4 GB Debian sandbox (python 3.12.15),
branch `sbx/demo-cad-to-usd-r2` at commit implementing `judge/selftest.sh`
(run 2026-10-15). Two environments run from scratch: the builder sandbox
itself (`~/w`) and a fresh `git clone --depth 1` of the repo at the same
branch (`/tmp/cad2usd-runpy-check`) replaying the exact commands `run.py`
sends to `sbx exec`. Both gave the same verdict and kill rate.

Tool versions recorded by setup (identical in both runs):

```
recorded: 2026-10-15T05:05:38Z by judge/setup.sh
python: Python 3.12.15
usd-convert-cad: 0.3.0
usd-core (pxr): 0.26.8
cadquery-ocp: 7.9.3.1.1
vtk: 9.6.2
converter banner: usage: usd-convert-cad [-h] -i INPUT -o OUTPUT [--global-xforms]
[setup] done
```

## `bash judge/setup.sh`

```
[setup] installing into cad2usd-convert from requirements-convert.txt (sha256-checked)
...
Installing collected packages: usd-convert-cad
Successfully installed usd-convert-cad-0.3.0
[setup] installing into cad2usd-judge from requirements-judge.txt (sha256-checked)
...
Successfully installed cadquery-ocp-7.9.3.1.1 cadquery-ocp-proxy-7.9.3.1.1
contourpy-1.4.0 cycler-0.12.1 fonttools-4.67.0 kiwisolver-1.5.1
matplotlib-3.11.2 numpy-2.5.4 packaging-26.3 pillow-12.3.0 pyparsing-3.3.3
python-dateutil-2.9.0.post0 six-1.17.0 usd-core-26.8 vtk-9.6.2
[setup] done

real    4m0.613s
exit code: 0
```

(Re-run on the existing install is idempotent:
`[setup] cad2usd-convert already installed ...` → 28.5 s, exit 0.)

## `bash judge/selftest.sh`

```
== selftest: known-good artifact ==
known-good: PASS (expected)
== selftest: generating known-bad mutants ==
[mutant] wrong_units      killed_by=stage_meta + bbox_match: metersPerUnit 0.001 -> 1: mm scene read as metres
[mutant] up_axis_y        killed_by=stage_meta: upAxis "Z" -> "Y"
[mutant] axis_swap        killed_by=bbox_match: Y/Z point coordinates swapped on every mesh (geometry, not just metadata)
[mutant] dropped_mesh     killed_by=bbox_match + area_match: largest Mesh prim removed
[mutant] decimated_mesh   killed_by=area_match: half the faces of the largest mesh dropped
[mutant] empty_stage      killed_by=geometry_counts: valid stage, no meshes at all
[mutant] garbage_convert  killed_by=conversion_script: convert.sh feeds a garbage STEP to the converter (exit 1)
[mutant] missing_part     killed_by=file_set: one part file deleted
[mutant] cross_part_copy  killed_by=file_set: one part's output replaced by a copy of another part's
mutant axis_swap: FAIL (expected) -- killed by gate: bbox_match
mutant cross_part_copy: FAIL (expected) -- killed by gate: file_set
mutant decimated_mesh: FAIL (expected) -- killed by gate: area_match
mutant dropped_mesh: FAIL (expected) -- killed by gate: area_match, bbox_match
mutant empty_stage: FAIL (expected) -- killed by gate: area_match, bbox_match, geometry_counts, stage_meta
mutant garbage_convert: FAIL (expected) -- killed by gate: conversion_script
mutant missing_part: FAIL (expected) -- killed by gate: file_set
mutant up_axis_y: FAIL (expected) -- killed by gate: stage_meta
mutant wrong_units: FAIL (expected) -- killed by gate: area_match, bbox_match, stage_meta
== selftest summary ==
known-good: passed
kill rate: 9/9 (100%)
== selftest: determinism (grade twice with --seed 42) ==
determinism: PASS (two --seed 42 runs identical excluding "timing")
selftest: PASS (1172 s)
exit code: 0
```

Every mutant was killed by the gate `judge/mutants.py` predicted for it
(`empty_stage` additionally trips `bbox_match`/`area_match`/`stage_meta`
because a stage with no meshes has nothing to measure).

## `bash judge/grade.sh examples/good --json /tmp/v.json`

```
[grade] artifact: examples/good  seed: 0
[fetch] ... 3 source file(s) verified in .../sources
[grade] file_set: PASS
[grade] conversion_script: PASS
[grade] stage_meta: PASS
[grade] geometry_counts: PASS
[grade] bbox_match: PASS
[grade] area_match: PASS
[grade] verdict: PASS (/tmp/v.json)
exit code: 0
real    4m41.502s
```

Key numbers from the verdict JSON (`/tmp/v.json`):

| part | prims | meshes | triangles | bbox match | area (USD vs oracle, mm²) | rel err |
|---|---|---|---|---|---|---|
| Servo_Futaba_S3003_v6_step | 16 | 4 | 13188 | pass | 10196.6041 vs 10198.5433 | 0.019 % |
| Servo_Futaba_S3003_v6_iges | 16 | 4 | 13292 | pass | 10196.0301 vs 10199.8284 | 0.037 % |
| ShockTowerFront_stp | 23 | 9 | 5015 | pass | 20949.249 vs 20972.9555 | 0.113 % |

(Tolerances: bbox endpoint deltas ≤ 1 % of the oracle extent per axis with a
0.1 mm floor; total area within 3 %: `SPEC.md` gates 4–5.)

```
timing: fetch_sources_s 2.4, file_set_s 0.0, gates_2_5_s 47.3,
        conversion_script_s 228.4, total_s 278.0
```

## Wall times

| step | builder sandbox | fresh clone (run.py sequence) |
|---|---|---|
| setup | 4 min 01 s | 29 s (idempotent re-run; first build seen by setup was the builder's) |
| selftest | 19 min 33 s (1172 s) | 17 min 10 s (1030 s) |
| grade examples/good | 4 min 42 s (282 s) | 2 min 22 s (141 s; same verdict) |

## run.py verification

`python3 -m py_compile run.py` passes. The exact command sequence `run.py`
sends to `sbx exec` (`git clone --depth 1 -b <ref>` → `bash judge/setup.sh`
→ `bash judge/selftest.sh` → `bash judge/grade.sh examples/good --seed 42
--json`) was executed directly in a fresh clone (`/tmp/cad2usd-runpy-check`)
because sandboxes cannot be created from inside this sandbox; clone/setup/
selftest/grade all exited 0 with the numbers above. The lead will run
`run.py` end to end with a real `sbx` key.

## Deviations

- `judge/VERSIONS.txt` is not committed; `setup.sh` instead writes
  `~/.venvs/cad2usd-VERSIONS.txt` on every run (pinned versions are the
  `judge/requirements-*.txt` hash files; the run-time record is printed to
  stdout and captured above). Keeping tool state out of git follows the
  standard's size rule.
- The determinism guarantee is verified over the whole verdict excluding
  `timing` (the standard allows wall-time variation only).
- Media (`media/`) is out of scope for this task by instruction; a later
  task produces it.
