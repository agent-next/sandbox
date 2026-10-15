# RECEIPT — cad-to-usd

Real output from two fresh runs of the demo in a disposable sandbox
(2 vCPU, ~4 GB RAM, Debian, CPython 3.12.15, no GPU). Run 1 is the
working tree at commit `8fbf685` (branch `sbx/demo-cad-to-usd-r3`);
run 2 is a fresh `git clone --depth 1` of that branch with the venvs
wiped first, i.e. the exact sequence `run.py` sends to `sbx exec`
(verified in-sandbox; the lead's end-to-end `run.py` run adds only the
`sbx create`/`sbx kill` wrapper).

Commands (both runs, from `cookbook/cad-to-usd`):

```bash
bash judge/setup.sh
bash judge/selftest.sh
bash judge/grade.sh examples/good --seed 42 --json /tmp/v.json
```

## Tool versions (judge/setup.sh, run 1)

```
recorded: 2026-10-15T06:04:25Z by judge/setup.sh
python: Python 3.12.15
usd-convert-cad: 0.3.0
usd-core (pxr): 0.26.8
cadquery-ocp: 7.9.3.1.1
vtk: 9.6.2
converter banner: usage: usd-convert-cad [-h] -i INPUT -o OUTPUT [--global-xforms]
[setup] done
exit=0
```

Every wheel is installed with `pip --require-hashes` from
`judge/requirements-*.txt` (sha256 pins in the repo). `setup.sh` exit 0
both runs.

## Self-test (judge/selftest.sh)

Run 1 (exit 0, 1164 s wall):

```
known-good: PASS (expected)
mutant wrong_units      FAIL (expected) -- killed by gate: area_match, bbox_match, stage_meta
mutant up_axis_y        FAIL (expected) -- killed by gate: stage_meta
mutant axis_swap        FAIL (expected) -- killed by gate: bbox_match
mutant dropped_mesh     FAIL (expected) -- killed by gate: area_match, bbox_match
mutant decimated_mesh   FAIL (expected) -- killed by gate: area_match
mutant empty_stage      FAIL (expected) -- killed by gate: area_match, bbox_match, geometry_counts, stage_meta
mutant garbage_convert  FAIL (expected) -- killed by gate: conversion_script
mutant missing_part     FAIL (expected) -- killed by gate: file_set
mutant cross_part_copy  FAIL (expected) -- killed by gate: file_set
known-good: passed
kill rate: 9/9 (100%)
determinism: PASS (two --seed 42 runs identical excluding "timing")
selftest: PASS (1164 s)
exit=0
```

Every known-bad mutant is killed by the gate `judge/mutants.py` predicts;
the kill rate is 100 % ≥ the required 90 %. Two grades of the good
artifact with `--seed 42` are byte-identical except the `timing` key.

Run 2 (exit 0, 1122 s): identical gate assignment per mutant, kill rate 9/9
(100 %), determinism PASS. The only self-test difference between runs is
wall time.

## Grade (judge/grade.sh examples/good --seed 42 --json /tmp/v.json)

Run 1 (exit 0, 2m45s wall; `total_s: 162.0` in the verdict timing):

```
[fetch] Servo Futaba S3003 v6.step @ 407bd553ee57668ceb58d81ffd7f4d617dee3dfa
[fetch] Servo Futaba S3003 v6.iges @ 407bd553ee57668ceb58d81ffd7f4d617dee3dfa
[fetch] ShockTowerFront/_ShockTowerFront.stp @ 407bd553ee57668ceb58d81ffd7f4d617dee3dfa
[fetch] 3 source file(s) verified in <work>/sources
[grade] file_set: PASS
[grade] stage_meta: PASS
[grade] geometry_counts: PASS
[grade] bbox_match: PASS
[grade] area_match: PASS
[grade] conversion_script: PASS
[grade] verdict: PASS
```

Key numbers, both runs side by side (mm / mm^2 after unit conversion):

