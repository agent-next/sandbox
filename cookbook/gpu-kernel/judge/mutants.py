#!/usr/bin/env python3
"""Generate known-bad artifacts for the self-test by single edits of the good one.

Each mutant is the good kernel with exactly one scripted edit; the self-test
expects every mutant to fail at least one gate (SPEC.md). Mutants cover the
failure classes from the brief: missing max-subtraction, off-by-one in the
reduction, wrong block reduction, missing normalisation, min-for-max,
wrong row stride, and a device-compile error.
"""

import os
import sys

# (name, must-exist-literal, replacement)
EDIT = [
    ("no_max_sub", "e = tl.exp(x - x_max)",
     "e = tl.exp(x)"),
    ("no_max_sub_other_form", "x = tl.load(X + row * n_cols + cols, mask=mask, other=float(\"-inf\"))\n    x_max = tl.max(x, axis=0)",
     "x = tl.load(X + row * n_cols + cols, mask=mask)\n    x_max = tl.zeros((), dtype=tl.float32)"),
    ("off_by_one", "x = tl.load(X + row * n_cols + cols, mask=mask, other=float(\"-inf\"))",
     "x = tl.load(X + row * n_cols + cols, mask=cols < n_cols - 1, other=float(\"-inf\"))"),
    ("wrong_block_reduction", "x_max = tl.max(x, axis=0)\n    e = tl.exp(x - x_max)",
     "x_max = tl.max(x, axis=0)\n    e = tl.exp(x - x_max) - 1.0"),
    ("no_normalise", "tl.store(Y + row * n_cols + cols, e / denom, mask=mask)",
     "tl.store(Y + row * n_cols + cols, e, mask=mask)"),
    ("min_for_max", "x_max = tl.max(x, axis=0)",
     "x_min = tl.min(x, axis=0)"),
    ("wrong_row_stride", "x = tl.load(X + row * n_cols + cols, mask=mask, other=float(\"-inf\"))",
     "x = tl.load(X + row * (n_cols // 2) + cols, mask=mask, other=float(\"-inf\"))"),
    ("compile_error", "x_max = tl.max(x, axis=0)",
     "x_max = tl.max(x, axis=1)"),
    ("masked_other_zero", "other=float(\"-inf\")",
     "other=0.0"),
    ("store_off_by_one", "tl.store(Y + row * n_cols + cols, e / denom, mask=mask)",
     "tl.store(Y + row * n_cols + cols, e / denom, mask=cols < (n_cols - 1))"),
]

# make min_for_max consistent: also swap the subtraction
def main():
    src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "examples", "good")
    good = open(os.path.join(src_dir, "kernel.py")).read()
    out_dir = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "mutants")
    os.makedirs(out_dir, exist_ok=True)
    names = []
    for name, old, new in EDIT:
        if old not in good:
            raise SystemExit(f"mutant {name}: edit anchor not found in good kernel")
        mutant = good.replace(old, new, 1)
        if name == "min_for_max":
            mutant = mutant.replace("e = tl.exp(x - x_max)", "e = tl.exp(x - x_min)")
        if mutant == good:
            raise SystemExit(f"mutant {name}: edit produced no change")
        path = os.path.join(out_dir, name + ".py")
        with open(path, "w") as fh:
            fh.write(mutant)
        names.append(name)
    print("\n".join(names))


if __name__ == "__main__":
    main()
