# REPRODUCE — `cookbook/backtest-equity/`

An independent agent run reproduced this demo on 2026-10-15, following **only**
`cookbook/backtest-equity/README.md` (never `SPEC.md`, `judge/*.py`, `run.py`
internals or `RECEIPT.md` while measuring), in a **fresh sandbox** created for
this run. Ref: `sbx/demo-backtest-equity-f1` (the branch the demo lives on;
`main` does not contain it — see README findings). Clone commit:
`2822237` (`wip: agent demo-backtest-equity-f1 (timeout)`), the branch tip on
`origin`. `RECEIPT.md` was read only after all numbers were captured, for the
comparison table below. The `sbx` CLI was already present (version `0.0.1`) at
`$HOME/.local/bin/sbx`; `SBX_API_KEY` came from the environment.

## Exact commands run

Manual reproduction (README's "Without the sbx CLI" steps, inside the fresh
sandbox `01a13e8f-a084-72f3-a246-8edb6c349cf2`):

```bash
# from the host: create a fresh sandbox and record the id
sbx create --timeout-min 45                     # -> 01a13e8f-a084-72f3-a246-8edb6c349cf2

# inside the sandbox: clone at the branch, then run the README's documented steps
sbx exec <id> -- bash -lc '
  mkdir -p ~/work && cd ~/work &&
  git clone --depth 1 --branch sbx/demo-backtest-equity-f1 \
      https://github.com/agent-next/sandbox.git repo &&
  cd repo/cookbook/backtest-equity &&
  bash judge/setup.sh &&
  bash judge/selftest.sh &&
  bash judge/grade.sh examples/good --seed 42 --json verdict.json'

# from the host: kill and confirm
sbx kill 01a13e8f-a084-72f3-a246-8edb6c349cf2
sbx list
```

One-command run (README's "One-command run" section, from the repo root on the
host):

```bash
python3 cookbook/backtest-equity/run.py                                    # README default --ref main
python3 cookbook/backtest-equity/run.py --ref sbx/demo-backtest-equity-f1  # the ref that actually holds the demo
```

## Raw verdict numbers measured

Verdict: **PASS** — all six gates pass. `grade.sh` exit code `0`.

| gate | result | detail |
|---|---|---|
| G1 fixture integrity | PASS | `ohlcv.csv` sha256 `227517225b7f4978c8c5c4092d40a91af9a5cbd82859c82c7516f92efb881821` == pinned fixture |
| G2 final equity vs oracle | PASS | artifact `0.9470302914` vs reference `0.9470302914` (relative deviation `0.000e+00`, limit `1e-03`) |
| G3 Sharpe consistency | PASS | `0.0365365875` vs recomputed `0.0365365875`, `|diff| 3.109e-15` (limit `1e-06`) |
| G4 max drawdown | PASS | `0.4177213784` vs recomputed `0.4177213784`, `|diff| 2.933e-12` (limit `1e-06`) |
| G5 lookahead control | PASS | reference final equity shift 1 `0.9470302914` vs shift 2 `0.6762990012` (differ by `2.859e-01`) |
| G6 schema sanity | PASS | 2517 return rows (2014-01-02..2023-08-25), dates strictly increasing, no NaNs; `equity.png` 2000x1400; metrics keys ok, `cost_bps 10.0`, `lookahead_shift 1.0` |

Key metrics (from the verdict JSON `metrics`):

| quantity | value |
|---|---|
| final_equity | `0.9470302914437041` |
| total_return | `-0.0529697085562959` (−5.3 %) |
| sharpe | `0.036536587479012825` |
| max_drawdown | `0.4177213784209337` (41.77 %) |
| n_trades | `101` |
| n_days | `2517` |
| volatility_ann | `0.1471606200700388` |
| reference final_equity | `0.9470302914437041` |
| reference sharpe | `0.03653658747901288` |

Self-test kill rate: **10/10 mutants = 100 %** (requirement ≥ 90 %), with
determinism PASS and judge-integrity PASS.

Tool versions printed by setup: Python `3.12`; numpy `2.2.6`; matplotlib
`3.9.4`; contourpy `1.4.0`; cycler `0.12.1`; fonttools `4.67.0`; kiwisolver
`1.5.1`; packaging `26.3`; pillow `12.3.0`; pyparsing `3.3.3`;
python-dateutil `2.9.0.post0`; six `1.17.0`.

> Note (builder, after this reproduction): `fonttools` was repinned
> `4.67.0` → `4.66.1` because `4.67.0` was published 2026-10-14, inside the
> standard's "nothing published in the last two weeks" window. `fonttools`
> is used only by the artifact's matplotlib PNG rendering, never by the
> judge (which is stdlib-only and reads `equity.png` only to size its IHDR),
> so no graded number can depend on it. The builder re-ran the full
> acceptance pipeline at the new pin (two fresh sandboxes, `RECEIPT.md`) and
> the verdicts and key numbers below were identical. The version line just
> quoted is what this reproduction observed at the old pin.

Wall times measured (Debian 12, 2 vCPU, Python 3.12.15):

| step | my wall time | README claim |
|---|---|---|
| `git clone --depth 1` | 3.6 s | 9 s |
| `judge/setup.sh` (fresh install) | 60.5 s | 60–90 s |
| `judge/selftest.sh` | 8.9 s | 10–15 s |
| `judge/grade.sh examples/good` | 0.64 s (verdict `timing.wall_s` 0.088) | 6–7 s |

