# SPEC — `cookbook/code-interpreter-charts/`

An agent works on a real data-analysis problem inside a disposable agent-next
sandbox: it writes a Python analysis script that answers five fixed questions
about a pinned public CSV and draws three charts, where a judge it cannot fool
recomputes every answer from the raw CSV with plain `csv` + `statistics` (no
pandas, no matplotlib) and inspects the pixels of every chart.

## Goal

Produce `analysis.py` — one self-contained pandas + matplotlib script — that,
given the pinned dataset in the same directory, writes `answers.json` (five
numeric answers) and `charts.json` (the plotted series, as numbers), and
renders three PNG charts. A separate grader recomputes all five answers from
the CSV by an independent path and checks that the PNGs are real, non-blank
images whose plotted data matches the grader's own aggregation.

Why a sandbox helps: the script needs a scientific Python stack (pandas +
matplotlib), a display-less renderer, and a re-runnable judge; the agent can
install, run, read the grader's verdict and iterate inside a disposable
environment without touching the user's machine. The whole grade runs in
seconds on 2 vCPU / ~3 GB RAM.

## Non-goals

- Any dataset other than the two pinned files under `data/` (see *Dataset*).
- Interactive or notebook output; only files written to disk are graded.
- Chart aesthetics beyond the numeric gates (palette, fonts, titles): any
  valid PNG that passes the gates is fine.
- Statistically sophisticated analysis: every question has an exact,
  reproducible definition (below); no fitting beyond one ordinary least
  squares line.
- Performance: the script may take up to the judge's timeout; there is no
  reward for speed.

## Dataset

`examples/good/data/co2_mm_mlo.csv` — NOAA Global Monitoring Laboratory,
*Trends in Atmospheric Carbon Dioxide*, Mauna Loa monthly mean CO₂ (dry air
mole fraction, ppm), downloaded 2026-10-15 from
<https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_mm_mlo.csv>.
Public domain / US Government work (NOAA GML data policy: freely available,
cite NOAA GML). 38 776 bytes, sha256
`d895fb5b4a59fb5e4cd98e69b7667fe5bef595c6581f630852b12cb41c07f675`.
File format: 40 comment lines beginning `#`, then a header
`year,month,decimal date,average,deseasonalized,ndays,sdev,unc`, then 823
monthly rows, March 1958 – September 2026, no missing `average` values.

`examples/good/data/annual-co2-emissions-per-country.csv` — Our World in Data,
*Annual CO₂ emissions by country* (fossil CO₂ and industry, tonnes per year),
downloaded 2026-10-15 from
<https://ourworldindata.org/grapher/annual-co2-emissions-per-country.csv>.
Licence CC BY 4.0 (Our World in Data; underlying data Global Carbon Budget).
Subset kept: rows whose `Year >= 1992` **and** whose `Code` is a 3-letter
ISO-3166 alpha-3 code, plus the `World` row — 7 122 rows, 194 953 bytes,
sha256 `51b7033c0ddeb27492b5f87e684576d72c7bd6ad18e5ef8a7dc7cd3f3e4d9316`
(the `Year >= 1990` slice is 206 396 bytes, over the 200 KB budget; the
aggregate rows other than `World` are dropped because no question uses them).
The filter is applied before committing, so Q4/C3's 2024 numbers are
identical to the full file's. Columns `Entity,Code,Year,Annual CO₂ emissions`;
`Code` is an ISO-3166 alpha-3 code, blank, or an OWID aggregate code
(`OWID_WRL` for `World`). Used by the *scope* question (Q4) and by chart C3.

**Question scope.** Q1–Q3, Q5 and charts C1–C2 use only the Mauna Loa file.
Q4 and C3 use only the emissions file. An artifact may read either file; the
judge supplies both.

## Artifact

A single file `analysis.py` (the file graded by `judge/grade.sh <artifact>`),
run as

```
python3 analysis.py --data-dir <dir> --out-dir <dir>
```

from the artifact's own directory, with `<dir>` holding the two pinned CSVs
(the judge passes a copy of `examples/good/data/`). It must:

- use **pandas** to load the CSV and **matplotlib** to draw the charts (the
  judge does not grade the libraries used, but the brief and the mutants are
  built around that stack; a solution that never imports pandas does not meet
  the brief);