| quantity | run 1 | run 2 |
|---|---|---|
| all_gates_passed | true | true |
| grade wall (timing total_s) | 162.0 | 181.2 |
| servo STEP: prims / meshes / triangles | 16 / 4 / 13188 | 16 / 4 / 13188 |
| servo IGES: prims / meshes / triangles | 16 / 4 / 13292 | 16 / 4 / 13292 |
| shock tower: prims / meshes / triangles | 23 / 9 / 5015 | 23 / 9 / 5015 |
| servo STEP area, USD vs oracle (mm²) | 10196.6041 vs 10198.5433 (rel 0.019 %) | same |
| servo IGES area, USD vs oracle (mm²) | 10196.0301 vs 10199.8284 (rel 0.037 %) | same |
| shock tower area, USD vs oracle (mm²) | 20949.249 vs 20972.9555 (rel 0.113 %) | same |
| bbox endpoint deltas (all parts, all axes) | max 0.3 mm (shock tower Y, tol 0.586 mm); all other axes 0.0 mm | same |

All bbox/area numbers are byte-identical across the two runs — the
geometry pipeline is deterministic. Full verdict JSON from run 1
(`/tmp/v.json`, `--seed 42`):

<details>
<summary>verdict JSON (run 1, /tmp/v.json, --seed 42; run 2 identical except timing)</summary>

