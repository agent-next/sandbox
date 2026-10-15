#!/usr/bin/env python3
"""Generate known-bad single-edit mutants of the good notebook artifact.

Each mutant is exactly one edit of examples/good/analysis.ipynb -- either
one source line replaced (anchored on a unique line, verified) or one code
cell moved below a cell that depends on it.  Used by judge/selftest.sh to
prove the judge fails on bad inputs.  Output: <outdir>/<name>.ipynb plus a
summary line per mutant naming the edit.

Mutants (the five defects the brief named, plus two):
  order-dependence      the figures cell (defines pred_log) moves *below*
                        the metrics cell: only works if cells already ran
                        out of order -- hidden state, NameError on a clean
                        top-to-bottom run
  error-cell            the dataset sanity check raises ValueError
  train-not-test        rmse_test is computed on the training split
  missing-figure        the third figure is never saved
  nondeterministic-seed the split uses an unseeded default_rng()
  round-metric          rmse_test reported to 4 decimals (breaks 1e-6
                        oracle agreement)
  stale-report          report.html tabulates a hard-coded rmse_test
"""

import json
import sys
from pathlib import Path

# (name, old line, new line) -- `old` must appear in exactly one code cell
# of the good notebook, exactly once.
LINE_EDITS = [
    ("error-cell",
     "assert len(df) == 1600",
     'raise ValueError("dataset sanity check failed: unexpected row count")'),
    ("train-not-test",
     "rmse_test = float(np.sqrt(np.mean((log_y[test_idx] - pred_log) ** 2)))",
     "rmse_test = float(np.sqrt(np.mean(\n"
     "    (log_y[train_idx] - model.predict(Xs[train_idx])) ** 2)))"),
    ("missing-figure",
     'fig.tight_layout(); fig.savefig(FIGDIR / "coefficients.png", dpi=150)',
     "pass  # figure skipped: not saved"),
    ("nondeterministic-seed",
     "rng = np.random.default_rng(SEED)",
     "rng = np.random.default_rng()"),
    ("round-metric",
     '"rmse_test": round(rmse_test, 6),',
     '"rmse_test": round(rmse_test, 4),'),
    ("stale-report",
     'f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in metrics.items())',
     'f"<tr><th>{k}</th><td>{v}</td></tr>"\n'
     '     for k, v in {**metrics, "rmse_test": 0.123456}.items())'),
]

# the cell whose source contains this unique line is moved to *after* the
# metrics cell, so the metrics cell references a variable defined later
ORDER_ANCHOR = 'fig.savefig(FIGDIR / "pred_vs_obs.png", dpi=150)'
METRICS_TAG = "metrics"


def fail(msg: str) -> None:
    print(f"mutants: {msg}", file=sys.stderr)
    sys.exit(1)


def cell_source(cell: dict) -> str:
    src = cell.get("source", "")
    return "".join(src) if isinstance(src, list) else src


def set_source(cell: dict, text: str) -> None:
    cell["source"] = text.splitlines(keepends=True)


def edit_one_line(cells: list, old: str, new: str) -> None:
    hits = [i for i, c in enumerate(cells)
            if c["cell_type"] == "code" and old in cell_source(c)]
    if len(hits) != 1:
        fail(f"anchor {old!r} found in {len(hits)} code cells, expected 1")
    c = cells[hits[0]]
    src = cell_source(c)
    if src.count(old) != 1:
        fail(f"anchor {old!r} appears {src.count(old)}x in its cell")
    set_source(c, src.replace(old, new))


def move_below_metrics(cells: list, anchor: str) -> None:
    hits = [i for i, c in enumerate(cells)
            if c["cell_type"] == "code" and anchor in cell_source(c)]
    if len(hits) != 1:
        fail(f"anchor {anchor!r} found in {len(hits)} code cells, expected 1")
    mtag = [i for i, c in enumerate(cells)
            if c["cell_type"] == "code"
            and METRICS_TAG in c.get("metadata", {}).get("tags", [])]
    if len(mtag) != 1:
        fail(f"expected exactly one metrics-tagged cell, found {len(mtag)}")
    moved = cells.pop(hits[0])
    cells.insert(mtag[0], moved)  # after the metrics cell


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: mutants.py <good.ipynb> <outdir>", file=sys.stderr)
        return 2
    good = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    outdir = Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)

    made = 0
    for name, old, new in LINE_EDITS:
        cells = json.loads(json.dumps(good))["cells"]  # deep copy
        edit_one_line(cells, old, new)
        dest = outdir / f"{name}.ipynb"
        dest.write_text(json.dumps({**good, "cells": cells}, indent=1) + "\n",
                        encoding="utf-8")
        print(f"mutants: {name}.ipynb  edit: {old.splitlines()[0][:60]!r}")
        made += 1

    cells = json.loads(json.dumps(good))["cells"]
    move_below_metrics(cells, ORDER_ANCHOR)
    dest = outdir / "order-dependence.ipynb"
    dest.write_text(json.dumps({**good, "cells": cells}, indent=1) + "\n",
                    encoding="utf-8")
    print("mutants: order-dependence.ipynb  edit: figures cell moved below "
          "the metrics cell")
    made += 1

    print(f"mutants: wrote {made} mutants to {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