- run headless (no display; the judge sets `MPLBACKEND=Agg`);
- write `answers.json` and `charts.json` into `--out-dir`, plus the three
  PNGs named in `charts.json` (bare file names, written to `--out-dir`);
- exit 0 on success.

### `answers.json` — five keys, all floats

| key | meaning |
|---|---|
| `mauna_loa_trend_ppm_per_year` | slope of the ordinary least squares line of monthly `average` on `decimal date`, over the Mauna Loa rows with `1990 <= year <= 2025` |
| `mauna_loa_seasonal_amplitude_ppm` | mean `average` of the annual maximum month minus that of the annual minimum month, over the same window; the month set is the 12 calendar months of the window |
| `mauna_loa_mean_annual_growth_ppm` | mean of `year_mean(y) - year_mean(y-1)` for `y` in 1991..2025, where `year_mean(y)` is the mean `average` over the window rows of year `y` |
| `owid_world_emissions_2024_gt` | total 2024 `Annual CO₂ emissions` over the rows whose `Code` is a 3-letter ISO-3166 alpha-3 code, in gigatonnes (1 Gt = 1e9 tonnes = 1e12 kg) |
| `owid_top_emitter_2024_share` | for the 2024 ISO rows, the largest emitter's emissions divided by the total over all ISO rows (a dimensionless fraction) |

"ISO-3166 alpha-3 code" means a `Code` matching `^[A-Z]{3}$` (so `OWID_WRL`,
other aggregates and blank codes are excluded; `World` is *not* in the total,
and is not the top emitter — 2024's largest ISO emitter is `CHN`).

### `charts.json` — the plotted series, as numbers

A JSON object with exactly the keys `C1`, `C2`, `C3`. Each is an object with
the same numeric keys as `answers.json` (the values the chart plots) plus:

| chart | extra keys |
|---|---|
| `C1` (Mauna Loa monthly series + OLS trend line) | `months` (list of `[decimal_date, average]` pairs, window order as in the file) and `trend_line` (`[[decimal_date, value], ...]` at the two window end dates) |
| `C2` (Mauna Loa mean seasonal cycle) | `months` (`[month, mean_average]` for months 1..12) and `amplitude_ppm` |
| `C3` (OWID 2024 top-10 ISO emitters, horizontal bars) | `entities` (list of entity names), `emissions_gt` (list of `[name, value_gt]` pairs, descending by value, 10 entries) and `total_gt` |

The PNG files named `c1_mauna_loa_trend.png`, `c2_seasonal_cycle.png`,
`c3_top_emitters_2024.png` must be written to `--out-dir` (size in px given
by `width_px` / `height_px` in `charts.json`, which must be 1280×800, 1280×800
and 1280×900 respectively).

## Judge gates (`judge/grade.sh <artifact> [--seed N] [--json out.json]`)

All gates are numeric and deterministic. Exit 0 only if every gate passes.
`--seed` is accepted for interface parity and recorded in the verdict; the
judge itself is seed-free (no random choices).

- **G1 artifact contract**: `analysis.py` parses (`py_compile`), imports
  pandas and matplotlib, and the judge's single run of it — from a temp copy
  of the artifact directory, with the pinned `data/` copied in — exits 0
  within 300 s and writes `answers.json`, `charts.json` and the three PNGs.
  A crash, a timeout, a missing file or unreadable JSON fails with the
  artifact's own stderr in the verdict.
- **G2 answers vs the independent oracle**: the judge recomputes all five
  values from the raw CSV using only `csv` + `statistics` (see *Acceptance
  oracle*) and requires `|artifact - oracle| <= 1e-6 * max(1, |oracle|)` for
  every key. The absolute tolerance is **1e-6** for a value of order 1 and
  scales with the value (≈ 2.1e-6 ppm/a for the trend, ≈ 3.7e-5 Gt for the
  total).
- **G3 images are real and non-blank**: each PNG decodes (judge uses Pillow),
  matches the declared `width_px` × `height_px` exactly, has ≥ 8 distinct
  RGB colours, and has grey-level variance ≥ **50.0** over its central
  70 % × 70 % region — the plot area, where the data is drawn. Whole-image
  variance is *not* used: a chart with its axes switched off still renders a
  title and labels and measures 55.9, while its plot area measures exactly
  0.0 (real charts here measure 265, 3634 and 708). The declared size is
  checked against the decoded file, not trusted.
- **G4 plotted data matches the oracle**: for each chart the numbers in
  `charts.json` are compared against the judge's own aggregation with the
  same 1e-6 relative tolerance: the OLS slope and amplitude (C1/C2), the 12
  monthly means (C2), the top-10 2024 ISO emitters and the total (C3), and
  C1's `months` against the window rows (a length mismatch or a value
  off by more than 1e-6 fails). This is what stops a script that draws a
  pretty chart of the wrong numbers.
