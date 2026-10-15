# RECEIPT — `cookbook/climate-glacier-model/`

Real command output, pasted as produced. The blocks below are the verbatim
log of **two fresh runs** of the one-command entry point, each in its own
disposable sandbox with no venv present (`rm -rf ~/glacier-venv` before the
run), so `judge/setup.sh` installed from nothing both times. Debian 12
(bookworm), glibc 2.36, 2 vCPU, ~4 GB RAM.

Command (from the repo root, on this branch):

```bash
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
export SBX_API_KEY=<your key>
python3 cookbook/climate-glacier-model/run.py --ref sbx/demo-climate-glacier-model-f4
```

`judge/setup.sh` installs only Python wheels into `~/glacier-venv`; no
system package is touched, so "fresh" means exactly "no venv".

## A confirming run at the final code

The two runs below were made after the timeout fix (commit `31b2677`). Later
commits changed only how `run.py` reports (`e1a3204`: echo a step's output
even when it fails) and documentation (`0ab3c9d`, `bb6f021`, `8f2a786`);
neither touches the judge or the artifact. A fresh run at the final HEAD
(`8f2a786`) reproduced the same result exactly:

```text
run: [   2.7s] sbx create --timeout-min 30 -> exit 0
run: sandbox 01a14000-a18b-7cf3-9baf-1136c7201148
run: [   5.6s] git clone -> exit 0
run: [  31.3s] judge/setup.sh -> exit 0
run: [  86.0s] judge/selftest.sh -> exit 0
selftest: known-good PASSED all gates
selftest: kill rate 13/13 = 100%
selftest: OK
run: [   9.0s] judge/grade.sh examples/good -> exit 0
run: SUMMARY passed=True zero_melt_worst=0.0 rows=303 warm_2p0:V100=2.832/t50=96.0076481835564 warm_2p4:V100=2.04288/t50=81.60555821753714 warm_2p8:V100=1.20192/t50=71.40555289612254
run: killed and confirmed gone: 01a14000-a18b-7cf3-9baf-1136c7201148
```

## Two fresh runs, side by side

| step | run 1 exit / s | run 2 exit / s |
|---|---|---|
| `sbx create --timeout-min 30` | 0 / 4.1 | 0 / 3.0 |
| `git clone --depth 1 -b <ref>` | 0 / 5.2 | 0 / 4.7 |
| `judge/setup.sh` (fresh venv) | 0 / 35.5 | 0 / 31.6 |
| `judge/selftest.sh` (good + 13 mutants + determinism) | 0 / 83.7 | 0 / 82.6 |
| `judge/grade.sh examples/good` | 0 / 10.8 | 0 / 11.1 |
| `sbx kill` + confirmed gone | 0 | 0 |
| **`run.py` total exit** | **0** | **0** |

| key number | run 1 | run 2 |
|---|---|---|
| sandbox id (created, then killed) | `01a13fdb-…ace13` | `01a13fdd-…58e1f` |
| kill rate | **13/13 = 100 %** | **13/13 = 100 %** |
| `verdict["passed"]` | `true` | `true` |
| `warm_2p0` crossing year | 96.0076481835564 | 96.0076481835564 |
| `warm_2p4` crossing year | 81.60555821753714 | 81.60555821753714 |
| `warm_2p8` crossing year | 71.40555289612254 | 71.40555289612254 |
| `warm_2p0` `V(100)` km³ | 2.832 | 2.832 |
| `warm_2p4` `V(100)` km³ | 2.04288 | 2.04288 |
| `warm_2p8` `V(100)` km³ | 1.20192 | 1.20192 |
| zero-melt worst deviation | 0.0 (tol 1e-9) | 0.0 (tol 1e-9) |
| grade `total_seconds` (in `timing`) | 7.37 | 7.29 |

Every graded number is identical between the two runs. The only differences
are the sandbox ids and the wall-time fields under `timing` — exactly what
SPEC.md allows to differ between same-seed runs.

## Run 1 — verbatim output

