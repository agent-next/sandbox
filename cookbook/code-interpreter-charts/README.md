# code-interpreter-charts

An LLM code interpreter doing data analysis in a disposable agent-next
sandbox: the agent writes `analysis.py` (pandas + matplotlib) that answers
five fixed questions about two pinned public datasets and draws three PNG
charts, and a judge it cannot fool recomputes every answer from the raw CSV
with plain `csv` + `statistics` and inspects the pixels of every chart.

Why a sandbox helps: the script needs a scientific Python stack and a
headless renderer, and the whole grade — install, run, judge, self-test —
takes about two minutes on a 2 vCPU sandbox. The agent can iterate against
the grader without touching the user's machine, and the dataset is pinned by
sha256 so a run on any machine grades the same numbers.

## Ask your agent

> Write a Python data-analysis script in a sandbox for these two CSVs (Mauna
> Loa monthly CO₂ and annual CO₂ emissions by country): answer the five
> questions in `SPEC.md`, draw the three charts, and iterate with
> `judge/grade.sh` until it passes. Show me the verdict and the three PNGs.

The plugin installs the judge for the agent; the agent designs the artifact
itself and re-runs the grader after each edit.

## One-command run

```bash
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
export SBX_API_KEY=<your key>
python3 cookbook/code-interpreter-charts/run.py              # clone main
python3 cookbook/code-interpreter-charts/run.py --ref <sha>  # pin a ref
```

Per run: create a sandbox (`--timeout-min 30`) → `git clone --depth 1 -b
main` this repo → `judge/setup.sh` (pinned wheels) → `judge/selftest.sh` →
`judge/grade.sh examples/good` → print the verdict → always `sbx kill` and
confirm with `sbx list` that the id is gone. Non-zero exit on any failure,
naming the sandbox id when cleanup could not be confirmed. `--keep` leaves
the sandbox up and prints its id.

## What the judge checks

`judge/grade.sh <artifact-dir> [--seed N] [--json out.json]` runs five
numeric gates (full rules in `SPEC.md`) and exits 0 only if all pass:

| gate | rule |
| --- | --- |
| G1 contract | `analysis.py` parses, imports pandas + matplotlib, runs headless within 300 s, writes `answers.json`, `charts.json` and the three PNGs |
| G2 answers | all five answers within `1e-6 * max(1, oracle)` of `judge/oracle.py`, which recomputes them from the raw CSV with `csv` + `statistics` only |
| G3 images | each PNG decodes, matches its declared size, has ≥ 8 distinct RGB colours and plot-area grey variance ≥ 50 |
| G4 plotted data | the series in `charts.json` (OLS slope, seasonal means, top-10, total, C1's 432 monthly points) match the oracle's own aggregation |
| G5 honesty | every number finite; the three PNGs are not byte-identical copies |

The oracle is a second, independently written implementation — the OLS slope
is the closed form `Σ(x-x̄)(y-ȳ)/Σ(x-x̄)²`, the amplitude is a difference of
means, the emissions total is a sum over an ISO-3166 code regex — so a
"plausible but wrong" number fails rather than being graded against itself.

## Measured results

Run 2026-10-15, 2 vCPU / ~3 GB, Python 3.12.15 (`judge/VERSIONS.txt`):

| step | wall time |
| --- | --- |
| `judge/setup.sh` (cold) | 40 s |
| `judge/setup.sh` (warm, idempotent) | 2.4 s |
| `judge/selftest.sh` (good + 8 mutants + determinism) | 67 s |
| `judge/grade.sh examples/good` | 6.5 s |

Self-test kill rate: **8/8 = 100 %** — off-by-one row filter, wrong groupby
key, mean-vs-median swap, unit error, blank chart, flat trend line, the
`World` aggregate double-counted, and a missing answer are each caught by at
least one gate. The good example's answers:

| answer | value |
| --- | --- |
| `mauna_loa_trend_ppm_per_year` | 2.098461926597848 |
| `mauna_loa_seasonal_amplitude_ppm` | 5.833611111111111 |
| `mauna_loa_mean_annual_growth_ppm` | 2.0827619047619024 |
| `owid_world_emissions_2024_gt` | 37.398064855 |
| `owid_top_emitter_2024_share` | 0.3286008794210911 |

Full pasted output and exit codes: `RECEIPT.md`.

## Dataset

Both files are pinned by sha256 under `examples/good/data/`; neither is
fetched at run time.

- `co2_mm_mlo.csv` — NOAA Global Monitoring Laboratory, *Trends in
  Atmospheric Carbon Dioxide*, Mauna Loa monthly mean CO₂, 1958–2026
  (<https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_mm_mlo.csv>). Public
  domain / US Government work. 38 776 bytes, sha256 `d895fb5b…c07f675`.
- `annual-co2-emissions-per-country.csv` — Our World in Data, *Annual CO₂
  emissions by country* (fossil CO₂ and industry), CC BY 4.0
  (<https://ourworldindata.org/grapher/annual-co2-emissions-per-country.csv>).
  Subset: `Year >= 1992` plus the `World` row, 7 122 rows, 194 953 bytes,
  sha256 `51b7033c…f3e4d9316`.

## Limits

- The script must run headless; the judge sets `MPLBACKEND=Agg`. Charts are
  graded on data and pixels, not on aesthetics.
- The judge pins CPython 3.11–3.13 (pandas 3.0.6 has no wheel below 3.11);
  `judge/setup.sh` fails with a named error on any other interpreter.
- Q1–Q3 are one window (1990–2025) and one estimator (ordinary least
  squares, means); they test whether the artifact computed *these* numbers,
  not whether another window would be more interesting.
- Chart validity is a variance and colour-count threshold, so a chart that
  draws the right series in an unreadable style still passes. The oracle
  gate, not the pixel gate, is what makes a wrong answer fail.
