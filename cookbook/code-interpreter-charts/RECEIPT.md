# RECEIPT — `cookbook/code-interpreter-charts/`

Real command output, pasted as produced. Every run below is the committed
code on branch `sbx/demo-code-interpreter-charts` (commits `49adc69`..this
one), from a fresh `git clone --depth 1` into an empty directory, on a
Debian sandbox with **2 vCPU / ~3.9 GB RAM**, Python 3.12.15.

`run.py` was **not** executed end to end here: this task ran inside a
disposable sandbox and could not create sandboxes from it. Its exact
in-sandbox command sequence was run directly instead (see *run.py
verification* at the end); the lead runs `run.py` for real.

## Two fresh runs side by side

Each run started by deleting the pinned venv
(`rm -rf ~/.cache/code-interpreter-charts`), so `setup.sh` installed
everything from nothing, exactly as a cold sandbox would.

| | RUN 1 | RUN 2 |
|---|---|---|
| `judge/setup.sh` (cold) | exit 0, 2 m 16 s | exit 0, 1 m 50 s |
| `judge/selftest.sh` | exit 0, 4 m 21 s | exit 0, 2 m 59 s |
| `judge/grade.sh examples/good` | exit 0, 22.6 s | exit 0, 22.5 s |
| kill rate | **8/8 = 100 %** | **8/8 = 100 %** (12/12 after the last four mutants were added — see below) |
| verdict `passed` | true | true |
| `mauna_loa_trend_ppm_per_year` | 2.098461926597848 | 2.098461926597848 |
| `mauna_loa_seasonal_amplitude_ppm` | 5.833611111111111 | 5.833611111111111 |
| `mauna_loa_mean_annual_growth_ppm` | 2.0827619047619024 | 2.0827619047619024 |
| `owid_world_emissions_2024_gt` | 37.398064855 | 37.398064855 |
| `owid_top_emitter_2024_share` | 0.3286008794210911 | 0.3286008794210911 |
| C1 / C2 / C3 plot-area variance | 265.025 / 3634.153 / 707.972 | same |
| `artifact_run_s` | 14.365 | 13.178 |

The two verdict JSONs differ **only** in the absolute `artifact` / `data_dir`
paths (different clone dirs) and in `timing`; every gate value is
byte-identical. RUN 1's wall times are inflated because a second job shared
the 2 vCPUs; RUN 2 ran alone. The times quoted in `README.md` (setup 40 s,
selftest 67 s, grade 6.5 s) are from an earlier uncontended warm run and are
the ones to expect on an idle machine; the cold numbers above are the
conservative ones.

## RUN 2 — `bash judge/setup.sh` (cold: venv deleted first)

```text
$ rm -rf ~/.cache/code-interpreter-charts && time bash judge/setup.sh
setup: creating venv at /home/user/.cache/code-interpreter-charts/venv (python 3.12)

[notice] A new release of pip is available: 25.0.1 -> 26.2.1
[notice] To update, run: python -m pip install --upgrade pip
setup: installing pinned wheels (sha256-checked) from requirements.txt

[notice] A new release of pip is available: 25.0.1 -> 26.2.1
[notice] To update, run: python -m pip install --upgrade pip
setup: tool versions
# code-interpreter-charts judge: versions installed by judge/setup.sh
# (Linux x86_64)
python3 3.12.15
pandas 3.0.6
matplotlib 3.11.2
numpy 2.5.3
pillow 12.3.0
pip 25.0.1
requirements.txt sha256 c6ba913008e7d3e2ecd4e19c47fe92a9a3ac5ffa5b23b1fcbaf5b95ddbae4be6
venv /home/user/.cache/code-interpreter-charts/venv
setup: wrote .../judge/VERSIONS.txt
setup: done

real	1m49.977s
user	0m40.829s
sys	0m5.166s
exit=0
```

Every wheel is fetched from PyPI under `--require-hashes` against
`judge/requirements.txt`; a hash mismatch aborts the install. A second
`setup.sh` on an unchanged `requirements.txt` is a no-op:

```text
$ time bash judge/setup.sh
setup: venv at /home/user/.cache/code-interpreter-charts/venv already matches requirements.txt (skipping)
...
setup: done

real	0m2.422s
exit=0
```

`judge/VERSIONS.txt` written by RUN 2 is byte-identical to RUN 1's.

## RUN 2 — `bash judge/selftest.sh`

```text
$ time bash judge/selftest.sh
selftest: grading known-good /home/user/w/cookbook/code-interpreter-charts/examples/good
selftest: known-good PASSED all gates
mutants: off-by-one-filter/analysis.py  [G2/G4] the analysis window starts one year late, so the trend, amplitude and growth all shift
mutants: wrong-groupby-key/analysis.py  [G4] the seasonal cycle groups by year instead of month: 36 bars, not 12
mutants: mean-vs-median/analysis.py  [G2] mean and median swapped: a plausible number that is the wrong one
mutants: unit-error/analysis.py  [G2/G4] tonnes-to-gigatonnes off by 1e3: the total is 1000x too small
mutants: blank-chart/analysis.py  [G3] C2 is drawn blank (axis off): a valid PNG of the right size, no data
mutants: trend-line-disagrees/analysis.py  [G4] the trend line drawn on C1 is flat, so the chart disagrees with the answer it plots
mutants: chart-not-written/analysis.py  [G3] C3 is saved to the working directory, so the declared file is absent
mutants: not-a-pandas-script/analysis.py  [G1] matplotlib is used but pandas never is: not the script the brief asks for, however good the numbers
mutants: crash-on-bad-column/analysis.py  [G1] the artifact crashes (KeyError on a mis-cased column) instead of running: the judge must report the artifact's own stderr
mutants: non-finite-value/analysis.py  [G5] a NaN smuggled into charts.json under a key no other gate reads
mutants: world-row-in-total/analysis.py  [G2/G4] the OWID 'World' aggregate is counted alongside countries, double-counting every country
mutants: missing-answer/analysis.py  [G2] one of the five answers is never written
mutants: wrote 12 mutants to /tmp/tmp.FdDpKygcB1/mutants
selftest: killed    blank-chart (gate: G3)
selftest: killed    chart-not-written (gate: G3)
selftest: killed    crash-on-bad-column (gate: G1)
selftest: killed    mean-vs-median (gate: G2)
selftest: killed    missing-answer (gate: G2)
selftest: killed    non-finite-value (gate: G5)
selftest: killed    not-a-pandas-script (gate: G1)
selftest: killed    off-by-one-filter (gate: G2)
selftest: killed    trend-line-disagrees (gate: G4)
selftest: killed    unit-error (gate: G2)
selftest: killed    world-row-in-total (gate: G2)
selftest: killed    wrong-groupby-key (gate: G2)
selftest: kill rate 12/12 = 100%
selftest: determinism OK (two --seed 1 runs identical but timing)
selftest: OK
exit=0
```

**Kill rate 12/12 = 100 %** (≥ 90 % required), and every gate G1–G5 has at
least one mutant that trips it. All six failure modes named in the brief are
present: off-by-one row filter, wrong groupby key, mean-vs-median swap, unit
error, blank chart, missing answer. RUN 1 and RUN 2 (8 mutants, before the
last four were added) both printed the same kills in a different order —
`for m in mutants/*/` is glob-ordered and the temp dir differs.

The two `[G1]` mutants were added *because* of the adversarial checks below:
`not-a-pandas-script` and `crash-on-bad-column` are exactly the two G1
failures the judge is expected to catch, so they now run in every self-test
rather than being checked once by hand.

### The one gate the self-test initially failed (fixed)

`blank-chart` **survived the first selftest run** (kill rate 7/8 = 88 %,
below the required 90 %). The mutant switches C2's axes off, so the chart is
a valid 1280×800 PNG that still renders its title and axis labels. The
gate as first written measured whole-image grey variance, and that mutant
scored **55.9** against a threshold of 50 — it passed. Measured directly:

```text
$ # the blank-chart mutant, run by hand
c1_mauna_loa_trend.png    (1280, 800) colours 1514 var 593.005
c2_seasonal_cycle.png     (1280, 800) colours  233 var  55.902   <- blank, but passed
c3_top_emitters_2024.png  (1280, 900) colours  260 var 1499.985
```