```text
run: [   4.1s] sbx create --timeout-min 30 -> exit 0
run: sandbox 01a13fdb-66b9-7452-a8c7-0859e41ace13
run: [   5.2s] git clone -> exit 0
run: [  35.5s] judge/setup.sh -> exit 0
run: [  83.7s] judge/selftest.sh -> exit 0
selftest: grading known-good /home/user/glacier-demo-repo/cookbook/climate-glacier-model/examples/good
selftest: known-good PASSED all gates
mutants: tau-doubled/model.py  [expect shape/final_volume]  edit: 'TAU = 10.0        # yr, length response time' -> 'TAU = 20.0        # yr, length response time'
mutants: taper-dropped/model.py  [expect shape]  edit: 'H = H0 - DH * X                     # ice thickness per cell' -> 'H = H0 * (X * 0.0 + 1.0)            # ice thickness per cell'
mutants: anomaly-doubled/model.py  [expect final_volume]  edit: 'anomaly = amp * (year / YEARS)' -> 'anomaly = amp * 2.0 * (year / YEARS)'
mutants: crossing-year-fabricated-in-json/model.py  [expect crossing]  edit: '"year": crossing_year(range(YEARS + 1), volumes),' -> '"year": crossing_year(range(YEARS + 1), volumes)\n            if args.zero_melt else 50.0,'
mutants: zero-melt-ignored/model.py  [expect zero_melt]  edit: 'amp = 0.0 if zero_melt else a2' -> 'amp = a2'
mutants: volume-in-cubic-metres-over-km/model.py  [expect final_volume]  edit: 'return float(W * H[X < length].sum() * DX / 1e9)' -> 'return float(W * H[X < length].sum() * DX / 1e6)'
mutants: mask-frozen-at-year-zero/model.py  [expect crossing]  edit: 'return float(W * H[X < length].sum() * DX / 1e9)' -> 'return float(W * H[X < L0].sum() * DX / 1e9)'
mutants: row-count-off-by-one/model.py  [expect artifact]  edit: 'for year in range(YEARS):' -> 'for year in range(YEARS + 1):'
mutants: figure-below-minimum-width/model.py  [expect figure]  edit: 'fig, ax = plt.subplots(figsize=(9.0, 5.5), dpi=200)' -> 'fig, ax = plt.subplots(figsize=(3.0, 2.0), dpi=200)'
mutants: nondeterministic-tiny-perturbation/model.py  [expect determinism]  edit: 'volumes = [volume_km3(length) for length in lengths]' -> "volumes = [volume_km3(length) *\n                   (1.0 + 1e-12 * __import__('random').randint(0, 10**9))\n                   for length in lengths]"
mutants: figure-not-written/model.py  [expect artifact]  edit: -'write_figure(os.path.join(args.out, "retreat.png"), series)'
mutants: import-outside-allow-list/model.py  [expect artifact]  edit: +'import subprocess  # not on the allow-list'
mutants: writes-outside-out-dir/model.py  [expect artifact]  edit: +'open("volumes.csv.bak", "w").write("scratch\\n")'
mutants: wrote 13 mutants to /tmp/tmp.KKMinLwiix/mutants
selftest: killed    anomaly-doubled (gate: crossing)
selftest: killed    crossing-year-fabricated-in-json (gate: crossing)
selftest: killed    figure-below-minimum-width (gate: figure)
selftest: killed    figure-not-written (gate: artifact)
selftest: killed    import-outside-allow-list (gate: artifact)
selftest: killed    mask-frozen-at-year-zero (gate: crossing)
selftest: killed    nondeterministic-tiny-perturbation (gate: determinism)
selftest: killed    row-count-off-by-one (gate: artifact)
selftest: killed    taper-dropped (gate: crossing)
selftest: killed    tau-doubled (gate: crossing)
selftest: killed    volume-in-cubic-metres-over-km (gate: final_volume)
selftest: killed    writes-outside-out-dir (gate: artifact)
selftest: killed    zero-melt-ignored (gate: zero_melt)
selftest: kill rate 13/13 = 100%
selftest: determinism OK (two --seed 1 runs identical but for timing)
selftest: OK
run: [  10.8s] judge/grade.sh examples/good -> exit 0
{
  "artifact": "examples/good",
  "gates": {
    "_meta": {
      "artifact": "examples/good",
      "passed": true,
      "python": "/home/user/glacier-venv/bin/python",
      "seed": 20261015,
      "spec_constants": {
        "L0": 15000.0,
        "V0_continuum_km3": 6.0,
        "V0_mask_km3": 6.0
      }
    },
    "artifact": {
      "passed": true,
      "rows": 303
    },
    "crossing": {
      "passed": true,
      "scenarios": {
        "warm_2p0": {
          "csv_deviation_years": 0.0006622751760403389,
          "csv_year": 96.0076481835564,
          "deviation_years": 0.0006622751760403389,
          "passed": true,
          "reference_year": 96.00698590838036,
          "reported_year": 96.0076481835564
        },
        "warm_2p4": {
          "csv_deviation_years": -0.06465542862589757,
          "csv_year": 81.60555821753714,
          "deviation_years": -0.06465542862589757,
          "passed": true,
          "reference_year": 81.67021364616303,
          "reported_year": 81.60555821753714
        },
        "warm_2p8": {
          "csv_deviation_years": -0.02058507876472504,
          "csv_year": 71.40555289612254,
          "deviation_years": -0.02058507876472504,
          "passed": true,
          "reference_year": 71.42613797488727,
          "reported_year": 71.40555289612254
        }
      },
      "tolerance_years": 3.0
    },
    "determinism": {
      "passed": true,
      "reason": null
    },
    "figure": {
      "bytes": 158627,
      "dpi": 200.0,
      "height_px": 1100,
      "legend": [
        "warm_2p0",
        "warm_2p4",
        "warm_2p8"
      ],
      "note": "the judge checks the PNG header and run.json, not the pixels: it does not OCR the plot",
      "passed": true,
      "width_px": 1800
    },
    "final_volume": {
      "passed": true,
      "scenarios": {
        "warm_2p0": {
          "measured_km3": 2.832,
          "passed": true,
          "reference_km3": 2.8319807504132917,
          "relative_deviation": 6.797216649644164e-06
        },
        "warm_2p4": {
          "measured_km3": 2.04288,
          "passed": true,
          "reference_km3": 2.0428553314704203,
          "relative_deviation": 1.2075514697235438e-05
        },
        "warm_2p8": {
          "measured_km3": 1.20192,
          "passed": true,
          "reference_km3": 1.201889389519038,
          "relative_deviation": 2.546863399339138e-05
        }
      },
      "tolerance_relative": 0.02
    },
    "shape": {
      "passed": true,
      "scenarios": {
        "warm_2p0": {
          "increases_at_years": [],
          "mask_cells": 240,
          "passed": true,
          "reference_cells": 240,
          "worst_relative_deviation": 0.0015196623405686668,
          "worst_year": 9
        },
        "warm_2p4": {
          "increases_at_years": [],
          "mask_cells": 168,
          "passed": true,
          "reference_cells": 168,
          "worst_relative_deviation": 0.0021006721855688177,
          "worst_year": 98
        },
        "warm_2p8": {
          "increases_at_years": [],
          "mask_cells": 96,
          "passed": true,
          "reference_cells": 96,
          "worst_relative_deviation": 0.0038029067127054884,
          "worst_year": 99
        }
      },
      "tolerance_relative": 0.02
    },
    "zero_melt": {
      "passed": true,
      "reported_crossings": {},
      "tolerance_relative": 1e-09,
      "worst_at": null,
      "worst_relative_deviation": 0.0
    }
  },
  "passed": true,
  "seed": 20261015,
  "timing": {
    "first_run_seconds": 2.65,
    "second_run_seconds": 2.79,
    "total_seconds": 7.37,
    "zero_melt_seconds": 1.89
  }
}
run: SUMMARY passed=True zero_melt_worst=0.0 rows=303 warm_2p0:V100=2.832/t50=96.0076481835564 warm_2p4:V100=2.04288/t50=81.60555821753714 warm_2p8:V100=1.20192/t50=71.40555289612254
run: killed and confirmed gone: 01a13fdb-66b9-7452-a8c7-0859e41ace13
```

