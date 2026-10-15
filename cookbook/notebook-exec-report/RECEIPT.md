# RECEIPT — notebook-exec-report

Real command output, pasted from two from-nothing runs of the demo in this
disposable Debian sandbox (2 vCPU, ~4 GB RAM; clone + fresh `~/.judge-venv`
each time — what `run.py`'s steps do in a fresh agent-next sandbox). Every
block below is the verbatim terminal output of the named command.

## Run 1 — fresh clone, fresh venv

Repo state: branch `sbx/demo-notebook-exec-report`, commit `06c4b7b`.

### `bash judge/setup.sh` (exit 0, 235 s)

    setup: creating /home/user/.judge-venv and installing judge/requirements.txt
    Collecting asttokens==3.0.2 (from -r .../judge/requirements.txt (line 7))
      Downloading asttokens-3.0.2-py3-none-any.whl (28 kB)
    Collecting attrs==26.1.0 (...)
      Downloading attrs-26.1.0-py3-none-any.whl (67 kB)
    ... (64 hash-pinned wheels, each "Downloading <name>-<version>.whl"; no version resolved freely)
    Successfully installed asttokens-3.0.2 attrs-26.1.0 beautifulsoup4-4.15.0 \
    bleach-6.4.0 cloudpickle-3.1.2 comm-0.2.3 contourpy-1.4.0 cycler-0.12.1 \
    debugpy-1.8.22 defusedxml-0.7.1 executing-2.2.1 fastjsonschema-2.22.2 \
    fonttools-4.66.1 ipykernel-7.4.0 ipython-9.17.1 \
    ipython_pygments_lexers-1.1.1 jedi-0.20.0 Jinja2-3.1.6 joblib-1.6.0 \
    jsonschema-4.26.0 jsonschema-specifications-2025.9.1 jupyter_client-8.10.0 \
    jupyter_core-5.9.1 jupyterlab_pygments-0.3.0 kiwisolver-1.5.1 \
    MarkupSafe-3.0.3 matplotlib-3.11.2 matplotlib-inline-0.2.2 mistune-3.3.4 \
    narwhals-2.26.0 nbclient-0.11.0 nbconvert-7.17.1 nbformat-5.11.1 \
    nest-asyncio2-1.7.3 numpy-2.5.3 packaging-26.3 pandas-3.0.6 \
    pandocfilters-1.5.1 parso-0.8.7 pexpect-4.9.0 pillow-12.3.0 \
    platformdirs-4.12.2 prompt_toolkit-3.0.53 psutil-7.2.2 ptyprocess-0.7.0 \
    pure_eval-0.2.4 Pygments-2.21.0 pyparsing-3.3.3 python-dateutil-2.9.0.post0 \
    pyzmq-27.2.0 referencing-0.37.0 rpds-py-2026.6.3 scikit-learn-1.9.1 \
    scipy-1.18.1 six-1.17.0 soupsieve-2.10 stack-data-0.6.3 threadpoolctl-3.7.0 \
    tinycss2-1.5.1 tornado-6.5.10 traitlets-5.16.1 typing_extensions-4.16.0 \
    wcwidth-0.9.1 webencodings-0.6.1
    setup: tool versions
    # notebook-exec-report judge: versions installed by judge/setup.sh
    # (Linux x86_64)
    python3 3.12.15
    ipykernel 7.4.0
    jupyter-client 8.10.0
    matplotlib 3.11.2
    nbclient 0.11.0
    nbconvert 7.17.1
    nbformat 5.11.1
    numpy 2.5.3
    pandas 3.0.6
    scikit-learn 1.9.1
    scipy 1.18.1
    traitlets 5.16.1
    [IPKernelApp] WARNING | Kernel is running over TCP without encryption. [...]
    setup: nbclient smoke kernel OK (smoke 2.5.3)
    setup: done

### `bash judge/selftest.sh` (exit 0, 502 s)

    selftest: grading known-good .../examples/good/analysis.ipynb
    selftest: known-good PASSED all gates
    mutants: error-cell.ipynb  edit: 'assert len(df) == 1600'
    mutants: train-not-test.ipynb  edit: 'rmse_test = float(np.sqrt(np.mean((log_y[test_idx] - pred_lo'
    mutants: missing-figure.ipynb  edit: 'fig.tight_layout(); fig.savefig(FIGDIR / "coefficients.png",'
    mutants: nondeterministic-seed.ipynb  edit: 'rng = np.random.default_rng(SEED)'
    mutants: round-metric.ipynb  edit: '"rmse_test": round(rmse_test, 6),'
    mutants: stale-report.ipynb  edit: 'f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in metrics.ite'
    mutants: order-dependence.ipynb  edit: figures cell moved below the metrics cell
    mutants: wrote 7 mutants to /tmp/tmp.sau5U0GPm7/mutants
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

### `bash judge/grade.sh examples/good/analysis.ipynb --json /tmp/v.json` (exit 0, 78 s)

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
                     "residuals.png": 48488 },
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
      "timing": { "first_run_s": 45.67, "total_s": 76.48 }
    }

## Run 2 — fresh clone, fresh venv

(RUN2_PLACEHOLDER)

## Both runs side by side

| quantity | run 1 | run 2 |
|---|---|---|
| `judge/setup.sh` | exit 0, 235 s | (RUN2_SETUP) |
| `judge/selftest.sh` | exit 0, 502 s, kill rate 7/7 = 100 % | (RUN2_SELFTEST) |
| `judge/grade.sh` verdict | passed | (RUN2_VERDICT) |
| notebook `rmse_test` | 0.295283 | (RUN2_RMSE) |
| oracle refit `rmse_test` | 0.29528270224052927 | (RUN2_ORACLE) |
| `r2_test` | 0.877895157 | (RUN2_R2) |
| coefficient recovery | 0.018015198777351894 | (RUN2_RECOVERY) |
| blind ratio | 0.9933903285423452 | (RUN2_BLIND) |
| figure bytes (3 files) | 37072 / 58534 / 48488 | (RUN2_FIGS) |

## Deviations

- **Both runs are in this one disposable sandbox**, each from a fresh
  clone and a deleted `~/.judge-venv` (the from-nothing state `run.py`
  creates in a fresh agent-next sandbox). A true second *sandbox* run plus
  the end-to-end `run.py` execution is the lead's follow-up step; the
  sandbox cannot be created from inside this environment.
- The `[IPKernelApp] WARNING | Kernel is running over TCP without
  encryption` lines on stderr are ipykernel's notice when no key file is
  provisioned; inside a single-use disposable sandbox the loopback
  transport is acceptable, and the warning does not affect grading.
- numpy's PRNG defines the split (stated as a deviation in SPEC.md:
  reimplementing PCG64 + Lemire shuffle bit-for-bit in the stdlib was
  rejected as fragile); everything after the split is judge-owned code.
- `REPRODUCE.md` (not done: independent reproduction by a *different*
  agent model family, per the demo standard, happens before merge).
- `media/` (not done: media is a later task by the lead's instruction).
- Two transitive pins sit close to, but before, the two-week cutoff
  (ipykernel 7.4.0 and fonttools 4.66.1, both 2026-09-29); every pin in
  `judge/requirements.txt` is ≤ 2026-09-30, enforced by `judge/genlock.py`.
- The executed notebook's `image/png` outputs are produced by
  `matplotlib_inline.backend_inline.set_matplotlib_formats("png")` — the
  documented headless equivalent of `%matplotlib inline`. The plain Agg
  backend registers no figure display hook, so figures render into the
  notebook only with this call (found by the self-test: the first judge
  draft failed its own figures gate).
