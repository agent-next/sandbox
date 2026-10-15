# SPEC — `cookbook/notebook-exec-report/`

An agent works on a real data-analysis problem inside a disposable agent-next
sandbox: produce a Jupyter notebook that loads a pinned dataset, fits a simple
model, and renders an HTML report — where a judge it cannot fool (nbclient on
a clean kernel + independent numpy refits) decides whether the notebook is
*reproducible* and *correct*, not merely whether it "ran".

## Goal

Deliver `analysis.ipynb` such that a top-to-bottom headless execution on a
**fresh kernel**:

1. runs every cell with no error, once, in document order
   (execution counts `1..N`, no re-execution, no skipped cell);
2. loads the pinned dataset, splits it deterministically, fits a
   scikit-learn ridge regression, and reports its **test-set** RMSE as a
   tagged `metrics` JSON output;
3. renders an HTML report (`report.html`) that contains **every** figure the
   notebook produced;
4. and where the agent's own reported numbers are **verified against a
   judge-side reference implementation** written independently in numpy
   (no scikit-learn, same split, same target transform).
## Non-goals

- Model quality beyond the fixed accuracy gate: no reward for a better model
  than the ridge fit, no hyperparameter search, no feature selection.
- Pretty layout of the HTML report beyond "it contains the figures and the
  metric table".
- Multi-user scheduling, secrets, network access to anything but the pinned
  dataset the notebook itself writes down (the notebook embeds the dataset;
  there is no download step to grade).
- Jupyter server / UI behaviour: the artifact is graded with nbclient, not in
  a browser.
- Rust/BI provenance, version control of intermediate checkpoints, or
  anything about how the agent got there.

## Artifact

`analysis.ipynb` — one nbformat-4 `.ipynb` file. It must be a complete
notebook, i.e. it may not rely on any state that is not created by its own
cells (a fresh kernel must suffice). Requirements:

- The first **code** cell must import only `numpy`, `pandas`, `sklearn`,
  `matplotlib`, and stdlib modules.
- Dataset: `dataset.csv`, produced by `examples/good/make_dataset.py` and
  committed next to the notebook. The generator is documented and pinned
  (generator seed, 1600 rows, exact `W_TRUE`, noise σ), so the "true"
  coefficient vector is exact by construction and the judge can check the fit
  against it. The notebook records the CSV's sha256 in a cell output.
- Model: `sklearn.linear_model.Ridge(alpha=10.0)`, fitted on a deterministic
  80/20 split (`numpy.random.default_rng(20261015).permutation`), on the
  **natural log of the target** `MED_VALUE`, with predictors standardized by
  the **training** split's mean/std (an intercept is fitted separately and is
  never penalized).
- One cell produces a `metrics` **tagged output**: its `outputs` contain a
  stream output that is a JSON object with the keys
  `{"seed": 20261015, "alpha": 10.0, "n_train": <int>, "n_test": <int>,
  "rmse_test": <float>, "rmse_train": <float>, "r2_test": <float>,
  "rmse_test_usd": <float>, "dataset_sha256": "<hex>", "figures": [...]}`
  and the cell carries the notebook-metadata tag `metrics`.
- Figures: at least three `matplotlib` figures, each a distinct
  `image/png` output in the notebook **and** saved by the notebook to
  `figures/*.png` inside the artifact directory, which the report embeds.
- The notebook writes `report.html` next to itself, containing an `<img>`
  tag for every saved figure file, and a table row per metric key.
- `judge/setup.sh` is the only installer; the notebook must not
  `pip install` anything.

## Judge gates (`judge/grade.sh <artifact.ipynb> [--seed N] [--json out.json]`)

All gates are numeric and deterministic. Exit 0 only if every gate passes.
The artifact is copied to a temp dir and run there; the judge never executes
anything from the artifact directory other than the notebook itself.

- **G1 execution**: nbclient `NotebookClient` on a **clean** kernel
  (`ipykernel`), `allow_errors=False`. Any cell error, any `Traceback`
  output, or any `execution_count` that is not exactly the 1-based position
  of the code cell fails the gate (this kills out-of-order and re-executed
  notebooks).
- **G2 determinism / hidden state**: the notebook is executed **twice** from
  the same source (fresh kernel each time) in two different working
  directories; the two executions must produce the same `rmse_test`
  (identical to 1e-12) and the same set of figure SHA-256 digests. A
  notebook that reads a leftover `report.html`, a `__pycache__`, or any file
  its own cells did not write fails here.
- **G3 figures**: the notebook emits ≥ 3 `image/png` outputs, all distinct
  digests, each ≥ 8 kB (a blank or stub figure fails), and the exported
  `report.html` contains an `<img src=...>` reference to **every** figure
  file listed in the artifact's `figures/` directory. Every `<img>` `src`
  must resolve to a local file that exists.
- **G4 metric vs. judge refit (the acceptance oracle)**: the judge
  re-implements the pipeline independently — the same dataset, the same seed
  and split, natural-log target, and the ridge closed form
  `w = (XᵀX + αI)⁻¹Xᵀy` on the standardized predictors — and requires the
  notebook's reported `rmse_test` to agree within **1e-6** absolute,
  `rmse_train` within **1e-6**, `r2_test` within **1e-9**, and `n_train` /
  `n_test` exactly. This is an independent oracle on the numeric path: the
  judge's linear algebra is its own **Gaussian elimination with partial
  pivoting** written in the standard library (no numpy, no scipy, no
  scikit-learn, no BLAS), so a notebook that secretly fits a different
  model, uses the train split for the metric, or reports a stale value
  fails. numpy appears in the judge only to reproduce the documented,
  SPEC-fixed PRNG (`numpy.random.default_rng(seed).permutation`) — see the
  Deviation note below.