## Run 2 — verbatim output

Second fresh sandbox, `~/glacier-venv` removed again before the run. The
verdict JSON is byte-identical to run 1 except the four `timing` fields; the
lines below are as produced (the judge's own `selftest:`/`mutants:` lines are
identical to run 1 and are abbreviated here with `…` only where they repeat
verbatim — the verdict and the summary line are complete).

```text
run: [   3.0s] sbx create --timeout-min 30 -> exit 0
run: sandbox 01a13fdd-f53b-7611-9704-d1f2d8a58e1f
run: [   4.7s] git clone -> exit 0
run: [  31.6s] judge/setup.sh -> exit 0
run: [  82.6s] judge/selftest.sh -> exit 0
selftest: grading known-good /home/user/glacier-demo-repo/cookbook/climate-glacier-model/examples/good
selftest: known-good PASSED all gates
…
selftest: killed    anomaly-doubled (gate: crossing)
selftest: killed    crossing-year-fabricated-in-json (gate: crossing)
selftest: killed    figure-below-minimum-width (gate: figure)
selftest: killed    figure-not-written (gate: artifact)
selftest: killed    import-outside-allow-list (gate: artifact)
selftest: killed    mask-frozen-at-year-zero (gate: crossing)
selftest: killed    nondeterministic-tiny-perturbation (gate: determinism)
selftest: killed    row-count-off-by-one (gate: artifact)
selftest: killed    taper-dropped (gate: crossing)
selftest: killed    tau-doubled (gate: crossing)
selftest: killed    volume-in-cubic-metres-over-km (gate: final_volume)
selftest: killed    writes-outside-out-dir (gate: artifact)
selftest: killed    zero-melt-ignored (gate: zero_melt)
selftest: kill rate 13/13 = 100%
selftest: determinism OK (two --seed 1 runs identical but for timing)
selftest: OK
run: [  11.1s] judge/grade.sh examples/good -> exit 0
{
  "artifact": "examples/good",
  "gates": {
    "_meta": {
      "artifact": "examples/good",
      "passed": true,
      "python": "/home/user/glacier-venv/bin/python",
      "seed": 20261015,
      "spec_constants": {
        "L0": 15000.0,
        "V0_continuum_km3": 6.0,
        "V0_mask_km3": 6.0
      }
    },
    "artifact": {
      "passed": true,
      "rows": 303
    },
    "crossing": {
      "passed": true,
      "scenarios": {
        "warm_2p0": {
          "csv_deviation_years": 0.0006622751760403389,
          "csv_year": 96.0076481835564,
          "deviation_years": 0.0006622751760403389,
          "passed": true,
          "reference_year": 96.00698590838036,
          "reported_year": 96.0076481835564
        },
        "warm_2p4": {
          "csv_deviation_years": -0.06465542862589757,
          "csv_year": 81.60555821753714,
          "deviation_years": -0.06465542862589757,
          "passed": true,
          "reference_year": 81.67021364616303,
          "reported_year": 81.60555821753714
        },
        "warm_2p8": {
          "csv_deviation_years": -0.02058507876472504,
          "csv_year": 71.40555289612254,
          "deviation_years": -0.02058507876472504,
          "passed": true,
          "reference_year": 71.42613797488727,
          "reported_year": 71.40555289612254
        }
      },
      "tolerance_years": 3.0
    },
    "determinism": {
      "passed": true,
      "reason": null
    },
    "figure": {
      "bytes": 158627,
      "dpi": 200.0,
      "height_px": 1100,
      "legend": [
        "warm_2p0",
        "warm_2p4",
        "warm_2p8"
      ],
      "note": "the judge checks the PNG header and run.json, not the pixels: it does not OCR the plot",
      "passed": true,
      "width_px": 1800
    },
    "final_volume": {
      "passed": true,
      "scenarios": {
        "warm_2p0": {
          "measured_km3": 2.832,
          "passed": true,
          "reference_km3": 2.8319807504132917,
          "relative_deviation": 6.797216649644164e-06
        },
        "warm_2p4": {
          "measured_km3": 2.04288,
          "passed": true,
          "reference_km3": 2.0428553314704203,
          "relative_deviation": 1.2075514697235438e-05
        },
        "warm_2p8": {
          "measured_km3": 1.20192,
          "passed": true,
          "reference_km3": 1.201889389519038,
          "relative_deviation": 2.546863399339138e-05
        }
      },
      "tolerance_relative": 0.02
    },
    "shape": {
      "passed": true,
      "scenarios": {
        "warm_2p0": {
          "increases_at_years": [],
          "mask_cells": 240,
          "passed": true,
          "reference_cells": 240,
          "worst_relative_deviation": 0.0015196623405686668,
          "worst_year": 9
        },
        "warm_2p4": {
          "increases_at_years": [],
          "mask_cells": 168,
          "passed": true,
          "reference_cells": 168,
          "worst_relative_deviation": 0.0021006721855688177,
          "worst_year": 98
        },
        "warm_2p8": {
          "increases_at_years": [],
          "mask_cells": 96,
          "passed": true,
          "reference_cells": 96,
          "worst_relative_deviation": 0.0038029067127054884,
          "worst_year": 99
        }
      },
      "tolerance_relative": 0.02
    },
    "zero_melt": {
      "passed": true,
      "reported_crossings": {},
      "tolerance_relative": 1e-09,
      "worst_at": null,
      "worst_relative_deviation": 0.0
    }
  },
  "passed": true,
  "seed": 20261015,
  "timing": {
    "first_run_seconds": 2.41,
    "second_run_seconds": 2.86,
    "total_seconds": 7.29,
    "zero_melt_seconds": 1.99
  }
}
run: SUMMARY passed=True zero_melt_worst=0.0 rows=303 warm_2p0:V100=2.832/t50=96.0076481835564 warm_2p4:V100=2.04288/t50=81.60555821753714 warm_2p8:V100=1.20192/t50=71.40555289612254
run: killed and confirmed gone: 01a13fdd-f53b-7611-9704-d1f2d8a58e1f
```

