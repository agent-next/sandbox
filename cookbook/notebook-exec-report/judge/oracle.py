"""Independent oracle for the notebook-exec-report judge (stdlib + numpy).

Re-runs the SPEC.md pipeline from the dataset bytes and the split the
notebook reports, and returns the four metrics the notebook's tagged
`metrics` cell is compared against.

Independence: the linear algebra here is a stdlib Gaussian elimination with
partial pivoting.  No scikit-learn, no BLAS, no numpy linalg -- a notebook
that fits a different model, or that reports a train metric, cannot match.
numpy is imported only to reproduce the SPEC-fixed split
(`default_rng(seed).permutation`); see SPEC.md, "Acceptance oracle".
"""

from __future__ import annotations

import csv
import io
import math
from typing import List, Sequence

FEATURES = (
    "MED_INC", "HOUSEHOLDS", "AVE_ROOMS", "AVE_BEDRMS",
    "POPULATION", "AVE_OCCUPANCY", "LAT", "LONG",
)
TARGET = "MED_VALUE"
W_TRUE = (0.30, 0.10, 0.25, -0.08, 0.05, -0.20, 0.45, -0.35)


# --- stdlib linear algebra -------------------------------------------------
def solve(A: Sequence[Sequence[float]], b: Sequence[float]) -> List[float]:
    """Solve A x = b by Gaussian elimination with partial pivoting."""
    n = len(A)
    M = [list(row) + [bb] for row, bb in zip(A, b)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(M[r][col]))
        if abs(M[piv][col]) < 1e-300:
            raise ValueError("singular normal equations")
        M[col], M[piv] = M[piv], M[col]
        pv = M[col][col]
        for r in range(n):
            if r == col:
                continue
            f = M[r][col] / pv
            if f == 0.0:
                continue
            row_r, row_c = M[r], M[col]
            for c in range(col, n + 1):
                row_r[c] -= f * row_c[c]
    return [M[r][n] / M[r][r] for r in range(n)]


def load_dataset(csv_bytes: bytes):
    """Return (X rows as float lists, y floats) from the CSV bytes."""
    reader = csv.reader(io.StringIO(csv_bytes.decode("utf-8")))
    header = next(reader)
    cols = {name: header.index(name) for name in list(FEATURES) + [TARGET]}
    xs: List[List[float]] = []
    ys: List[float] = []
    for row in reader:
        if not row:
            continue
        xs.append([float(row[cols[name]]) for name in FEATURES])
        ys.append(float(row[cols[TARGET]]))
    return xs, ys


def refit(csv_bytes: bytes, seed: int, alpha: float) -> dict:
    """Refit the SPEC pipeline from scratch; returns the four gate metrics
    plus the coefficient recovery against the generator's exact W_TRUE."""
    import numpy as np  # only for the SPEC-fixed split; see oracle docstring

    xs, ys = load_dataset(csv_bytes)
    n = len(ys)
    if n != 1600:
        raise ValueError(f"dataset has {n} rows, expected 1600")

    order = list(np.random.default_rng(seed).permutation(n))
    n_train = int(round(0.8 * n))
    train_idx, test_idx = order[:n_train], order[n_train:]

    mu = [sum(xs[i][j] for i in train_idx) / n_train for j in range(len(FEATURES))]
    var = [sum((xs[i][j] - mu[j]) ** 2 for i in train_idx) / n_train
           for j in range(len(FEATURES))]
    sd = [math.sqrt(v) for v in var]
    # numpy's default std is the population std; scikit-learn's linear models
    # use it too.  A zero sd means a constant column: keep it at 0.
    zs = [[(xs[i][j] - mu[j]) / sd[j] if sd[j] else 0.0 for j in range(len(FEATURES))]
          for i in range(n)]

    d = len(FEATURES)
    # X^T X + alpha I over the augmented design [1, Z]
    ata = [[0.0] * (d + 1) for _ in range(d + 1)]
    aty = [0.0] * (d + 1)
    t_train = [math.log(ys[i]) for i in train_idx]
    for pos, i in enumerate(train_idx):
        row = [1.0] + zs[i]
        ti = t_train[pos]
        for a in range(d + 1):
            ra = row[a]
            ata_a = ata[a]
            for b in range(d + 1):
                ata_a[b] += ra * row[b]
            aty[a] += ra * ti
    for k in range(1, d + 1):
        ata[k][k] += alpha
    w = solve(ata, aty)

    def predict(i: int) -> float:
        return w[0] + sum(w[k + 1] * zs[i][k] for k in range(d))

    ss_tr = sum((math.log(ys[i]) - predict(i)) ** 2 for i in train_idx)
    ss_te = sum((math.log(ys[i]) - predict(i)) ** 2 for i in test_idx)
    mean_te = sum(math.log(ys[i]) for i in test_idx) / len(test_idx)
    sst_te = sum((math.log(ys[i]) - mean_te) ** 2 for i in test_idx)
    coef = w[1:]
    wnorm = math.sqrt(sum(c * c for c in W_TRUE))
    recovery = math.sqrt(sum((c - wt) ** 2 for c, wt in zip(coef, W_TRUE))) / wnorm
    return {
        "n_train": n_train,
        "n_test": n - n_train,
        "rmse_train": math.sqrt(ss_tr / n_train),
        "rmse_test": math.sqrt(ss_te / len(test_idx)),
        "r2_test": 1.0 - ss_te / sst_te,
        "coef_recovery": recovery,
    }