```json
{
  "all_gates_passed": true,
  "demo": "cad-to-usd",
  "gates": {
    "area_match": {
      "detail": {
        "Servo_Futaba_S3003_v6_iges": {
          "area_oracle_mm2": 10199.8284,
          "area_usd_mm2": 10196.0301,
          "pass": true,
          "rel_error": 0.000372
        },
        "Servo_Futaba_S3003_v6_step": {
          "area_oracle_mm2": 10198.5433,
          "area_usd_mm2": 10196.6041,
          "pass": true,
          "rel_error": 0.00019
        },
        "ShockTowerFront_stp": {
          "area_oracle_mm2": 20972.9555,
          "area_usd_mm2": 20949.249,
          "pass": true,
          "rel_error": 0.00113
        }
      },
      "passed": true
    },
    "bbox_match": {
      "detail": {
        "Servo_Futaba_S3003_v6_iges": [
          {
            "axis": "x",
            "delta_max": 4e-06,
            "delta_min": 0.0,
            "oracle_max": 28.786025,
            "oracle_min": -27.25,
            "pass": true,
            "tol_mm": 0.56036,
            "usd_max": 28.786021,
            "usd_min": -27.25
          },
          {
            "axis": "y",
            "delta_max": 0.0,
            "delta_min": 0.0,
            "oracle_max": 47.8,
            "oracle_min": -0.0,
            "pass": true,
            "tol_mm": 0.478,
            "usd_max": 47.8,
            "usd_min": 0.0
          },
          {
            "axis": "z",
            "delta_max": 4e-06,
            "delta_min": 4e-06,
            "oracle_max": 18.25,
            "oracle_min": -18.25,
            "pass": true,
            "tol_mm": 0.365,
            "usd_max": 18.249996,
            "usd_min": -18.249996
          }
        ],
        "Servo_Futaba_S3003_v6_step": [
          {
            "axis": "x",
            "delta_max": 4e-06,
            "delta_min": 0.0,
            "oracle_max": 28.786025,
            "oracle_min": -27.25,
            "pass": true,
            "tol_mm": 0.56036,
            "usd_max": 28.786021,
            "usd_min": -27.25
          },
          {
            "axis": "y",
            "delta_max": 0.0,
            "delta_min": 0.0,
            "oracle_max": 47.8,
            "oracle_min": -0.0,
            "pass": true,
            "tol_mm": 0.478,
            "usd_max": 47.8,
            "usd_min": 0.0
          },
          {
            "axis": "z",
            "delta_max": 0.0,
            "delta_min": 4e-06,
            "oracle_max": 18.25,
            "oracle_min": -18.25,
            "pass": true,
            "tol_mm": 0.365,
            "usd_max": 18.25,
            "usd_min": -18.249996
          }
        ],
        "ShockTowerFront_stp": [
          {
            "axis": "x",
            "delta_max": 4e-06,
            "delta_min": 4e-06,
            "oracle_max": 192.208042,
            "oracle_min": 122.791958,
            "pass": true,
            "tol_mm": 0.694161,
            "usd_max": 192.208038,
            "usd_min": 122.791962
          },
          {
            "axis": "y",
            "delta_max": 0.300196,
            "delta_min": 0.300196,
            "oracle_max": 29.300196,
            "oracle_min": -29.300196,
            "pass": true,
            "tol_mm": 0.586004,
            "usd_max": 29.0,
            "usd_min": -29.0
          },
          {
            "axis": "z",
            "delta_max": 0.0,
            "delta_min": 0.0,
            "oracle_max": 67.0,
            "oracle_min": 30.0,
            "pass": true,
            "tol_mm": 0.37,
            "usd_max": 67.0,
            "usd_min": 30.0
          }
        ]
      },
      "passed": true
    },
    "conversion_script": {
      "detail": {
        "error": null,
        "measures": {
          "Servo_Futaba_S3003_v6_iges": {
            "area": 10196.030067,
            "bbox_max": [
              28.786021,
              47.8,
              18.249996
            ],
            "bbox_min": [
              -27.25,
              0.0,
              -18.249996
            ],
            "default_prim": "/Servo_Futaba_S3003_v6_iges",
            "meshes": 4,
            "meters_per_unit": 0.001,
            "prims": 16,
            "triangles": 13292,
            "up_axis": "Z"
          },
          "Servo_Futaba_S3003_v6_step": {
            "area": 10196.604123,
            "bbox_max": [
              28.786021,
              47.8,
              18.25
            ],
            "bbox_min": [
              -27.25,
              0.0,
              -18.249996
            ],
            "default_prim": "/Servo_Futaba_S3003_v6_step",
            "meshes": 4,
            "meters_per_unit": 0.001,
            "prims": 16,
            "triangles": 13188,
            "up_axis": "Z"
          },
          "ShockTowerFront_stp": {
            "area": 20949.248991,
            "bbox_max": [
              192.208038,
              29.0,
              67.0
            ],
            "bbox_min": [
              122.791962,
              -29.0,
              30.0
            ],
            "default_prim": "/ShockTowerFront_stp",
            "meshes": 9,
            "meters_per_unit": 0.001,
            "prims": 23,
            "triangles": 5015,
            "up_axis": "Z"
          }
        },
        "per_part": {
          "Servo_Futaba_S3003_v6_iges": {
            "error": null,
            "ok": true
          },
          "Servo_Futaba_S3003_v6_step": {
            "error": null,
            "ok": true
          },
          "ShockTowerFront_stp": {
            "error": null,
            "ok": true
          }
        },
        "reproduced": true
      },
      "passed": true
    },
    "file_set": {
      "detail": {
        "pairwise_distinct": true,
        "parts": {
          "Servo_Futaba_S3003_v6_iges": {
            "bytes": 969145,
            "present": true,
            "sha256": "fc2f8f0cfcc1f9446ad8482b5a52140561313bc179017ec35408024483bf75a5"
          },
          "Servo_Futaba_S3003_v6_step": {
            "bytes": 871844,
            "present": true,
            "sha256": "b1ec164a55761880b013ac4c99710996c75ebcc08b3c6ada6048adeecd5d7264"
          },
          "ShockTowerFront_stp": {
            "bytes": 344509,
            "present": true,
            "sha256": "97ded144a8ebd5671feff1369c4fb806610def69e034b66fdf3b50ecfacd3bcb"
          }
        }
      },
      "passed": true
    },
    "geometry_counts": {
      "detail": {
        "Servo_Futaba_S3003_v6_iges": {
          "meshes": 4,
          "prims": 16,
          "triangles": 13292
        },
        "Servo_Futaba_S3003_v6_step": {
          "meshes": 4,
          "prims": 16,
          "triangles": 13188
        },
        "ShockTowerFront_stp": {
          "meshes": 9,
          "prims": 23,
          "triangles": 5015
        }
      },
      "passed": true
    },
    "stage_meta": {
      "detail": {
        "Servo_Futaba_S3003_v6_iges": {
          "default_prim": "/Servo_Futaba_S3003_v6_iges",
          "meters_per_unit": 0.001,
          "up_axis": "Z"
        },
        "Servo_Futaba_S3003_v6_step": {
          "default_prim": "/Servo_Futaba_S3003_v6_step",
          "meters_per_unit": 0.001,
          "up_axis": "Z"
        },
        "ShockTowerFront_stp": {
          "default_prim": "/ShockTowerFront_stp",
          "meters_per_unit": 0.001,
          "up_axis": "Z"
        }
      },
      "passed": true
    }
  },
  "measures": {
    "Servo_Futaba_S3003_v6_iges": {
      "area": 10196.030067,
      "bbox_max": [
        28.786021,
        47.8,
        18.249996
      ],
      "bbox_min": [
        -27.25,
        0.0,
        -18.249996
      ],
      "default_prim": "/Servo_Futaba_S3003_v6_iges",
      "meshes": 4,
      "meters_per_unit": 0.001,
      "prims": 16,
      "triangles": 13292,
      "up_axis": "Z"
    },
    "Servo_Futaba_S3003_v6_step": {
      "area": 10196.604123,
      "bbox_max": [
        28.786021,
        47.8,
        18.25
      ],
      "bbox_min": [
        -27.25,
        0.0,
        -18.249996
      ],
      "default_prim": "/Servo_Futaba_S3003_v6_step",
      "meshes": 4,
      "meters_per_unit": 0.001,
      "prims": 16,
      "triangles": 13188,
      "up_axis": "Z"
    },
    "ShockTowerFront_stp": {
      "area": 20949.248991,
      "bbox_max": [
        192.208038,
        29.0,
        67.0
      ],
      "bbox_min": [
        122.791962,
        -29.0,
        30.0
      ],
      "default_prim": "/ShockTowerFront_stp",
      "meshes": 9,
      "meters_per_unit": 0.001,
      "prims": 23,
      "triangles": 5015,
      "up_axis": "Z"
    }
  },
  "per_part": {
    "Servo_Futaba_S3003_v6_iges": {
      "error": null,
      "ok": true
    },
    "Servo_Futaba_S3003_v6_step": {
      "error": null,
      "ok": true
    },
    "ShockTowerFront_stp": {
      "error": null,
      "ok": true
    }
  },
  "seed": "42",
  "timing": {
    "conversion_script_s": 127.8,
    "fetch_sources_s": 1.6,
    "file_set_s": 0.0,
    "gates_2_5_s": 32.6,
    "total_s": 162.0
  }
}```
</details>