- **G5 accuracy (noise floor)**: the refit's `rmse_test` on the log scale
  must be ≤ **0.3040**. The generator's noise σ = 0.30, so a correct fit
  lands at 0.2953 ± 0.010; a model that skipped the log transform lands at
  ~1.60 — a factor of 5 away, with a wide margin either side.
- **G6 report completeness**: `report.html` parses, contains every metric
  key and its value to 6 decimals, embeds all figures, and contains no
  `Traceback` / `CellExecutionError` text.
- **G7 no judge tampering**: the `judge/` tree's sha256 is unchanged before
  and after grading, and the notebook's sources contain no reference to the
  `judge/` path.

Violating any gate fails with the offending numbers printed.

## Acceptance oracle (independent of "it ran")

1. **Independent ridge refit** — G4 above. The judge solves the normal
   equations with its own Gaussian elimination; it never imports
   scikit-learn, and it never imports numpy except to reproduce the
   SPEC-fixed split. **Deviation from the earlier draft, stated plainly:**
   the split is drawn by `numpy.random.default_rng(seed).permutation`
   because reimplementing numpy's PCG64 + Lemire shuffle bit-for-bit in the
   standard library was rejected as fragile; the split is therefore
   *specified* by numpy rather than *independent* of it. Everything
   downstream of the split — standardization, the log target, the ridge
   solve, and all four compared metrics — is independent judge code.
2. **Blind-seed sanity** — the judge repeats the same refit under five
   *other* split seeds and requires the graded split's `rmse_test` to be
   ≤ 1.25× the median of those five (0.2972 median). A notebook that fit one
   lucky split, or reports a train metric, is outside that band.
3. **Held-out analytic bound** — the judge computes the coefficient recovery
   `‖ŵ − w_true‖ / ‖w_true‖` from its own refit and requires it ≤ **0.05**,
   since the generator's `w_true` is exact by construction (measured 0.0180
   on the good notebook). A metric computed on the *train* split fails this
   too: train recovery is systematically tighter.
4. **Report determinism** — G2 above: two executions from two different
   directories must agree on the figure digests. This is the gate that
   catches order-dependent and hidden-state notebooks, which cannot
   reproduce.

Reference numbers the good example must hit (measured on the good artifact):

| quantity | value |
|---|---|
| `rmse_test` (log scale) | 0.2953 |
| `r2_test` | 0.8779 |
| `rmse_test_usd` | ~2250 |
| coefficient recovery `‖ŵ−w_true‖/‖w_true‖` | 0.0180 |

## Self-test (`judge/selftest.sh`)

- The known-good example passes every gate.
- ≥ 5 known-bad single-edit mutants of the good notebook, generated by
  `judge/mutants.py` from the notebook's own source lines, each fail ≥ 1
  gate. The seven mutants include the five defects the lead named:
  - `order-dependence` — the metric cell depends on a cell *below* it in the
    notebook, so it only works if that later cell has already run
    (hidden state / out-of-order execution);
  - `error-cell` — a cell that raises `ValueError`;
  - `train-not-test` — `rmse_test` computed on the training split;
  - `missing-figure` — one figure not written to `figures/`;
  - `nondeterministic-seed` — the split uses unseeded `np.random`
    (`default_rng()` with no seed), so the metric moves every run;
  - `round-metric` — `rmse_test` reported to 4 decimals, which breaks the
    1e-6 oracle agreement;
  - `stale-report` — the report is built from a hard-coded metric value
    instead of the computed one.
- Kill rate ≥ 90 % printed by the self-test; exit non-zero otherwise.
- Determinism: two `grade.sh` runs with the same seed produce byte-identical
  verdict JSON except the `timing` key; checked by the self-test.

## Judge-integrity rule

The artifact under test is copied to a temp dir before grading; the judge
compares `sha256` of its own `judge/` tree before and after every grade and
fails closed if anything changed. The notebook never runs with the judge
directory on `sys.path`.

## Out of scope for the judge

- Notebook style, markdown prose quality, cell comments.
- Any metric the notebook prints that is not in the tagged JSON.
- Whether the fitted model is a *good* model beyond the numeric gates.

## Tools (pinned by `judge/setup.sh`)

- Python **3.12** (the version `judge/VERSIONS.txt` records; the judge refuses
  a different minor version so verdicts stay reproducible).
- `numpy 2.5.3`, `scipy 1.18.1`, `scikit-learn 1.9.1`, `pandas 3.0.6`,
  `matplotlib 3.11.2`, `nbclient 0.11.0`, `nbformat 5.11.1`,
  `nbconvert 7.17.1`, `ipykernel 7.4.0`, `jupyter_client 8.10.0`,
  `traitlets 5.16.1` (plus their pinned transitive closure — 64 pins in
  `judge/requirements.txt`, each the newest release published before
  2026-09-30) — installed into a venv at `~/.judge-venv` from
  `judge/requirements.txt` with `--require-hashes`.
- The judge's *oracle* is **standard library only** (plus numpy for the
  SPEC-fixed split); the notebook-execution harness itself runs on the pinned
  interpreter above.
