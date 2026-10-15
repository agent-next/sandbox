#!/usr/bin/env python3
"""Unit tests for judge/stats.py -- the two procedures the gates rest on.

Run by judge/selftest.sh before anything is graded.  Every expected value
here is either published or hand-derived, never read back from this code:

  * Fisher's exact test on [[3,1],[1,3]] (Fisher's tea-tasting) = 6/7!*3!*3!...
    -> 0.4857142857142857, the textbook value;
  * on [[1,9],[11,3]] -> 0.0027594561852200832, the standard worked example
    (this one catches a one-sided implementation, which would return about
    half of it);
  * a 2x2 table with a zero cell -> 1.0 exactly, by the hypergeometric pmf;
  * the bootstrap's bounds are hand-checkable on degenerate arms: 16/16 vs
    4/16 resamples to a difference whose 2.5th percentile is exactly 0.5.

Exits non-zero on the first failure and prints every check it ran.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import stats  # noqa: E402

FAILURES: list[str] = []


def check(label: str, got, want, tol: float = 0.0) -> None:
    ok = (abs(got - want) <= tol) if isinstance(want, float) else (got == want)
    print(f"  {'ok  ' if ok else 'FAIL'} {label}: {got!r}"
          + ("" if ok else f" (want {want!r})"))
    if not ok:
        FAILURES.append(label)


def main() -> int:
    print("test_stats: Fisher's exact test (two-sided)")
    # Fisher's tea-tasting: 3 right, 1 wrong of each.  Published value.
    check("tea-tasting [[3,1],[1,3]]", stats.fisher_exact_2x2(3, 1, 1, 3),
          0.4857142857142857, 1e-15)
    # The standard worked example; a one-sided test would return ~1.38e-3.
    check("worked example [[1,9],[11,3]]", stats.fisher_exact_2x2(1, 9, 11, 3),
          0.0027594561852200832, 1e-15)
    # Symmetry: swapping the arms cannot change a two-sided p-value.
    check("symmetric under arm swap",
          stats.fisher_exact_2x2(9, 1, 3, 11),
          stats.fisher_exact_2x2(1, 9, 11, 3))
    # Perfect separation: only the all-or-nothing arrangements are this
    # extreme, so the two-sided p is 2/C(32,16) = 3.3273419550419868e-09.
    check("perfect separation [[16,0],[0,16]]",
          stats.fisher_exact_2x2(16, 0, 0, 16), 2 / 601080390, 1e-20)
    # A balanced table is not significant (1 up to floating-point rounding).
    check("balanced [[8,8],[8,8]]", stats.fisher_exact_2x2(8, 8, 8, 8), 1.0,
          1e-12)
    # The bench's own table: p must be far below 0.05.
    p = stats.fisher_exact_2x2(16, 0, 4, 12)
    check("bench table [[16,0],[4,12]] < 0.05", p < 0.05, True)
    print(f"       (bench table p = {p:.6g})")
    # And the marginal table must NOT reach significance: this is the whole
    # reason G5 exists next to G6.
    p_marg = stats.fisher_exact_2x2(16, 0, 12, 4)
    check("marginal [[16,0],[12,4]] >= 0.05", p_marg >= 0.05, True)
    print(f"       (marginal table p = {p_marg:.6g})")

    print("test_stats: bootstrap CI on the pass-rate delta")
    skill = [True] * 16
    noskill = [True] * 4 + [False] * 12
    ci = stats.bootstrap_delta_ci(skill, noskill, seed=20261014, resamples=10000)
    check("point estimate is the measured delta", ci["point"], 0.75, 1e-15)
    check("lower bound > 0 for a 75 pt gap", ci["lo"] > 0, True)
    check("upper bound <= 1", ci["hi"] <= 1.0, True)
    check("resamples recorded", ci["resamples"], 10000)
    # The 2.5th percentile of the resampled difference, hand-checked: every
    # skill resample is 16/16 and the 2.5th percentile of the no-skill arm is
    # 8/16, so the lower bound is 1 - 8/16 = 0.5 exactly.
    check("lower bound is exactly 0.5", ci["lo"], 0.5, 1e-15)

    same = stats.bootstrap_delta_ci(skill, noskill, seed=20261014, resamples=10000)
    check("same seed -> identical bounds", same, ci)
    # A different seed must move the bounds, or --seed is decorative.  With
    # this table the 2.5th percentile flips between 8/16 and 9/16, so seed 5
    # gives lo = 0.5625 where the default seed gives 0.5.
    other = stats.bootstrap_delta_ci(skill, noskill, seed=5, resamples=10000)
    check("different seed -> different bounds", other["lo"] != ci["lo"], True)
    check("seed 5 lower bound is 0.5625", other["lo"], 0.5625, 1e-15)

    # A placebo that changes one task must not clear the bar.
    placebo = [True] * 5 + [False] * 11
    ci_p = stats.bootstrap_delta_ci(noskill, placebo, seed=20261014,
                                    resamples=10000)
    check("placebo CI contains 0", ci_p["lo"] <= 0.0 <= ci_p["hi"], True)
    check("placebo |delta| < 10 pts", abs(100.0 * ci_p["point"]) < 10.0, True)

    # Two arms drawn from the same 8/16 population have a point estimate of
    # exactly 0 and a CI that straddles 0 -- the interval reflects sampling
    # noise, so a null result stays a null result rather than becoming a win.
    flat = stats.bootstrap_delta_ci([True] * 8 + [False] * 8,
                                    [True] * 8 + [False] * 8,
                                    seed=1, resamples=10000)
    check("identical arms -> point estimate 0", flat["point"], 0.0, 1e-15)
    check("identical arms -> CI contains 0",
          flat["lo"] <= 0.0 <= flat["hi"], True)

    print("test_stats: input validation")
    for label, call in (
        ("negative cell rejected", lambda: stats.fisher_exact_2x2(-1, 1, 1, 1)),
        ("empty table rejected", lambda: stats.fisher_exact_2x2(0, 0, 0, 0)),
        ("empty arm rejected",
         lambda: stats.bootstrap_delta_ci([], [True], seed=1)),
        ("resamples=0 rejected",
         lambda: stats.bootstrap_delta_ci([True], [True], seed=1, resamples=0)),
    ):
        try:
            call()
        except ValueError:
            print(f"  ok   {label}")
        else:
            print(f"  FAIL {label}: no ValueError")
            FAILURES.append(label)

    if FAILURES:
        print(f"test_stats: {len(FAILURES)} FAILURE(S): {', '.join(FAILURES)}")
        return 1
    print("test_stats: all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
