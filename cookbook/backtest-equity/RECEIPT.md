# RECEIPT — `cookbook/backtest-equity/`

Real command output from two fresh sandbox runs of the one-command demo
(`run.py`), recorded by the builder agent on 2026-10-15. Both runs created a
fresh sandbox, cloned this repo at `--ref sbx/demo-backtest-equity-f1` (the
branch the demo lives on), ran `judge/setup.sh` → `judge/selftest.sh` →
`judge/grade.sh examples/good --seed 42`, and killed the sandbox, confirming
with `sbx list` that its id was gone.

Command (from outside the repo, exactly as a user runs it):

```bash
python3 cookbook/backtest-equity/run.py --ref sbx/demo-backtest-equity-f1
```

## Run A — sandbox `01a13e96-dea9-7332-ab2b-e9fb8d47de77`

Per-step timing lines printed by `run.py`:

```
[  7.6s] sandbox 01a13e96-dea9-7332-ab2b-e9fb8d47de77
[  9.5s] clone: ok
[ 77.3s] setup: ok
[ 14.1s] selftest: ok
[  7.7s] grade: ok
```

`run.py` exit code: **0**. Verdict: **PASS** (all six gates).

Self-test kill-rate lines:

```
mutant lookahead-shift: FAIL (expected) -- killed by gate: G2_final_equity_oracle
mutant lookahead-signal: FAIL (expected) -- killed by gate: G3_sharpe_consistency
mutant sharpe-tamper: FAIL (expected) -- killed by gate: G3_sharpe_consistency
mutant equity-tamper: FAIL (expected) -- killed by gate: G2_final_equity_oracle
mutant mdd-tamper: FAIL (expected) -- killed by gate: G4_max_drawdown
mutant fixture-drift: FAIL (expected) -- killed by gate: G1_fixture_integrity
mutant cost-tamper: FAIL (expected) -- killed by gate: G6_schema_sanity
mutant returns-drift: FAIL (expected) -- killed by gate: G3_sharpe_consistency
mutant short-history: FAIL (expected) -- killed by gate: G6_schema_sanity
mutant tiny-figure: FAIL (expected) -- killed by gate: G6_schema_sanity
kill rate: 10/10 (100%)
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
G2_final_equity_oracle: PASS  artifact final_equity 0.9470302914 vs reference 0.9470302914
                              (relative deviation 0.000e+00, limit 1e-03)
G3_sharpe_consistency:  PASS  metrics.json sharpe 0.0365365875 vs recomputed from
                              returns.csv 0.0365365875; |diff| 3.109e-15, limit 1e-06
G4_max_drawdown:        PASS  metrics.json max_drawdown 0.4177213784 vs recomputed
                              0.4177213784; |diff| 2.933e-12, limit 1e-06
G5_lookahead_control:   PASS  reference final_equity shift 1 = 0.9470302914,
                              shift 2 = 0.6762990012 (differ by 2.859e-01, limit 1e-09)
failed_gates: []
```

Summary line:

```
run: SUMMARY verdict=PASS final_equity=0.9470302914437041 (reference 0.9470302914437041) sharpe=0.036536587479012825 max_drawdown=0.4177213784209337 n_trades=101.0 n_days=2517.0 failed_gates=[]
```

Sandbox cleanup: `run.py` printed
`sandbox 01a13e96-dea9-7332-ab2b-e9fb8d47de77 killed and confirmed gone`,
and `sbx list` no longer lists the id.

## Run B — sandbox `01a13e98-e462-70e1-b528-d1801f8ad782`

Per-step timing lines:

```
[  8.2s] sandbox 01a13e98-e462-70e1-b528-d1801f8ad782
[ 12.0s] clone: ok
[ 83.8s] setup: ok
[ 15.0s] selftest: ok
[  7.3s] grade: ok
```

`run.py` exit code: **0**. Verdict: **PASS** (all six gates).

Self-test kill-rate lines: identical to Run A (10/10, 100 %); determinism
PASS; judge integrity PASS; selftest PASS.

Summary line: identical to Run A.

Sandbox cleanup: `run.py` printed
`sandbox 01a13e98-e462-70e1-b528-d1801f8ad782 killed and confirmed gone`,
and `sbx list` no longer lists the id.

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
| kill rate | 10/10 (100 %) | 10/10 (100 %) |
| determinism | PASS | PASS |
| judge integrity | PASS | PASS |
| `run.py` exit code | 0 | 0 |
| clone wall time | 9.5 s | 12.0 s |
| setup wall time (fresh install) | 77.3 s | 83.8 s |
| selftest wall time | 14.1 s | 15.0 s |
| grade wall time | 7.7 s | 7.3 s |

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
kill + confirm) with exit code 0 and an all-gates-pass verdict.
