# RECEIPT — `cookbook/backtest-equity/`

Real command output from two fresh sandbox runs of the one-command demo
(`run.py`), recorded by the builder agent on 2026-10-15, after the PR
review fixes (G6 rejects `lookahead_shift 0`; the demo video was re-cut;
the self-test now carries 11 mutants; the media MANIFEST counts them).
Both runs created a fresh sandbox,
cloned this repo at `--ref sbx/demo-backtest-equity-f3` (the branch the demo
lives on, at the head SHA this RECEIPT ships with), ran `judge/setup.sh` →
`judge/selftest.sh` → `judge/grade.sh examples/good --seed 42`, and killed
the sandbox, confirming with `sbx list` that its id was gone.

Command (from outside the repo, exactly as a user runs it):

```bash
python3 cookbook/backtest-equity/run.py --ref sbx/demo-backtest-equity-f3
```

## Run A — sandbox `01a140a7-cd97-71e1-90ea-d0684acc94fe`

Per-step timing lines printed by `run.py`:

```
[  2.9s] sandbox 01a140a7-cd97-71e1-90ea-d0684acc94fe
[  5.7s] clone: ok
[ 42.7s] setup: ok
[  7.4s] selftest: ok
[  4.0s] grade: ok
```

`run.py` exit code: **0**. Verdict: **PASS** (all six gates).

Self-test kill-rate lines:

```
mutant lookahead-shift: FAIL (expected) -- killed by gate: G2_final_equity_oracle
mutant lookahead-signal: FAIL (expected) -- killed by gate: G3_sharpe_consistency
mutant shift-0-declare: FAIL (expected) -- killed by gate: G6_schema_sanity
mutant sharpe-tamper: FAIL (expected) -- killed by gate: G3_sharpe_consistency
mutant equity-tamper: FAIL (expected) -- killed by gate: G2_final_equity_oracle
mutant mdd-tamper: FAIL (expected) -- killed by gate: G4_max_drawdown
mutant fixture-drift: FAIL (expected) -- killed by gate: G1_fixture_integrity
mutant cost-tamper: FAIL (expected) -- killed by gate: G6_schema_sanity
mutant returns-drift: FAIL (expected) -- killed by gate: G3_sharpe_consistency
mutant short-history: FAIL (expected) -- killed by gate: G6_schema_sanity
mutant tiny-figure: FAIL (expected) -- killed by gate: G6_schema_sanity
kill rate: 11/11 (100%)
determinism: PASS (two --seed 42 runs identical excluding "timing")
judge integrity: PASS (judge/ checksum unchanged by grading)
selftest: PASS
```

Verdict gates (from the printed JSON):

```
G6_schema_sanity:       PASS  2517 return rows (2014-01-02..2023-08-25), dates
                              strictly increasing, no NaNs; equity.png 2000x1400;
                              metrics.json keys ok, cost_bps 10.0, lookahead_shift 1.0
G1_fixture_integrity:   PASS  ohlcv.csv sha256 227517225b7f4978c8c5c4092d40a91af9a5cbd82859c82c7516f92efb881821 == pinned fixture
G2_final_equity_oracle: PASS  artifact final_equity 0.9470302914 vs reference 0.9470302914 at
                              lookahead_shift 1 (relative deviation 0.000e+00, limit 1e-03)
G3_sharpe_consistency:  PASS  metrics.json sharpe 0.0365365875 vs recomputed from
                              returns.csv 0.0365365875; |diff| 3.109e-15, limit 1e-06
G4_max_drawdown:        PASS  metrics.json max_drawdown 0.4177213784 vs recomputed
                              0.4177213784; |diff| 2.933e-12, limit 1e-06
G5_lookahead_control:   PASS  reference final_equity at shift 1 = 0.9470302914,
                              at shift 2 = 0.6762990012 (differ by 2.859e-01, limit 1e-09)
failed_gates: []
```

Summary line:

```
run: SUMMARY verdict=PASS final_equity=0.9470302914437041 (reference 0.9470302914437041) sharpe=0.036536587479012825 max_drawdown=0.4177213784209337 n_trades=101.0 n_days=2517.0 failed_gates=[]
```

