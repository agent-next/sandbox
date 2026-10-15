#!/usr/bin/env python3
"""Build analysis.ipynb from the cell sources below.

The notebook is written by a generator rather than hand-assembled JSON so
that the single-edit mutants in judge/mutants.py have stable anchors: every
source line a mutant targets appears exactly once in this file.

Layout, all under examples/good/:
    make_dataset.py    the dataset generator (stdlib + numpy + pandas)
    dataset.csv        the pinned dataset it writes
    build_notebook.py  this file
    analysis.ipynb     the built artifact

Usage:  python3 build_notebook.py
"""

from __future__ import annotations

import json
from pathlib import Path

# --- cell sources ---------------------------------------------------------
# Lines the mutants anchor on must be unique across this list; mutants.py
# fails loudly if an anchor line is missing or ambiguous.

MD_TITLE = """\
# California-style housing price model

Pinned dataset, deterministic train/test split, one ridge fit, one HTML
report.  The last metric cell prints the `metrics` JSON the judge grades
against its own independent numpy refit.
"""

CODE_IMPORTS = """\
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.linear_model import Ridge

OUT = Path("_out"); OUT.mkdir(exist_ok=True)
FIGDIR = OUT / "figures"; FIGDIR.mkdir(parents=True, exist_ok=True)
print("numpy", np.__version__, "| pandas", pd.__version__)
"""

MD_DATASET = """\
## 1. Load the pinned dataset

`dataset.csv` is written by `make_dataset.py` from a documented, seeded
generator (generator seed, 1600 rows, an exact weight vector `W_TRUE` and a
noise sigma), so its provenance is auditable.  We record the file digest so
the judge can confirm it graded the same bytes we did.
"""

CODE_LOAD = """\
DATASET = Path("dataset.csv")
df = pd.read_csv(DATASET)
FEATURES = [
    "MED_INC", "HOUSEHOLDS", "AVE_ROOMS", "AVE_BEDRMS",
    "POPULATION", "AVE_OCCUPANCY", "LAT", "LONG",
]
TARGET = "MED_VALUE"
assert set(FEATURES + [TARGET]) == set(df.columns), df.columns
assert len(df) == 1600
dataset_sha256 = hashlib.sha256(DATASET.read_bytes()).hexdigest()
print("rows", len(df), "| sha256", dataset_sha256[:16], "...")
df.head()
"""

MD_SPLIT = """\
## 2. Deterministic split

An 80/20 split drawn from `numpy.random.default_rng(20261015).permutation`,
which is reproducible without any global RNG state.
"""

CODE_SPLIT = """\
SEED = 20261015
ALPHA = 10.0
rng = np.random.default_rng(SEED)
order = rng.permutation(len(df))
n_train = int(round(0.8 * len(df)))
train_idx, test_idx = order[:n_train], order[n_train:]
X = df[FEATURES].to_numpy(dtype=float)
y = df[TARGET].to_numpy(dtype=float)
"""

MD_FIT = """\
## 3. Fit the ridge model

Predictors are standardized by the **training** split's own mean and standard
deviation, the target is modelled on the natural log scale, and the intercept
is kept out of the penalty.
"""

CODE_FIT = """\
mu = X[train_idx].mean(axis=0)
sd = X[train_idx].std(axis=0)
Xs = (X - mu) / sd
model = Ridge(alpha=ALPHA, fit_intercept=True)
model.fit(Xs[train_idx], np.log(y[train_idx]))
coef = model.coef_
print("coefficients on the standardized scale:")
for name, c in zip(FEATURES, coef):
    print(f"  {name:<14s} {c:+.4f}")
print(f"intercept {model.intercept_:+.4f}")
"""

MD_FIGURES = """\
## 4. Figures

Three figures, each saved under `figures/` so the HTML report can embed them
and the judge can check that the report references every figure.
"""