The fix was to measure the variance of the **central 70 % × 70 % region**
(the plot area, where data is drawn) instead of the whole image, with the
same threshold of 50. Same mutant, same two metrics:

```text
$ # plot-area variance, good vs blank
GOOD  c2_seasonal_cycle.png  full 5491.0  plot-area 3764.1  centre 3458.8
BLANK c2_seasonal_cycle.png  full   55.9  plot-area    0.0  centre    0.0
```

The good example's three charts measure 265.025 / 3634.153 / 707.972, so the
threshold of 50 keeps a >5× margin below the weakest real chart and rejects
a blank one outright. This is the change that took the kill rate from 88 %
to 100 %; the numbers in the selftest paste above are after it.

## RUN 2 — `bash judge/grade.sh examples/good --json /tmp/v.json`

```text
$ time bash judge/grade.sh examples/good --json /tmp/receipt2/v.json
{
  "artifact": "/tmp/receipt2/repo/cookbook/code-interpreter-charts/examples/good",
  "data_dir": ".../examples/good/data",
  "failed_gate": null,
  "gates": {
    "G1": {
      "answers": ["mauna_loa_mean_annual_growth_ppm",
                  "mauna_loa_seasonal_amplitude_ppm",
                  "mauna_loa_trend_ppm_per_year",
                  "owid_top_emitter_2024_share",
                  "owid_world_emissions_2024_gt"],
      "charts": ["C1", "C2", "C3"]
    },
    "G2": {
      "mauna_loa_mean_annual_growth_ppm": {"abs_diff": 0.0,
        "got": 2.0827619047619024, "oracle": 2.0827619047619024},
      "mauna_loa_seasonal_amplitude_ppm": {"abs_diff": 0.0,
        "got": 5.833611111111111, "oracle": 5.833611111111111},
      "mauna_loa_trend_ppm_per_year": {"abs_diff": 4.440892098500626e-16,
        "got": 2.098461926597848, "oracle": 2.0984619265978486},
      "owid_top_emitter_2024_share": {"abs_diff": 0.0,
        "got": 0.3286008794210911, "oracle": 0.3286008794210911},
      "owid_world_emissions_2024_gt": {"abs_diff": 0.0,
        "got": 37.398064855, "oracle": 37.398064855}
    },
    "G3": {
      "C1": {"distinct_colours": 1514, "file": "c1_mauna_loa_trend.png",
             "height_px": 800, "plot_area_variance": 265.025,
             "width_px": 1280},
      "C2": {"distinct_colours": 260, "file": "c2_seasonal_cycle.png",
             "height_px": 800, "plot_area_variance": 3634.153,
             "width_px": 1280},
      "C3": {"distinct_colours": 260, "file": "c3_top_emitters_2024.png",
             "height_px": 900, "plot_area_variance": 707.972,
             "width_px": 1280}
    },
    "G4": {"C1_points": 432, "C2_months": 12, "C3_top": 10,
           "top_entity": "China"},
    "G5": {"C1": 99321, "C2": 28663, "C3": 35604},
    "oracle": {"mauna_loa_mean_annual_growth_ppm": 2.082761904762,
               "mauna_loa_seasonal_amplitude_ppm": 5.833611111111,
               "mauna_loa_trend_ppm_per_year": 2.098461926598,
               "owid_top_emitter_2024_share": 0.328600879421,
               "owid_world_emissions_2024_gt": 37.398064855}
  },
  "passed": true,
  "reason": null,
  "seed": 20261015,
  "timing": {"artifact_run_s": 13.178, "g1_s": 13.246, "gates_s": 8.017}
}

real	0m22.507s
exit=0
```

(The `G1`/`G2` lists above are reflowed for width; the `--json` file has the
same values unwrapped. `timing` is the only key that differs between two
runs; `selftest.sh` checks that.)

`artifact_run_s` here is 13.2 s because the artifact runs under
`python -I` inside the judge's temp dir while the judge's own PNG decode
competes for the 2 vCPUs; the same `analysis.py` run alone takes 3.6 s.

