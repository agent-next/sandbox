# RECEIPT — notebook-exec-report

Real command output, pasted from two from-nothing runs of the demo's
one-command run (`python3 cookbook/notebook-exec-report/run.py --ref
sbx/demo-notebook-exec-report-f5`), each in its own **fresh agent-next
sandbox** created by `run.py` itself (clone + fresh `~/.judge-venv` inside
the sandbox, killed and confirmed gone at the end). Every block below is
verbatim terminal output; only the sandbox ids and wall times differ
between the runs.

Repo state: branch `sbx/demo-notebook-exec-report-f5`, commit `2dd95c0`,
local `sbx` CLI 0.0.1.

## Run 1 — fresh sandbox (run.py, exit 0, ~6.5 min total)

    run: [   3.3s] sbx create --timeout-min 30 -> exit 0
    run: sandbox 01a14081-69b5-7c32-8da1-f9a143698e26
    run: [   5.0s] git clone -> exit 0
    run: [ 137.2s] judge/setup.sh -> exit 0
    run: [ 221.8s] judge/selftest.sh -> exit 0
    selftest: grading known-good <sandbox-home>/notebook-demo-repo/cookbook/notebook-exec-report/examples/good/analysis.ipynb
    selftest: known-good PASSED all gates
    mutants: error-cell.ipynb  edit: 'assert len(df) == 1600'
    mutants: train-not-test.ipynb  edit: 'rmse_test = float(np.sqrt(np.mean((log_y[test_idx] - pred_lo'
    mutants: missing-figure.ipynb  edit: 'fig.tight_layout(); fig.savefig(FIGDIR / "coefficients.png",'
    mutants: nondeterministic-seed.ipynb  edit: 'rng = np.random.default_rng(SEED)'
    mutants: round-metric.ipynb  edit: '"rmse_test": round(rmse_test, 6),'
    mutants: stale-report.ipynb  edit: 'f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in metrics.ite'
    mutants: order-dependence.ipynb  edit: figures cell moved below the metrics cell
    mutants: wrote 7 mutants to /tmp/tmp.sRSCDSwfVW/mutants
    selftest: killed    error-cell (gate: execution; a cell failed during execution)
    selftest: killed    missing-figure (gate: figures; fewer than three figures were saved)
    selftest: killed    nondeterministic-seed (gate: determinism; two clean runs of the notebook disagree on rmse_test)
    selftest: killed    order-dependence (gate: execution; a cell failed during execution)
    selftest: killed    round-metric (gate: oracle; reported rmse_test disagrees with the independent refit)
    selftest: killed    stale-report (gate: report; report.html omits metric rmse_test)
    selftest: killed    train-not-test (gate: oracle; reported rmse_test disagrees with the independent refit)
    selftest: kill rate 7/7 = 100%
    selftest: determinism OK (two --seed 1 runs identical except timing)
    selftest: OK
    run: [  20.5s] judge/grade.sh examples/good/analysis.ipynb -> exit 0

Verdict JSON printed by the grading step:

    {
      "artifact": "examples/good/analysis.ipynb",
      "failed_gate": null,
      "gates": {
        "blind": {
          "median_blind": 0.29724770970267506,
          "ratio": 0.9933903285423452,
          "seeds": [1, 2, 3, 4, 5]
        },
        "determinism": {
          "dirs": ["runA", "runB"],
          "figures": 3,
          "html_identical": true,
          "rmse_test_diff": 0.0
        },
        "execution": { "cells_ok": true },
        "figures": {
          "bytes": { "coefficients.png": 37072, "pred_vs_obs.png": 58534,
                     "residuals.png": 44848 },
          "count": 3
        },
        "integrity": { "clean": true },
        "oracle": {
          "coef_recovery": 0.018015198777351894,
          "n_test": 320,
          "n_train": 1280,
          "r2_test": 0.8778951574041314,
          "rmse_test": 0.29528270224052927,
          "rmse_train": 0.3013676435551875
        },
        "report": { "metrics_rendered": true }
      },
      "metrics": {
        "dataset_sha256": "83029ea238f4cda3b2eec9e5a9f6518547f8edb226574520a3785ff7cdae799c",
        "n_test": 320,
        "n_train": 1280,
        "r2_test": 0.877895157,
        "rmse_test": 0.295283
      },
      "passed": true,
      "reason": null,
      "timing": { "first_run_s": 7.53, "total_s": 17.28 }
    }
    run: SUMMARY passed=True rmse_test=0.295283 (refit 0.29528270224052927) r2_test=0.877895157 coef_recovery=0.018015198777351894 blind_ratio=0.9933903285423452 figures=3
    run: killed and confirmed gone: 01a14081-69b5-7c32-8da1-f9a143698e26

(figures gate bytes above condensed to one line; everything else verbatim)