CODE_FIGS = """\
log_y = np.log(y)
pred_log = model.predict(Xs[test_idx])

fig, ax = plt.subplots(figsize=(6, 4))
ax.scatter(log_y[test_idx], pred_log, s=8, alpha=0.5, color="#0072B2")
lo = min(log_y[test_idx].min(), pred_log.min()) - 0.1
hi = max(log_y[test_idx].max(), pred_log.max()) + 0.1
ax.plot([lo, hi], [lo, hi], "--", color="#D55E00", lw=1.5, label="1:1")
ax.set_xlabel("log(observed MED_VALUE)")
ax.set_ylabel("log(predicted MED_VALUE)")
ax.set_title("Predicted vs observed (test split)")
ax.legend()
fig.tight_layout(); fig.savefig(FIGDIR / "pred_vs_obs.png", dpi=150)

resid = log_y[test_idx] - pred_log
fig, ax = plt.subplots(figsize=(6, 4))
ax.scatter(pred_log, resid, s=8, alpha=0.5, color="#0072B2")
ax.axhline(0.0, color="#D55E00", lw=1.5, ls="--")
ax.set_xlabel("log(predicted MED_VALUE)")
ax.set_ylabel("residual")
ax.set_title("Residuals vs prediction (test split)")
fig.tight_layout(); fig.savefig(FIGDIR / "residuals.png", dpi=150)

fig, ax = plt.subplots(figsize=(6, 4))
order_c = np.argsort(np.abs(coef))
ax.barh(np.array(FEATURES)[order_c], coef[order_c],
        color=["#0072B2" if c > 0 else "#CC79A7" for c in coef[order_c]])
ax.axvline(0.0, color="k", lw=0.8)
ax.set_xlabel("standardized coefficient")
ax.set_title("Ridge coefficients (log target)")
fig.tight_layout(); fig.savefig(FIGDIR / "coefficients.png", dpi=150)
print("figures:", sorted(p.name for p in FIGDIR.glob("*.png")))
"""

MD_REPORT = """\
## 5. Metrics and HTML report

The metric cell is tagged `metrics` so the judge can find it.  The report
embeds every figure and tabulates every metric.
"""

CODE_METRICS = """\
rmse_test = float(np.sqrt(np.mean((log_y[test_idx] - pred_log) ** 2)))
rmse_train = float(np.sqrt(np.mean(
    (log_y[train_idx] - model.predict(Xs[train_idx])) ** 2)))
ss_res = float(np.sum((log_y[test_idx] - pred_log) ** 2))
ss_tot = float(np.sum((log_y[test_idx] - log_y[test_idx].mean()) ** 2))
r2_test = 1.0 - ss_res / ss_tot
# the same error expressed back in the target's own units (1.0 = 1.0 of
# MED_VALUE, i.e. the column's own scale)
rmse_price = float(np.sqrt(np.mean(
    (y[test_idx] - np.exp(pred_log)) ** 2)))
metrics = {
    "seed": SEED,
    "alpha": ALPHA,
    "n_train": int(n_train),
    "n_test": int(len(test_idx)),
    "rmse_test": round(rmse_test, 6),
    "rmse_train": round(rmse_train, 6),
    "r2_test": round(r2_test, 9),
    "rmse_price": round(rmse_price, 6),
    "dataset_sha256": dataset_sha256,
    "figures": sorted(p.name for p in FIGDIR.glob("*.png")),
}
print(json.dumps(metrics, indent=2))
"""

CODE_REPORT = """\
rows = "".join(
    f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in metrics.items())
imgs = "".join(
    f'<figure><img src="figures/{name}" alt="{name}">'
    f"<figcaption>{name}</figcaption></figure>"
    for name in metrics["figures"])
html = (
    "<!doctype html><html><head><meta charset='utf-8'>"
    "<title>Housing model report</title></head><body>"
    "<h1>Housing model report</h1>"
    f"<table>{rows}</table>"
    "<h2>Figures</h2>"
    f"{imgs}"
    "</body></html>"
)
(OUT / "report.html").write_text(html, encoding="utf-8")
print("report ->", OUT / "report.html", len(html), "bytes")
"""

MD_CLOSE = """\
## 6. Conclusion

A plain ridge fit on the log target: the judge recomputes it in numpy from
the same split and must land on the same `rmse_test` to 1e-6.
"""


def main() -> int:
    cells = [
        ("markdown", MD_TITLE, []),
        ("code", CODE_IMPORTS, []),
        ("markdown", MD_DATASET, []),
        ("code", CODE_LOAD, []),
        ("markdown", MD_SPLIT, []),
        ("code", CODE_SPLIT, []),
        ("markdown", MD_FIT, []),
        ("code", CODE_FIT, []),
        ("markdown", MD_FIGURES, []),
        ("code", CODE_FIGS, []),
        ("markdown", MD_REPORT, []),
        ("code", CODE_METRICS, ["metrics"]),
        ("code", CODE_REPORT, []),
        ("markdown", MD_CLOSE, []),
    ]

    nb_cells = []
    for n, (ctype, source, tags) in enumerate(cells, start=1):
        cell = {
            "id": f"{ctype[:2]}-{n:02d}",
            "cell_type": ctype,
            "metadata": {"tags": tags},
            "source": source.splitlines(keepends=True),
        }
        if ctype == "code":
            cell["execution_count"] = None
            cell["outputs"] = []
        nb_cells.append(cell)

    nb = {
        "cells": nb_cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python",
                           "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }

    out = Path(__file__).parent / "analysis.ipynb"
    out.write_text(json.dumps(nb, indent=1) + "\n", encoding="utf-8")
    print(f"build_notebook: wrote {out} ({len(nb_cells)} cells)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
