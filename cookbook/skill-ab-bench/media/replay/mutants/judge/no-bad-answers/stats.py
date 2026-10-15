#!/usr/bin/env python3
"""The two statistical procedures the judge gates on.  Standard library only.

  fisher_exact_2x2   two-sided Fisher's exact test, from the hypergeometric
                     pmf in `math.comb` -- no scipy, no floating-point
                     approximation of a factorial.
  bootstrap_delta_ci percentile bootstrap CI on the pass-rate difference,
                     resampling *tasks* independently within each arm, from a
                     seeded `random.Random` so the same `--seed` always gives
                     byte-identical bounds.

Both are used by `judge/grade.py` and both are checked against known values by
`judge/selftest.sh` (see `judge/tests/test_stats.py`).
"""

from __future__ import annotations

import math
import random


def _hypergeom_pmf(a: int, row1: int, col1: int, n: int) -> float:
    """P(top-left cell == a) for a 2x2 table with these fixed margins."""
    return (math.comb(row1, a) * math.comb(n - row1, col1 - a)) / math.comb(n, col1)


def fisher_exact_2x2(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher's exact test p-value for the table [[a, b], [c, d]].

    `a`/`b` are the passes/fails of the first arm, `c`/`d` of the second.  The
    two-sided p-value is the sum of the pmf over every table with the same
    margins whose pmf is no larger than the observed table's -- the standard
    definition, which counts tables in *both* tails.
    """
    for value in (a, b, c, d):
        if value < 0:
            raise ValueError(f"fisher_exact_2x2: negative cell {value}")
    row1, row2 = a + b, c + d
    col1 = a + c
    n = row1 + row2
    if n == 0:
        raise ValueError("fisher_exact_2x2: empty table")

    observed = _hypergeom_pmf(a, row1, col1, n)
    # a' ranges over every top-left count the margins allow.
    lo = max(0, col1 - row2)
    hi = min(row1, col1)
    # A tiny relative slack keeps tables that are equal up to floating-point
    # representation from being dropped, which would bias p downward.
    tol = observed * 1e-9
    total = 0.0
    for a2 in range(lo, hi + 1):
        p = _hypergeom_pmf(a2, row1, col1, n)
        if p <= observed + tol:
            total += p
    return min(1.0, total)


def bootstrap_delta_ci(passes_a: list[bool], passes_b: list[bool], seed: int,
                       resamples: int = 10000,
                       alpha: float = 0.05) -> dict:
    """Percentile bootstrap CI on rate(a) - rate(b), resampling tasks.

    Each resample draws `len(passes_a)` tasks with replacement from arm A and
    `len(passes_b)` from arm B, independently, and records the difference of
    the resampled pass rates.  The CI is the (alpha/2, 1 - alpha/2) percentile
    pair of those differences.

    Returns the point estimate, the bounds and the resample count.  The point
    estimate is the difference of the observed rates, not the bootstrap mean,
    so the reported delta is a measured number rather than a resampled one.
    """
    if not passes_a or not passes_b:
        raise ValueError("bootstrap_delta_ci: an arm has no tasks")
    if resamples <= 0:
        raise ValueError(f"bootstrap_delta_ci: resamples must be > 0, "
                         f"got {resamples}")

    na, nb = len(passes_a), len(passes_b)
    point = sum(passes_a) / na - sum(passes_b) / nb

    rng = random.Random(seed)
    deltas: list[float] = []
    for _ in range(resamples):
        hit_a = sum(passes_a[rng.randrange(na)] for _ in range(na))
        hit_b = sum(passes_b[rng.randrange(nb)] for _ in range(nb))
        deltas.append(hit_a / na - hit_b / nb)
    deltas.sort()

    lo_idx = int(math.floor((alpha / 2.0) * resamples))
    hi_idx = min(resamples - 1, int(math.ceil((1.0 - alpha / 2.0) * resamples)) - 1)
    return {
        "point": point,
        "lo": deltas[lo_idx],
        "hi": deltas[hi_idx],
        "resamples": resamples,
        "seed": seed,
    }
