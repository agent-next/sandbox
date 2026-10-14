#!/usr/bin/env python3
"""Grade one controller artifact. Prints a JSON verdict, exits 0 only if all
gates pass. Usage: grade.py <artifact.json> [--seed N] [--json out.json]
[--no-mc]"""
import argparse
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import judge_lib


def load_artifact(path):
    """Parse and validate the artifact. Returns (Q, R) or raises ValueError."""
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    if not isinstance(raw, dict):
        raise ValueError("artifact must be a JSON object")
    if set(raw.keys()) != {"type", "Q", "R"}:
        raise ValueError(f"artifact keys must be exactly type,Q,R; "
                         f"got {sorted(raw.keys())}")
    if raw["type"] != "lqr":
        raise ValueError(f"type must be \"lqr\", got {raw['type']!r}")
    weights = []
    for key, n in (("Q", 4), ("R", 2)):
        val = raw[key]
        if not isinstance(val, list) or len(val) != n:
            raise ValueError(f"{key} must be a list of {n} numbers")
        for i, v in enumerate(val):
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ValueError(f"{key}[{i}] is not a number")
            if not math.isfinite(v):
                raise ValueError(f"{key}[{i}] is not finite")
        weights.append(np.array(val, dtype=float))
    Q, R = weights
    # Q must be elementwise >= 0, strictly positive on positions (0, 2);
    # R must be strictly positive (an LQR input penalty of 0 is ill-posed)
    if np.any(Q < 0):
        raise ValueError("Q must be elementwise non-negative")
    for i in (0, 2):
        if Q[i] <= 0:
            raise ValueError(f"Q[{i}] (position weight) must be > 0")
    if np.any(R <= 0):
        raise ValueError("R must be elementwise > 0")
    return Q, R


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=20260101)
    ap.add_argument("--json", dest="json_out", default=None,
                    help="also write the verdict JSON to this path")
    ap.add_argument("--no-mc", action="store_true",
                    help="skip the Monte-Carlo gate (selftest speed-up)")
    args = ap.parse_args()

    try:
        Q, R = load_artifact(args.artifact)
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        verdict = {"passed": False, "error": f"invalid artifact: {exc}",
                   "gates": {}}
        print(json.dumps(verdict, indent=2))
        if args.json_out:
            with open(args.json_out, "w", encoding="utf-8") as fh:
                json.dump(verdict, fh, indent=2)
        return 1

    verdict = judge_lib.evaluate(Q, R, seed=args.seed,
                                 run_mc=not args.no_mc)
    print(json.dumps(verdict, indent=2))
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(verdict, fh, indent=2)
    return 0 if verdict["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
