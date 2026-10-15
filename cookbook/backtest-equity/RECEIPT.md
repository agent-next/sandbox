# RECEIPT — `cookbook/backtest-equity/`

Real command output from two fresh sandbox runs of the one-command demo
(`run.py`), recorded by the builder agent on 2026-10-15 at commit `2667d46`
(`fix(cookbook): confirm sandbox cleanup before claiming it`), after the lead's
independent acceptance review of PR #79 was fixed (round 2). Both runs created
a fresh sandbox, cloned this repo at `--ref sbx/demo-backtest-equity-f7`, ran
`judge/setup.sh` → `judge/selftest.sh` → `judge/grade.sh examples/good
--seed 42`, and killed the sandbox, confirming with `sbx list` that the id
was gone.

Command (from outside the repo, exactly as a user runs it):

```bash
python3 cookbook/backtest-equity/run.py --ref sbx/demo-backtest-equity-f7
```

## Run A — sandbox `01a141a5-1384-7032-b770-7e2ac3a9c35b`

Per-step timing lines printed by `run.py`:

```
[  5.1s] sandbox 01a141a5-1384-7032-b770-7e2ac3a9c35b
[  14.9s] clone: ok
[  88.8s] setup: ok
[  11.3s] selftest: ok
[   5.3s] grade: ok
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
                              returns.csv 0.0365365875 (mean/std*sqrt(252)); |diff| 3.109e-15, limit 1e-06
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
`sandbox 01a141a5-1384-7032-b770-7e2ac3a9c35b killed and confirmed gone`,
and `sbx list` no longer lists the id.

## Run B — sandbox `01a141a7-9eb2-71a2-8f9c-1f4f593024d7`

Per-step timing lines:

```
[  11.7s] sandbox 01a141a7-9eb2-71a2-8f9c-1f4f593024d7
[  15.2s] clone: ok
[ 119.8s] setup: ok
[  12.7s] selftest: ok
[   7.7s] grade: ok
```

`run.py` exit code: **0**. Verdict: **PASS** (all six gates).

Self-test kill-rate lines: identical to Run A (11/11, 100 %); determinism
PASS; judge integrity PASS; selftest PASS.

Summary line: identical to Run A.

Sandbox cleanup: `run.py` printed
`sandbox 01a141a7-9eb2-71a2-8f9c-1f4f593024d7 killed and confirmed gone`,
and `sbx list` no longer lists the id.

## What the lead-review fixes changed (round 2, measured)

- **Cleanup confirmation can no longer pass vacuously (the MAJOR finding).**
  `run.py` used to discard `sbx list`'s exit code and then search the combined
  stdout+stderr for the sandbox id, so a gateway 5xx during cleanup left the
  id missing from what was really error text: the check passed, `run.py`
  printed `killed and confirmed gone` and exited 0 with the sandbox possibly
  still running. Measured before the fix, with the lead's probe (a stub `sbx`
  on `PATH` whose `kill` and `list` both exit 2 with a `gateway 503` message
  while create/exec/grade succeed):

  ```
  WARNING: sbx kill exit 2: sbx: ConnectionError: gateway 503 during kill
  sandbox sandbox 01STUB0000-0000-0000-0000-000000000000 killed and confirmed gone
  EXIT=0
  ```

  After the fix, the same probe exits **2** and names the id:

  ```
  WARNING: sbx kill exit 2: sbx: ConnectionError: gateway 503 during kill
  could not confirm sandbox sandbox 01STUB0000-0000-0000-0000-000000000000 is gone: sbx list exit 2: sbx: ConnectionError: gateway 503 during list
  EXIT=2
  ```

  The id is now searched for only in a listing that exited 0 (never inside
  error text); a listing that cannot be obtained, or that still shows the id,
  exits 2; and a kill that failed while a good listing proves the id is gone
  is reported as exactly that, not as a confirmed kill.
- **The confirmation is real against the live API.** A probe sandbox created
  with `sbx create --timeout-min 30` appeared in `sbx list` while alive
  (exactly one row), and after `sbx kill <id>` the id was absent from
  `sbx list` — so "not in the listing" really means "gone", in both
  directions.
- **SPEC.md gate attributions corrected to the measured verdicts**
  (`judge/grade.sh` on each mutant, `--seed 42`): `lookahead-shift` is killed
  by `G2_final_equity_oracle` (it said G5), `cost-tamper` by
  `G6_schema_sanity` (it said G2/G3). `judge/mutants.py`, `selftest.sh` and
  the kill lines above already agreed.
- **README's one-command block now states the seed** (`--seed 42`, the
  default `run.py` passes to `grade.sh`), matching the Results heading and
  the "Without the sbx CLI" block, as the independent reproduction asked.

For round 1 (G6 rejects `lookahead_shift 0`; the demo video re-cut; the
eleventh mutant), see `git log` and the previous RECEIPT (commit `0b2eaf5`);
every graded number is unchanged by both rounds.

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
| sandbox create wall time | 5.1 s | 11.7 s |
| clone wall time | 14.9 s | 15.2 s |
| setup wall time (fresh install) | 88.8 s | 119.8 s |
| selftest wall time | 11.3 s | 12.7 s |
| grade wall time | 5.3 s | 7.7 s |

The two runs agree on every graded number to full double precision. Wall
times differ between runs (and are slower late at night than the round-1
runs' 40–43 s setup: the shared network and PyPI are the variable, the
pinned wheels and every graded number are not).

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
kill + confirm) with exit code 0 and an all-gates-pass verdict, at commit
`2667d46` (the head of the graded code; the only commit after it is the docs
commit that carries this RECEIPT, which touches no graded path).
