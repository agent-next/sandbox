# notebook-exec-report — a notebook a judge can re-run

An agent has to *produce analysis code that reproduces*, not just a
notebook that once ran: deliver `analysis.ipynb`, which loads a pinned
dataset, fits a scikit-learn ridge regression on the log of the target,
renders three figures and an HTML report, and prints its metrics as
tagged JSON. The judge executes the notebook **headless, top-to-bottom,
twice, on clean kernels** (nbclient), checks the execution counts are
sequential `1..N` (killing out-of-order and re-run notebooks), and then
refits the model itself — a stdlib Gaussian-elimination oracle, no
scikit-learn, no BLAS — requiring every reported number to match within
1e-6. A notebook whose metric only reproduces with hidden state, that
reports a train metric, drops a figure, or uses an unseeded split fails
with the offending numbers printed. A disposable sandbox is the right
place for this: the agent needs the pinned Jupyter/scikit-learn
toolchain and a throwaway filesystem to iterate in, and the graded
artifact is one small `.ipynb` it hands back.

## Results

Key numbers from the judge verdict (`examples/good/analysis.ipynb`,
seed 20261015; media/ ships the figures):

- **rmse_test (log scale)**: 0.295283 (independent refit 0.295283; limit
  ≤ 0.3040, agreement tolerance 1e-6)
- **r2_test**: 0.877895 (refit agreement 1e-9)
- **coefficient recovery** ‖ŵ−w_true‖/‖w_true‖: 0.0180 (limit ≤ 0.05)
- **blind-seed ratio**: 0.993 (limit ≤ 1.25)
- **split**: 1280 train / 320 test, dataset sha256 `83029ea2…dae799c`
- **Self-test kill rate**: 7/7 = 100 % (requirement ≥ 90 %) across:
  order-dependence, error-cell, train-not-test, missing-figure,
  nondeterministic-seed, round-metric, stale-report

## Ask your agent

> Set up a sandbox and solve the demo in
> `cookbook/notebook-exec-report/` of
> https://github.com/agent-next/sandbox (clone it first). Run
> `bash cookbook/notebook-exec-report/judge/setup.sh`, read
> `cookbook/notebook-exec-report/SPEC.md`, then design the artifact
> yourself: `analysis.ipynb`, a Jupyter notebook that loads the pinned
> `dataset.csv` sitting in `examples/good/` (copy it next to your
> notebook), splits it 80/20 with `numpy.random.default_rng(20261015)`
> `.permutation`, fits `sklearn.linear_model.Ridge(alpha=10.0)` on the
> natural log of `MED_VALUE` with predictors standardized by the
> training split's mean/std, saves at least three distinct figures under
> `figures/`, writes `report.html` embedding every figure and every
> metric, and prints a `metrics` JSON object (keys per SPEC) from a cell
> tagged `metrics`. The judge runs your notebook headless twice on clean
> kernels and verifies the numbers against its own independent refit.
> Iterate with
> `bash cookbook/notebook-exec-report/judge/grade.sh <your-notebook.ipynb> --json v.json`
> until it exits 0, then paste the final verdict JSON. Do not edit
> anything under `judge/`; if you believe the judge is wrong, say so
> instead of working around it. Kill the sandbox when you are done.

The known-good example in `examples/good/` (built by
`build_notebook.py` from `make_dataset.py`'s pinned generator) is one
valid answer; a working artifact does not have to resemble it beyond
the SPEC.

## One-command run

```bash
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
export SBX_API_KEY=<your key>
python3 cookbook/notebook-exec-report/run.py --ref <ref>   # --keep supported
```

`--ref` is the repo ref to clone and run — a branch name while this demo
is under review (e.g. `--ref sbx/demo-notebook-exec-report-f5`), `main`
once merged (the default). The demo directory must exist at that ref or
the run fails at `judge/setup.sh`.

Creates a sandbox, clones the repo, installs pinned tools, runs the judge
self-test, grades `examples/good/analysis.ipynb`, prints the verdict JSON,
then kills the sandbox and confirms it is gone. Stdlib only; exits
non-zero on any failure, naming the sandbox id if cleanup could not be
confirmed.

## Measured wall time (Debian sandbox, 2 vCPU / ~3 GB)

| step | wall time |
|---|---|
| `git clone --depth 1` | ~4 s |
| `judge/setup.sh` (fresh install, 64 hash-pinned wheels) | 90–235 s (idempotent re-run: 8 s) |
| `judge/selftest.sh` (good + 7 mutants + determinism) | 185–502 s |
| `judge/grade.sh examples/good/analysis.ipynb` (2 clean kernel runs + refit) | 20–78 s |

Whole run including sandbox create/kill: 5–15 min (three fresh-sandbox
runs: 6.6 min, 4.4 min, 4.7 min — see RECEIPT.md; setup.sh dominates and
varies with PyPI throughput). `run.py` prints a per-step timing line.

## Limits, plainly

- The judge grades one ridge fit on a fixed synthetic dataset; model
  quality beyond the noise-floor gate, hyperparameter search and feature
  selection are non-goals — see SPEC.
- The split PRNG (`numpy.random.default_rng(seed).permutation`) is
  *specified* by numpy: the judge reimplements everything downstream of
  the split (standardization, log target, ridge solve, all compared
  metrics) in the standard library, but the split itself comes from the
  pinned numpy — stated as a deviation in SPEC.
- The pinned interpreter is CPython 3.12 (the sandbox image's default);
  `grade.sh` refuses another minor version so the calibration numbers
  stay valid.
- No pin in `judge/requirements.txt` was published within two weeks of
  the demo (cutoff 2026-09-30, enforced by `judge/genlock.py`).
- `analysis.ipynb` must not `pip install` anything; the judge's venv is
  the only toolchain, and the notebook must pass on a fresh kernel with
  only the files it writes itself.