`run.py --ref sbx/demo-backtest-equity-f1` per-step lines (its own overhead
included): sandbox 3.0 s, clone ok, setup ok, selftest ok, grade ok; exit 0;
verdict PASS; sandbox killed and confirmed gone.

## Comparison against RECEIPT.md

| quantity | mine | RECEIPT.md (Run 1 / Run 2) | within tolerance? |
|---|---|---|---|
| verdict | PASS | PASS / PASS | yes (exact) |
| final_equity | 0.9470302914437041 | 0.9470302914437041 / 0.9470302914437041 | yes — rel. dev. 0.000e+00 ≤ 0.1 % |
| reference final_equity | 0.9470302914437041 | 0.9470302914437041 / 0.9470302914437041 | yes (exact) |
| sharpe | 0.036536587479012825 | 0.036536587479012825 / 0.036536587479012825 | yes — \|diff\| 3.109e-15 < 1e-6 |
| max_drawdown | 0.4177213784209337 | 0.4177213784209337 / 0.4177213784209337 | yes — \|diff\| 2.933e-12 ≤ 1e-6 |
| n_trades | 101 | 101 / 101 | yes (exact) |
| n_days | 2517 | 2517 / 2517 | yes (exact) |
| kill rate | 10/10 (100 %) | 10/10 (100 %) / 10/10 (100 %) | yes (exact) |
| determinism | PASS | PASS / PASS | yes (exact) |
| judge integrity | PASS | PASS / PASS | yes (exact) |
| run.py exit code | 0 | 0 / 0 | yes (exact) |
| clone wall time | 3.6 s | 7.1 s / 7.8 s | n/a (timing) |
| setup wall time | 60.5 s | 49.2 s / 43.7 s | n/a (timing) |
| selftest wall time | 8.9 s | 7.8 s / 8.3 s | n/a (timing) |
| grade wall time | 0.64 s | 4.9 s / 5.2 s | n/a (timing) |

Every graded number agrees with `RECEIPT.md` to full double precision; only
wall times differ, as expected on a shared network. (The `grade` wall-time gap
is measurement scope: `RECEIPT.md` reports `run.py`'s grade step, which
includes the `sbx exec` round trip, while my 0.64 s is bare `grade.sh`.)

## README findings

- **The "One-command run" default ref is wrong for this branch.** The README
  states `--ref main` is the default ("Creates a sandbox ... clones the repo at
  `--ref` (default `main`)"). But the demo is **not on `main`** — it lives only
  on `sbx/demo-backtest-equity-f1`. I ran `run.py` with no `--ref` and it
  failed: `setup: FAILED rc=1` / `cd: backtest-demo-repo/cookbook/backtest-equity:
  No such file or directory` (exit 1). A cold-start agent that follows the
  README's default literally gets a failure until the demo is merged. Only
  `--ref sbx/demo-backtest-equity-f1` works. This should be called out, or the
  default should point at the branch until merge.
- **The "Without the sbx CLI" block omits the working directory.** It shows
  `bash judge/setup.sh` etc. without saying to `cd cookbook/backtest-equity`
  first; a fresh agent must infer the cwd. (Minor — the paths are obviously
  relative to the demo.)
- **`--seed 42` is not shown in the one-command block.** The block prints
  `python3 cookbook/backtest-equity/run.py` with no seed; the seed only appears
  in the "Without the sbx CLI" block and the Results heading. `run.py` hardcodes
  `--seed 42` internally, so the numbers are reproducible, but the README never
  states this in the one-command section — a reader cannot tell from the README
  alone which seed the one-command run uses.
- **README Results numbers all reproduce.** Final equity `0.9470302914`,
  Sharpe `0.0365365875` (to `3.1e-15`), max drawdown `0.4177213784` (to
  `2.9e-12`), lookahead shift-2 reference `0.6763`, kill rate 10/10 — all
  matched exactly.
- **Setup wall-time claim holds.** README's 60–90 s for a fresh `setup.sh`
  matched (60.5 s).

## Deviations

- **Ref used.** The README's default `--ref main` fails because the demo is
  unmerged; I used `--ref sbx/demo-backtest-equity-f1` for the working run (as
  `RECEIPT.md` itself did). Recorded above as a README finding, not a demo
  defect.
- **CLI install skipped.** The README's one-command block starts with
  `pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"`;
  `sbx` (`0.0.1`) was already installed at `$HOME/.local/bin/sbx`, so I used it
  rather than reinstalling. Behaviour is unaffected.
- **Clone commit is `2822237`, not `c00920c`.** The local checkout on the host
  is at `c00920c` (the `docs(cookbook): RECEIPT ...` commit), but that commit is
  **not pushed** to `origin`; cloning the branch yields `2822237`. This does not
  change the graded numbers, which match `RECEIPT.md` exactly.
- **Sandboxes created and all killed.** `01a13e8f-a084-72f3-a246-8edb6c349cf2`
  (manual reproduction, killed by me and confirmed gone via `sbx list`);
  `01a13e91-dfc0-7340-b581-2dd110329e14` (run.py `--ref main`, failed, auto-killed
  and confirmed gone by run.py); `01a13e92-632d-7b13-9226-e6a4bf563283` (run.py
  branch ref, PASS, auto-killed and confirmed gone by run.py). No sandbox was
  deleted by listing; each was deleted by the id this run created.
- **Manual `sbx create` vs `run.py`.** The manual reproduction used my own
  `sbx create --timeout-min 45` sandbox as instructed; the one-command path
  created its own. Both exercised the same demo steps.