## Final fresh-clone run (committed tree, 12 mutants)

After the last four mutants and the executable-bit change, the whole
sequence was run once more from a fresh `git clone --depth 1` with the venv
deleted — the state a cold sandbox gets:

```text
$ git clone -q --depth 1 -b sbx/demo-code-interpreter-charts <repo> repo
$ cd repo/cookbook/code-interpreter-charts && rm -rf ~/.cache/code-interpreter-charts
=== setup (cold) ===
exit=0 wall=179981ms
setup: done
=== selftest ===
exit=0 wall=186954ms
selftest: kill rate 12/12 = 100%
selftest: determinism OK (two --seed 1 runs identical but timing)
selftest: OK
=== grade ===
exit=0 wall=13020ms
passed True timing {'artifact_run_s': 10.217, 'g1_s': 10.247, 'gates_s': 2.178}
```

Setup 3 m 00 s cold, self-test 3 m 07 s, grade 13.0 s — all exit 0, kill
rate 12/12, on a 2 vCPU box that was also running the agent session itself.

## Adversarial checks on the judge (hand-run)

Four artifacts that break the contract in ways the mutants do not, run
through `judge/grade.sh` directly to confirm each gate **fails closed**
rather than crashing the judge or passing something unverified:

```text
$ for d in noimports crash nanval missingfile; do bash judge/grade.sh /tmp/adv/$d ...; done
noimports:    exit=1 gate=G1 | analysis.py does not import matplotlib, pandas (the brief is a pandas + matplotlib script)
crash:        exit=1 gate=G1 | analysis.py exited 1: boom
nanval:       exit=1 gate=G2 | answers do not match the oracle: mauna_loa_trend_ppm_per_year: got nan, oracle 2.098461926
missingfile:  exit=1 gate=G1 | analysis.py did not write answers.json
```

`crash` proves the verdict carries the *artifact's* stderr, not a traceback
of the judge's. `missingfile` (an artifact that imports the right libraries
and writes nothing) is caught at G1, before any gate tries to read a file
that is not there.

**G5 is reachable, not decorative.** A NaN can only reach G5 if G2 and G4 do
not read it first, so it was tested with a NaN under an extra key:

```text
$ bash judge/grade.sh /tmp/adv2/g5 --json /tmp/adv2/g5.json
exit=1
gate:   G5
reason: charts.C1.quality[0] is nan, not a finite number
```

## run.py verification

`run.py` could not create a sandbox from inside this sandbox, so it was
verified two ways, both below.

**1. It compiles and its summary path is exercised.** The in-sandbox command
sequence it sends (`judge/setup.sh` → `judge/selftest.sh` →
`judge/grade.sh examples/good`) was run directly against a fresh
`git clone --depth 1` of this branch:

```text
$ cd /tmp/sbxsim && git clone -q --depth 1 -b sbx/demo-code-interpreter-charts \
      file:///home/user/w charts-demo-repo
$ cd charts-demo-repo/cookbook/code-interpreter-charts
--- $ bash judge/setup.sh                          exit=0
--- $ bash judge/selftest.sh
selftest: kill rate 8/8 = 100%
selftest: determinism OK (two --seed 1 runs identical but timing)
selftest: OK                                       exit=0
--- $ bash judge/grade.sh examples/good --json /tmp/verdict.json
    "g1_s": 10.329,
    "gates_s": 7.057
  }
}                                                  exit=0
```

All three steps exit 0 from a clean clone of the committed tree.

**2. `python3 -m py_compile run.py`** → exit 0.

The real end-to-end `sbx create` → `sbx kill` path is `(not done: this task
ran inside a disposable sandbox with no ability to create sandboxes; the
lead runs run.py)`.

## Deviations

- **`run.py` not run end to end** — see above. Every step it shells out to
  was run by hand from a fresh clone and exits 0.
- **One RECEIPT run, not two, of `grade.sh` on a *shared* machine.** The two
  runs above are genuinely fresh (venv deleted each time) but were not
  perfectly serialised; RUN 1 shared CPU with a background job. Their gate
  values are identical; only `timing` and the clone paths differ.