## Run 2 — fresh sandbox (run.py, exit 0, ~5.1 min total)

    run: [   2.3s] sbx create --timeout-min 30 -> exit 0
    run: sandbox 01a14087-889a-7221-bb50-d4fb8e742d05
    run: [   4.0s] git clone -> exit 0
    run: [  90.1s] judge/setup.sh -> exit 0
    run: [ 185.3s] judge/selftest.sh -> exit 0
    selftest: known-good PASSED all gates
    selftest: killed    error-cell (gate: execution; a cell failed during execution)
    selftest: killed    missing-figure (gate: figures; fewer than three figures were saved)
    selftest: killed    nondeterministic-seed (gate: determinism; two clean runs of the notebook disagree on rmse_test)
    selftest: killed    order-dependence (gate: execution; a cell failed during execution)
    selftest: killed    round-metric (gate: oracle; reported rmse_test disagrees with the independent refit)
    selftest: killed    stale-report (gate: report; report.html omits metric rmse_test)
    selftest: killed    train-not-test (gate: oracle; reported rmse_test disagrees with the independent refit)
    selftest: kill rate 7/7 = 100%
    selftest: determinism OK (two --seed 1 runs identical except timing)
    selftest: OK
    run: [  24.0s] judge/grade.sh examples/good/analysis.ipynb -> exit 0
    run: SUMMARY passed=True rmse_test=0.295283 (refit 0.29528270224052927) r2_test=0.877895157 coef_recovery=0.018015198777351894 blind_ratio=0.9933903285423452 figures=3
    run: killed and confirmed gone: 01a14087-889a-7221-bb50-d4fb8e742d05

The full verdict JSON of run 2 is byte-identical to run 1's (including the
`metrics` and every gate number); a diff of the two run logs differs only
in the sandbox ids, the mutants temp-dir name, and the per-step wall times.

A third confirming run at the final branch head `0691b41` (after the
media/REPRODUCE commits; `run.py` and the judge are unchanged by them)
also exited 0 with the same SUMMARY line and identical numbers:

    run: [   3.8s] sbx create --timeout-min 30 -> exit 0
    run: sandbox 01a140b6-6fff-7b91-87d7-88cb1d69c2a3
    run: [   8.7s] git clone -> exit 0
    run: [ 151.8s] judge/setup.sh -> exit 0
    run: [ 250.4s] judge/selftest.sh -> exit 0
    run: [  27.6s] judge/grade.sh examples/good/analysis.ipynb -> exit 0
    run: SUMMARY passed=True rmse_test=0.295283 (refit 0.29528270224052927) r2_test=0.877895157 coef_recovery=0.018015198777351894 blind_ratio=0.9933903285423452 figures=3
    run: killed and confirmed gone: 01a140b6-6fff-7b91-87d7-88cb1d69c2a3
    EXIT=0

## Both runs side by side

| quantity | run 1 | run 2 |
|---|---|---|
| `sbx create` + clone | 3.3 s + 5.0 s | 2.3 s + 4.0 s |
| `judge/setup.sh` | exit 0, 137.2 s | exit 0, 90.1 s |
| `judge/selftest.sh` | exit 0, 221.8 s, kill rate 7/7 = 100 % | exit 0, 185.3 s, kill rate 7/7 = 100 % |
| `judge/grade.sh` verdict | passed (exit 0, 20.5 s) | passed (exit 0, 24.0 s) |
| notebook `rmse_test` | 0.295283 | 0.295283 |
| oracle refit `rmse_test` | 0.29528270224052927 | 0.29528270224052927 |
| `r2_test` | 0.877895157 | 0.877895157 |
| coefficient recovery | 0.018015198777351894 | 0.018015198777351894 |
| blind ratio (median 0.297248) | 0.9933903285423452 | 0.9933903285423452 |
| figure bytes (3 files) | 37072 / 58534 / 44848 | 37072 / 58534 / 44848 |
| dataset sha256 | 83029ea2…dae799c | 83029ea2…dae799c |
| sandbox killed + confirmed gone | yes | yes |
| `run.py` exit code | 0 | 0 |

Tool versions installed by `judge/setup.sh` in these runs: recorded in
`judge/VERSIONS.txt` (python3 3.12.15, numpy 2.5.3, scikit-learn 1.9.1,
pandas 3.0.6, matplotlib 3.11.2, nbclient 0.11.0, ipykernel 7.4.0).

## Deviations

- The two runs hit different sandbox instances with different I/O speed
  (setup 90 s vs 137 s); every graded number is identical, and the
  wall-time spread is the reason `run.py` prints per-step timings.
- The `[IPKernelApp] WARNING | Kernel is running over TCP without
  encryption` lines on stderr are ipykernel's notice when no key file is
  provisioned; inside a single-use disposable sandbox the loopback
  transport is acceptable, and the warning does not affect grading.
- numpy's PRNG defines the split (stated as a deviation in SPEC.md:
  reimplementing PCG64 + Lemire shuffle bit-for-bit in the stdlib was
  rejected as fragile); everything after the split is judge-owned code.
- Two transitive pins sit close to, but before, the two-week cutoff
  (ipykernel 7.4.0 and fonttools 4.66.1, both 2026-09-29); every pin in
  `judge/requirements.txt` is ≤ 2026-09-30, enforced by `judge/genlock.py`.
- The executed notebook's `image/png` outputs are produced by
  `matplotlib_inline.backend_inline.set_matplotlib_formats("png")` — the
  documented headless equivalent of `%matplotlib inline`. The plain Agg
  backend registers no figure display hook, so figures render into the
  notebook only with this call (found by the self-test: the first judge
  draft failed its own figures gate).
- History: an earlier run of `run.py` at commit `90d743c` failed — the
  client-side subprocess timeout (120 s) was shorter than the sandbox-side
  `--timeout`, so `judge/setup.sh` was cut off mid-install; fixed in
  `2dd95c0` (local timeout = sandbox timeout + 120 s margin on every
  step).