## Wall times (2 vCPU / 4 GB sandbox)

| step | run 1 | run 2 |
|---|---|---|
| `judge/setup.sh` (two venvs, ~630 MB sha256-checked wheels) | 3m27s | 2m34s |
| `judge/selftest.sh` (good ×3 grades + 9 mutants + determinism) | 1164 s | 1122 s |
| `judge/grade.sh examples/good` (fetch + oracle + re-conversion) | 2m45s (total_s 162.0) | 3m04s (total_s 181.2) |

## Deviations

- `run.py` itself was **not** run end-to-end with `sbx create` from inside
  this sandbox: an in-sandbox agent cannot create agent-next sandboxes
  (no `SBX_API_KEY` here). It was verified with `python3 -m py_compile`
  and by running its exact in-sandbox command sequence (`git clone
  --depth 1 -b <ref> … && bash judge/setup.sh && bash judge/selftest.sh
  && bash judge/grade.sh examples/good --seed 42`) directly against a
  fresh clone of the pushed branch — that sequence is run 2 above and
  exits 0 at every step. The lead runs `run.py` end to end.
- Only media files are missing relative to the layout table in
  `cookbook/DEMO-STANDARD.md` (`media/`, `REPRODUCE.md`): media is a
  later task, and independent reproduction happens before merge per the
  standard.
- The two verdict JSONs were compared programmatically: byte-identical
  after removing the `timing` key (both 8984 bytes).
