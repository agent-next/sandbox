# SPEC — `cookbook/backtest-equity/`

An agent works on a real quant problem inside a disposable agent-next sandbox:
backtest a 12/26 dual-momentum strategy on pinned OHLCV price history, report
the equity curve, maximum drawdown and Sharpe ratio — where a judge it cannot
fool (a blind independent reference implementation, a Sharpe self-consistency
check, and a lookahead negative control) decides whether the numbers are right.

## Goal

Produce a backtest of the 12/26 momentum strategy on the pinned OHLCV
fixture with 10 bps transaction costs, written as one artifact the agent
designs and fixes itself in the sandbox. The judge must be able to decide
correctness **without trusting any code in the artifact**.

## Non-goals

- Live data, data quality beyond schema validation, missing-value policy,
  corporate-action adjustment. The fixture is clean and pinned.
- Optimality of the strategy, parameter search, or comparison against
  other strategies. There is exactly one parameter set (12/26, 10 bps).
- Trading realism beyond proportional costs: no slippage model, market
  impact, margin, borrow, or position limits.
- Style of the agent's engine: any vectorized or looped implementation is
  fine as long as the output is correct and self-consistent.

## Artifact

A directory containing (the file graded by `judge/grade.sh <artifact>`):

- `backtest.py` — the agent's own vectorized engine (readable Python;
  the judge never executes it — it imports nothing from it);
- `ohlcv.csv` — the pinned daily OHLCV fixture (copy of the checked-in
  `tools/data/ohlcv.parquet` exported by the demo's own `tools/make_fixture.py`,
  or the parquet itself with a loader the agent writes);
- `returns.csv` — one row per trading day: `date,ret` where `ret` is the
  strategy's net daily return;
- `metrics.json` — the reported metrics, at minimum:
  `final_equity`, `total_return`, `n_days`, `n_trades`, `max_drawdown`,
  `sharpe`, `volatility_ann`, `mean_daily_ret`, `risk_free_rate`,
  `cost_bps`, `lookahead_shift` (the position-signal lag actually used;
  see gates);
- `equity.png` — the equity curve (self-describing: title/axes with units).

The known-good example was produced by `tools/make_fixture.py` and a clean
reference run (see `examples/good/`); the gates below apply to *any* artifact
the agent produces.

## Judge gates (`judge/grade.sh <artifact> [--seed N] [--json out.json]`)

All gates are numeric and deterministic. Exit 0 only if every gate passes.

- **G1 fixture integrity**: the artifact's price history matches the pinned
  reference fixture (the judge ships a sha256 manifest of the exact
  OHLCV values it was built from; any value that differs fails). This is the
  **no-lookahead data gate**: prices are the one input that must not drift.
- **G2 final-equity oracle**: the judge re-implements the whole backtest
  independently (its own code path, not the artifact's — see
  `judge/reference.py`) and requires `|final_equity_artifact −
  final_equity_reference| / final_equity_reference ≤ 0.1 %`.
  The reference is blind to the artifact.
- **G3 Sharpe self-consistency**: the judge recomputes Sharpe from the
  artifact's own `returns.csv` and requires
  `|sharpe_direct − sharpe_from_csv| < 1e-6`, where
  `sharpe_from_csv = mean(ret) / std(ret, ddof=1) × sqrt(252)` and
  `std(ret)` uses the sample std. This forces the artifact's CSV to be
  the same series its metrics claim.
- **G4 max drawdown**: the judge recomputes max drawdown from the artifact's
  own equity series and requires `|mdd_artifact − mdd_csv| ≤ 1e-6` (absolute,
  on a normalised 0..1 equity curve).
- **G5 lookahead negative control (must-be-different)**: the artifact
  declares `lookahead_shift` (the number of bars the signal is lagged when
  sizing positions). The judge runs its own reference with the signal
  shifted by **one extra bar** (`shift = lookahead_shift + 1`) and requires
  the resulting final equity to **differ** from the reference with the
  declared shift by more than `1e-9` (relative). An artifact that "works"
  under both a 1-bar and a 2-bar lag is not reacting to its signal lag —
  it is not really trading the signal.
- **G6 schema sanity**: `returns.csv` has ≥ 252 rows (one trading year),
  dates strictly increasing, no NaNs; `equity.png` is a valid PNG ≥ 800×600;
  `metrics.json` parses and carries the keys listed in Artifact with
  `cost_bps = 10.0`, `lookahead_shift ≥ 0`.

Violating any gate fails with the offending numbers printed.

## Acceptance oracle (independent of "it ran")

1. **Blind reference implementation**: `judge/reference.py` computes
   final equity from the pinned fixture with an independent code path
   (loop-based, deliberately written differently from the artifact's
   vectorized engine). Both sides must agree within 0.1 % — this catches
   wrong signal alignment, off-by-one rebalancing, and cost leaks.
2. **Sharpe second way**: the 1e-6 self-consistency gate (G3) plus G4.
3. **Lookahead negative control**: G5 above, plus the self-test runs a
   scripted lookahead mutant that the judge must flag as a *different*
   equity.
4. **Determinism**: the fixture is pinned and all randomness (if any) is
   seeded; two `grade.sh` runs with the same seed produce byte-identical
   verdict JSON (excluding `timing`). The self-test checks this.

## Self-test (`judge/selftest.sh`)

- The known-good example passes all gates.
- ≥ 5 known-bad single-edit mutants of the good artifact each fail ≥ 1
  gate; mutants generated by `judge/mutants.py` (one textual edit each),
  including:
  `lookahead-shift` (declares a 2-bar lag → G5 must-be-different fails),
  `sharpe-tamper` (reports a Sharpe that disagrees with the CSV → G3),
  `equity-tamper` (reports a final equity 20 % off the reference → G2),
  `mdd-tamper` (reports max drawdown that disagrees with the CSV → G4),
  `fixture-drift` (one pinned price altered → G1),
  `cost-tamper` (costs reported as 0 bps → G2/G3).
- Kill rate ≥ 90 % printed by the self-test; exit non-zero otherwise.
- Determinism: two `grade.sh` runs with the same seed produce byte-identical
  verdict JSON; checked by the self-test on every run.

## Judge-integrity rule

The artifact under test is copied to a temp dir before grading; the judge
compares `sha256` of its own `judge/` tree before and after every grade and
fails closed if anything changed.

## Out of scope for the judge

- Whether the strategy is *good* (Sharpe > 0 is not required — the
  fixture may produce any sign).
- Comments or claims in the artifact's code.
- Runtime of the agent's engine (only the judge's own runtime matters).

## Tools (pinned by `judge/setup.sh`)

- Python ≥ 3.10, standard library only for the judge math and the fixture
  manifest (a pinned `pandas`/`numpy` pair is installed for PNG and CSV
  handling, hashes pinned via `pip --require-hashes`; the reference
  implementation itself uses only stdlib so the oracle stays independent of
  the artifact's stack).
- **python-dateutil 2.9.0.post0**, **numpy 2.5.4**, **pandas 3.0.4**,
  **matplotlib 3.9.4** (all sha256-pinned wheels), installed idempotently
  into `$HOME/.venvs/backtest-equity`.
