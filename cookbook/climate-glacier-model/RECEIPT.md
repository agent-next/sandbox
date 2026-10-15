# RECEIPT — `cookbook/climate-glacier-model/`

Real command output, pasted as produced. The three blocks below are the
verbatim log of **one fresh run** on this branch: a clean copy of the tree
with no venv present (`rm -rf ~/glacier-venv` before `setup.sh`), Debian 12
(bookworm), glibc 2.36, 2 vCPU, ~4 GB RAM. Nothing here is retyped or
stitched together from different runs.

`judge/setup.sh` installs only Python wheels into `~/glacier-venv`; no
system package is touched, so "fresh" means exactly "no venv".

| step | exit | wall time |
|---|---|---|
| `bash judge/setup.sh` (fresh venv) | 0 | 69 s |
| `bash judge/selftest.sh` (good + 13 mutants + determinism) | 0 | 218 s |
| `bash judge/grade.sh examples/good --json verdict.json` | 0 | 27 s |

| key number | this run |
|---|---|
| kill rate | **13/13 = 100 %** |
| `warm_2p0` crossing year | 96.0076481835564 |
| `warm_2p4` crossing year | 81.60555821753714 |
| `warm_2p8` crossing year | 71.40555289612254 |
| `warm_2p0` `V(100)` km³ | 2.832 |
| `warm_2p4` `V(100)` km³ | 2.04288 |
| `warm_2p8` `V(100)` km³ | 1.20192 |
| zero-melt worst deviation | 0.0 (tolerance 1e-9) |
| `verdict["passed"]` | `true` |

## Step 1 — `bash judge/setup.sh`

```text
setup: creating venv /home/user/glacier-venv
setup: installing pinned wheels (sha256-checked by pip --require-hashes)
setup: python 3.12.15
setup: numpy 2.2.6
setup: matplotlib 3.10.6
setup: wrote /tmp/gscratch/final/w/cookbook/climate-glacier-model/judge/VERSIONS.txt
setup: done
```

## Step 2 — `bash judge/selftest.sh`

```text
selftest: grading known-good /tmp/gscratch/final/w/cookbook/climate-glacier-model/examples/good
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
mutants: wrote 13 mutants to /tmp/tmp.MQB9DKyt8D/mutants
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
```

**Kill rate 13/13 = 100 %** (requirement ≥ 90 %, ≥ 5 known-bad). Kills span
`artifact` (×4), `crossing` (×4), `determinism`, `final_volume`, `figure`
and `zero_melt`. The final three lines are the determinism check: two
`grade.sh --seed 1` runs must be identical but for the `timing` key.

## Step 3 — `bash judge/grade.sh examples/good --json verdict.json`

```json
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
    "first_run_seconds": 10.03,
    "second_run_seconds": 10.16,
    "total_seconds": 25.62,
    "zero_melt_seconds": 5.29
  }
}
```

The four wall-time fields live under `timing`; SPEC.md requires that they
be the only keys that differ between two runs with the same seed, which is
what step 2's determinism check asserts.

## What the judge actually measured

- **Analytic oracle**: crossing years are +0.0007 / -0.0647 / -0.0206 yr from the closed-form
  roots (tolerance ±3 yr) — the interpolation and cell-mask discretisation,
  not a fit.
- **Negative control**: with `--zero-melt` the worst deviation from `V(0)`
  over all 303 rows is exactly **0.0** (tolerance 1e-9 relative), and no
  scenario reports a crossing.
- **Mask consistency**: the CSV volumes invert to 240 / 168 / 96 ice cells,
  matching the analytic length to the cell.
- **Shape**: worst deviation from the analytic volume across all years is
  0.15 % / 0.21 % / 0.38 % (tolerance 2 %); no scenario's volume rises.

## Second fresh run

An earlier pair of fresh runs on the same branch (identical tree, venv
removed before each) gave the same verdict byte-for-byte with the `timing`
key removed, and the same kill rate. Their wall times differed with machine
load (setup 80 s / 107 s, selftest 206 s / 239 s) while every graded number
was identical — the verdict does not depend on wall time, which is why the
`timing` key is excluded from the determinism comparison.

## Deviations

- **`REPRODUCE.md` is not filled in.** The standard requires an independent
  agent on a different model family to follow README.md alone in a fresh
  sandbox before merge. That has not happened yet; the file states this and
  lists the numbers to compare. *(not done: independent agent run)*
- **`media/` is absent.** A later task produces `result.png`, `loop.png`,
  `demo.mp4`, `MANIFEST.json` and `make_media.sh`. *(not done: out of scope
  for this task, by instruction)*
- **`run.py` was not executed end to end.** No sandbox can be created from
  inside this sandbox. It was checked with `python3 -m py_compile` and by
  running its exact in-sandbox command sequence directly against a local
  copy of this tree: `git clone` → `bash judge/setup.sh` →
  `bash judge/selftest.sh` → `bash judge/grade.sh examples/good --json …`,
  which is precisely what the three blocks above are. The lead runs
  `run.py` itself.
- **Wall times vary with machine load.** `setup.sh` ranged 63–107 s and
  `selftest.sh` 206–239 s across fresh-venv runs; the verdicts did not vary
  at all. README quotes the range.
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