**Kill rate 13/13 = 100 %** (requirement ≥ 90 %, ≥ 5 known-bad). Kills span
`artifact` (×4), `crossing` (×4), `determinism`, `final_volume`, `figure`
and `zero_melt`. The two lines after the kill rate are the determinism check:
two `grade.sh --seed 1` runs are identical but for the `timing` key.

## What the judge actually measured

- **Analytic oracle**: crossing years are +0.0007 / -0.0647 / -0.0206 yr from
  the closed-form roots (tolerance ±3 yr) — the interpolation and cell-mask
  discretisation, not a fit.
- **Negative control**: with `--zero-melt` the worst deviation from `V(0)`
  over all 303 rows is exactly **0.0** (tolerance 1e-9 relative), and no
  scenario reports a crossing.
- **Mask consistency**: the CSV volumes invert to 240 / 168 / 96 ice cells,
  matching the analytic length to the cell.
- **Shape**: worst deviation from the analytic volume across all years is
  0.15 % / 0.21 % / 0.38 % (tolerance 2 %); no scenario's volume rises.

## Deviations

- **Independent reproduction is complete.** A different agent, following
  only `README.md` in a fresh sandbox, reproduced every graded number exactly
  (13/13 kill rate, identical crossing years and `V(100)` values,
  `verdict["passed"] = true`); its numbers and the side-by-side comparison are
  in `REPRODUCE.md`. *(done)*
