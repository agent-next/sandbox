#!/usr/bin/env python3
"""Deterministic case generator for the multi-lang-runner demo.

Generates >= 3 cases per problem under --cases-dir, driven by --seed.
Same seed -> same cases (byte-identical files). The judge uses these cases;
the oracle (oracle.py) is the source of expected output.

Usage: gencases.py --cases-dir DIR --seed N
"""
import argparse
import os
import random


def gen_sumsq_cases(seed):
    rng = random.Random(seed)
    cases = []
    # edge: single element
    cases.append("1\n7\n")
    # edge: all zeros
    cases.append("5\n0\n0\n0\n0\n0\n")
    # edge: negative values
    cases.append("3\n-3\n4\n-5\n")
    # edge: sum exceeds the 10^18 cap
    cases.append("3\n1000000000\n1000000000\n1000000000\n")
    # random
    for _ in range(2):
        n = rng.randint(1, 200)
        lines = [str(n)]
        for _ in range(n):
            lines.append(str(rng.randint(-10 ** 9, 10 ** 9)))
        cases.append("\n".join(lines) + "\n")
    return cases


def gen_rle_cases(seed):
    rng = random.Random(seed)
    cases = []
    # edge: single char
    cases.append("a\n")
    # edge: all same
    cases.append("zzzzzzzzzz\n")
    # edge: alternating
    cases.append("ababababab\n")
    # edge: two runs
    cases.append("aaabb\n")
    # random printable
    for _ in range(2):
        length = rng.randint(1, 500)
        chars = [chr(rng.randint(97, 122)) for _ in range(length)]
        cases.append("".join(chars) + "\n")
    return cases


def gen_primes_cases(seed):
    rng = random.Random(seed)
    cases = []
    # edge: lo == hi, non-prime
    cases.append("4 4\n")
    # edge: lo == hi, prime
    cases.append("7 7\n")
    # edge: full small range
    cases.append("0 10\n")
    # edge: hi < 2
    cases.append("0 1\n")
    # random
    for _ in range(2):
        lo = rng.randint(0, 10 ** 7 - 10)
        hi = lo + rng.randint(1, 10 ** 6)
        cases.append("%d %d\n" % (lo, hi))
    return cases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases-dir", required=True)
    ap.add_argument("--seed", type=int, default=20261015)
    args = ap.parse_args()

    gens = {
        "sumsq": gen_sumsq_cases,
        "rle": gen_rle_cases,
        "primes": gen_primes_cases,
    }
    os.makedirs(args.cases_dir, exist_ok=True)
    for prob, gen in gens.items():
        cases = gen(args.seed)
        for i, text in enumerate(cases):
            path = os.path.join(args.cases_dir, "%s_%d.in" % (prob, i))
            with open(path, "w") as f:
                f.write(text)
    total = sum(len(g(args.seed)) for g in gens.values())
    print("gencases: wrote %d cases to %s (seed=%d)" % (total, args.cases_dir, args.seed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