- **G5 honesty**: every numeric value in `charts.json` is finite (no `NaN`,
  `Infinity` or `null`), and the three PNG files are distinct byte-wise (one
  image copied three times fails).

Violating any gate fails with the offending numbers printed.

## Acceptance oracle (independent of "it ran")

The judge does **not** trust the artifact's own numbers. `judge/oracle.py`
recomputes every answer and every plotted series from the raw CSV with
Python's `csv` and `statistics` modules only — no pandas, no numpy — so the
comparison is against a second, independently written implementation:

1. **Analytic/reference recomputation**: the OLS slope is the closed-form
   `Σ(x-x̄)(y-ȳ) / Σ(x-x̄)²`; the seasonal amplitude is the difference of two
   means; the growth is a mean of yearly differences; the emissions total is
   a sum over rows filtered by an ISO-3166 code regex, with the unit
   conversion 1e9 applied by the judge.
2. **Cross-check of the good example**: the judge's numbers for the pinned
   data are recorded in this SPEC and in `examples/good/answers.json`, and
   `judge/selftest.sh` requires the good example to match them.
3. **Pixels, not claims**: chart validity is decided by decoding the PNG and
   measuring colour count and variance; the declared size is compared with
   the decoded image.
4. **Fail closed**: if the oracle itself cannot parse the CSV, or the
   artifact's JSON is missing a key, the gate **fails** — the judge never
   passes an artifact it could not verify.

Reference values for the pinned files (judge oracle, `csv`+`statistics`):

```
mauna_loa_trend_ppm_per_year      2.0984619265978486
mauna_loa_seasonal_amplitude_ppm  5.833611111111111
mauna_loa_mean_annual_growth_ppm  2.082761904761904
owid_world_emissions_2024_gt      37.398064855
owid_top_emitter_2024_share       0.3286008794210911
```

The 2024 ISO cross-section sums to 37 398 064 855 t = **37.398 GtCO₂**
(`CHN` alone is 12.289 Gt). The `1e9` conversion is applied by the judge, so
a unit error in the artifact moves the total by a factor of 1e3 or 1e12 and
fails G2; the share is unit-free and is caught by G4's top-10 comparison
instead.

## Self-test (`judge/selftest.sh`)

- The known-good example passes all gates.
- ≥ 5 known-bad single-edit mutants of `analysis.py` each fail ≥ 1 gate;
  mutants are generated by `judge/mutants.py` (one edit each), and include
  the failure modes named in the brief: off-by-one row filter, wrong groupby
  key, mean-vs-median swap, unit error, blank chart, missing answer.
- Kill rate ≥ 90 % printed by the self-test; exit non-zero otherwise.
- Determinism: two `grade.sh` runs on the good example produce byte-identical
  verdict JSON (excluding the `timing` key); checked on every self-test run.

## Judge-integrity rule

The artifact under test is copied to a temp dir before grading and never
imported into the judge process; the judge compares the sha256 of its own
`judge/` tree before and after every grade and fails closed if anything
changed.

## Out of scope for the judge

- Whether the analysis is *interesting* or the charts are *pretty*.
- Anything the artifact claims in comments, docstrings or printed output.
- Libraries other than pandas/matplotlib, as long as G1's imports hold.

## Tools (pinned by `judge/setup.sh`)

- Python 3.12 (judge engine: stdlib only, plus **Pillow 12.3.0** for PNG
  decoding, installed from a sha256-pinned wheel).
- pandas **3.0.6**, matplotlib **3.11.2**, numpy **2.5.3** and their
  transitive pins (exact versions, sha256-checked wheels, nothing published
  within two weeks of 2026-10-15). `judge/VERSIONS.txt` records what
  `setup.sh` actually installed.