- **Wall times vary with machine load.** `setup.sh` was 63–107 s across
  earlier fresh-venv runs and 31.6–35.5 s in the two runs above; `selftest.sh`
  206–239 s earlier and 82.6–83.7 s above. No graded number varied at all —
  the verdict does not depend on wall time, which is why the `timing` key is
  excluded from the determinism comparison.
- **`run.py` step timeout.** The local subprocess timeout is the sandbox-side
  `--timeout` plus a 60 s buffer. An earlier revision did not forward the
  per-step timeout, so the ~84 s self-test step was killed at the default
  120 s; that is fixed on this branch (commit `31b2677`).
- **`judge/VERSIONS.txt` is git-ignored** (it records what `setup.sh`
  actually installed, which differs per host); the pins live in
  `judge/requirements.txt`. The content `setup.sh` writes is:

```text
# climate-glacier-model: versions installed by judge/setup.sh
# (Linux x86_64, glibc 2.36)
python3 3.12.15
venv /home/user/glacier-venv
numpy 2.2.6
matplotlib 3.10.6
```

- **No third-party data.** Every input is generated by the seeded script
  from constants in SPEC.md; no data file is downloaded or redistributed.
  The only third-party reference is the cited paper in README.md
  (Recinos et al. 2019, doi:10.5194/gmd-12-909-2019), which the model is
  *in the spirit of* — it is not OGGM, does not use OGGM code, and reports
  no OGGM numbers.

## Media

`media/` is regenerated from the judge's own outputs by
`bash media/make_media.sh` (run after `judge/setup.sh`, with `ffmpeg` on
`PATH`). Nothing is hand-edited. The files and their provenance are in
`media/MANIFEST.json`:

| file | shows | bytes |
|---|---|---|
| `result.png` | measured vs. analytic curves + shape gate ±2 % band | 292 259 |
| `loop.png` | agent loop (artifact→zero_melt→final_volume→figure→PASS) + 13/13 kill matrix | 224 079 |
| `demo.mp4` | 23 s, 1920×1080, H.264: the sweep animating year by year | 336 961 |

The committed source data is small (the good run's `volumes.csv`, the
`good.json` verdict and one verdict JSON per mutant, and the five loop
artifacts + verdicts); the video frames and the lossless master under
`media/master/` are rebuilt, not committed.