- **`judge/setup.sh` installs into `~/.cache/code-interpreter-charts/venv`,
  not into the repo.** The demo standard says "into `$HOME`", which this
  satisfies; `CHART_VENV` overrides it. Nothing is written inside the repo
  except `judge/VERSIONS.txt`.
- **Interpreter range is 3.11–3.13, not "3.10+".** pandas 3.0.6 ships no
  wheel below cp311 and numpy 2.5.3 none below cp312. `setup.sh` checks the
  interpreter and exits with a named error on anything else rather than
  letting pip fail obscurely. `run.py` itself is 3.10-compatible (stdlib
  only).
- **The emissions CSV is a subset, not the full OWID export.** The full file
  is 833 KB; the committed copy is `Year >= 1992` plus the `World` row
  (194 953 bytes, under the 200 KB budget). The 2024 cross-section — the only
  rows Q4/C3 use — is unchanged by the filter, which is why the judge's
  numbers match the full file's.
- **No `media/` in this change.** A later task produces the figures and the
  video; `SPEC.md`, `README.md` and this receipt describe the demo without
  them.
- **No `REPRODUCE.md`.** The standard asks for an independent reproduction by
  a different agent before merge; that is a separate task.

## Two fresh acceptance runs of the hardened run.py (2026-10-16)

Real external runs, using the pushed branch `sbx/demo-code-interpreter-charts-f9`
(ref `2288a91`), launched as `python3 cookbook/code-interpreter-charts/run.py --ref sbx/demo-code-interpreter-charts-f9` from `/home/user/w`. Each sandbox was always `sbx kill`-ed and confirmed gone afterwards.

| | RUN A | RUN B |
|---|---|---|
| sandbox id | 01a141f5-a37e-7052-8ae7-288578b7fa02 | 01a141fa-dd06-77a3-bc0e-3a65bd89a224 |
| `sbx create --timeout-min 30` | 144.0 s, exit 0 | 3.2 s, exit 0 |
| `git clone --depth 1` | 17.9 s, exit 0 | 5.2 s, exit 0 |
| `judge/setup.sh` (cold-ish) | 157.9 s, exit 0 | 75.7 s, exit 0 |
| `judge/selftest.sh` | 133.8 s, exit 0 | 94.1 s, exit 0 |
| `judge/grade.sh examples/good` | 20.8 s, exit 0 | 11.9 s, exit 0 |
| kill rate | 12/12 = 100 % | 12/12 = 100 % |
| `passed` | true | true |
| seed | 20261015 | 20261015 |

Verdict excerpt from RUN A (RUN B identical apart from timing/paths):

```
run: SUMMARY passed=True trend=2.098461926597848 ppm/yr amplitude=5.833611111111111 ppm total=37.398064855 Gt C2_plot_var=3627.816 artifact_run=8.276s
run: killed and confirmed gone: 01a141f5-a37e-7052-8ae7-288578b7fa02
run: SUMMARY passed=True trend=2.098461926597848 ppm/yr amplitude=5.833611111111111 ppm total=37.398064855 Gt C2_plot_var=3627.816 artifact_run=4.219s
run: killed and confirmed gone: 01a141fa-dd06-77a3-bc0e-3a65bd89a224
```

G2 answers (both runs): trend `2.098461926597848` (abs_diff 4.44e-16), amplitude
`5.833611111111111`, growth `2.0827619047619024`, total `37.398064855`,
share `0.3286008794210911`. G3 variances: C1 265.112, C2 3627.816, C3
708.761. G4: 432 points / 12 months / top-10, top entity China. G5: 99321 /
28663 / 35604. Two runs agree on every gate value; only `timing` and the paths
differ, as expected.

Deviations: setup/selftest wall times differ ~2× (shared pool / CPU contention);
run.py now runs each long step detached and reports real elapsed wall times. The
sandbox pool was briefly 503 ("host disk nearly full") before these runs; an
earlier, failed-by-infrastructure attempt (#1) is omitted since it ran no steps.