Sandbox cleanup: `run.py` printed
`sandbox 01a140a7-cd97-71e1-90ea-d0684acc94fe killed and confirmed gone`,
and `sbx list` no longer lists the id.

## Run B — sandbox `01a140a8-e168-7621-b341-bcfe0c2c8e2e`

Per-step timing lines:

```
[  2.4s] sandbox 01a140a8-e168-7621-b341-bcfe0c2c8e2e
[  5.9s] clone: ok
[ 40.0s] setup: ok
[  8.2s] selftest: ok
[  4.1s] grade: ok
```

`run.py` exit code: **0**. Verdict: **PASS** (all six gates).

Self-test kill-rate lines: identical to Run A (11/11, 100 %); determinism
PASS; judge integrity PASS; selftest PASS.

Summary line: identical to Run A.

Sandbox cleanup: `run.py` printed
`sandbox 01a140a8-e168-7621-b341-bcfe0c2c8e2e killed and confirmed gone`,
and `sbx list` no longer lists the id.

## What the PR-review fixes changed (measured)

- **G6 rejects `lookahead_shift 0`.** Before the fix a fully self-consistent
  artifact at shift 0 (the lookahead cheat: today's close sizing today's
  position) passed every gate with final equity `1.4091495383` vs the
  reference `0.9470302914` (+48.7 %). The judge now fails it: G6 detail
  `lookahead_shift 0.0 must be an integer >= 1 ...`, `grade.sh` exit 1. The
  new `judge/mutants.py` mutant `shift-0-declare` is exactly that artifact,
  and `judge/selftest.sh` fails outright if any mutant escapes.
- **Video re-cut.** `cookbook/tools/video_gate.py` on the new
  `media/demo.mp4`: `scene_cuts_per_10s 1.44` (≥ 0.8), `motion_fraction
  0.52` (≥ 0.20), `endcard_static 0.00` (≤ 0.5), 34.7 s, 1920×1080, 30 fps,
  1.59 MiB — `passed: true`, `failed: []`. The old cut was a slow morph
  reveal (0 cuts, moving tail); the new one is four scenes separated by hard
  black cuts with a rolling per-day market tape.

## Side-by-side key numbers

| quantity | Run A | Run B |
|---|---|---|
| verdict | PASS | PASS |
| final_equity | 0.9470302914437041 | 0.9470302914437041 |
| reference final_equity | 0.9470302914437041 | 0.9470302914437041 |
| sharpe | 0.036536587479012825 | 0.036536587479012825 |
| max_drawdown | 0.4177213784209337 | 0.4177213784209337 |
| n_trades | 101 | 101 |
| n_days | 2517 | 2517 |
| kill rate | 11/11 (100 %) | 11/11 (100 %) |
| determinism | PASS | PASS |
| judge integrity | PASS | PASS |
| `run.py` exit code | 0 | 0 |
| clone wall time | 5.7 s | 5.9 s |
| setup wall time (fresh install) | 42.7 s | 40.0 s |
| selftest wall time | 7.4 s | 8.2 s |
| grade wall time | 4.0 s | 4.1 s |

The two runs agree on every graded number to full double precision. Wall
times differ by a few seconds per step, as expected for a shared network.

## Tool versions (from `judge/VERSIONS.txt`, written by `judge/setup.sh`)

```
python3 3.12
numpy 2.2.6
matplotlib 3.9.4
contourpy 1.4.0
cycler 0.12.1
fonttools 4.66.1
kiwisolver 1.5.1
packaging 26.3
pillow 12.3.0
pyparsing 3.3.3
python-dateutil 2.9.0.post0
six 1.17.0
```

Every pin is at least two weeks old (the standard's freshness rule);
`fonttools` was repinned `4.67.0` → `4.66.1` because `4.67.0` was published
2026-10-14, inside that window.

## Deviations

None. Both runs completed every step (clone → setup → selftest → grade →
kill + confirm) with exit code 0 and an all-gates-pass verdict, on the
reviewed head SHA.
