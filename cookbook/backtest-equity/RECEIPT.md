# RECEIPT — `cookbook/backtest-equity/`

Real command output from two fresh sandbox runs of the one-command demo
(`run.py`), recorded by the builder agent on 2026-10-15. Both runs used a
fresh sandbox created by `run.py` itself, with `--ref sbx/demo-backtest-equity-f1`
(the branch this demo lives on), `--seed 42` for the graded verdict, and the
sandbox killed and confirmed gone after each run.

## Run 1 — sandbox `01a13e8a-a5e2-7d91-aaa7-f7027d5d4175`

Command (from outside the repo, in a fresh sandbox created by `run.py`):

```bash
python3 cookbook/backtest-equity/run.py --ref sbx/demo-backtest-equity-f1
```

Per-step timing lines printed by `run.py`:

```
[  3.9s] sandbox 01a13e8a-a5e2-7d91-aaa7-f7027d5d4175
[   7.1s] clone: ok
[  49.2s] setup: ok
[   7.8s] selftest: ok
[   4.9s] grade: ok
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

Summary line:

```
run: SUMMARY verdict=PASS final_equity=0.9470302914437041 (reference 0.9470302914437041) sharpe=0.036536587479012825 max_drawdown=0.4177213784209337 n_trades=101.0 n_days=2517.0 failed_gates=[]
```

Sandbox cleanup: `sbx list` no longer lists `01a13e8a-…`; `run.py` printed
`sandbox 01a13e8a-a5e2-7d91-aaa7-f7027d5d4175 killed and confirmed gone`.

## Run 2 — sandbox `01a13e8c-4118-7403-be33-f74a668365b2`

Command:

```bash
python3 cookbook/backtest-equity/run.py --ref sbx/demo-backtest-equity-f1
```

Per-step timing lines:

```
[  4.1s] sandbox 01a13e8c-4118-7403-be33-f74a668365b2
[   7.8s] clone: ok
[  43.7s] setup: ok
[   8.3s] selftest: ok
[   5.2s] grade: ok
```

`run.py` exit code: **0**. Verdict: **PASS** (all six gates).

Self-test kill-rate lines: identical to Run 1 (10/10, 100 %).

Summary line:

```
run: SUMMARY verdict=PASS final_equity=0.9470302914437041 (reference 0.9470302914437041) sharpe=0.036536587479012825 max_drawdown=0.4177213784209337 n_trades=101.0 n_days=2517.0 failed_gates=[]
```

Sandbox cleanup: `sbx list` no longer lists `01a13e8c-…`; `run.py` printed
`sandbox 01a13e8c-4118-7403-be33-f74a668365b2 killed and confirmed gone`.

## Side-by-side key numbers

| quantity | Run 1 | Run 2 |
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
| clone wall time | 7.1 s | 7.8 s |
| setup wall time (fresh install) | 49.2 s | 43.7 s |
| selftest wall time | 7.8 s | 8.3 s |
| grade wall time | 4.9 s | 5.2 s |

The two runs agree on every graded number to full double precision. Wall
times differ by a few seconds per step, as expected for a shared CI network.

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

## Deviations

None. Both runs completed every step (clone → setup → selftest → grade →
kill + confirm) with exit code 0 and an all-gates-pass verdict.
