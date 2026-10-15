#!/usr/bin/env python3
"""Generate the task bank the demo's environment is built over.

The bank is data, not code: `tasks/tasks.json` is committed and is the
public contract between the environment under test and the judge.

    python3 tasks/gen_tasks.py --seed 20261015 --out tasks/tasks.json

Twenty small programming tasks, five hidden tests each.  Test inputs are
drawn from `random.Random(seed * 1000 + task_index)`, so the bank depends on
`--seed` and on nothing else -- no clock, no hash randomisation, no
platform.  Regenerating with the same seed must produce the same file byte
for byte; the judge checks the stored expectations against its own
independent reference implementations before grading anything.

The reference implementations *here* are the generator's: they exist to fill
in `expect`.  The judge carries a second, independently written set in
`judge/oracle/reference.py` and gate 1 requires the two to agree on all 100
tests.  Neither is derived from the other.
"""

import argparse
import json
import math
import random
import sys

# --------------------------------------------------------------------------
# Generator-side reference implementations.
#
# Each entry is (task_id, entry_name, prompt, cases) where `cases` is a list
# of (args, expect) pairs built by a per-task function that takes a seeded
# random.Random.
# --------------------------------------------------------------------------


def g_add(rng):
    cases = []
    for _ in range(5):
        a, b = rng.randint(-50, 50), rng.randint(-50, 50)
        cases.append(([a, b], a + b))
    return cases


def g_gcd(rng):
    cases = []
    for _ in range(5):
        a, b = rng.randint(1, 200), rng.randint(1, 200)
        cases.append(([a, b], math.gcd(a, b)))
    return cases


def g_is_prime(rng):
    cases = []
    for _ in range(3):
        n = rng.randint(2, 200)
        cases.append(([n], all(n % d for d in range(2, int(n ** 0.5) + 1))))
    cases.append(([1], False))
    cases.append(([97], True))
    return cases


def g_factorial(rng):
    cases = []
    for _ in range(4):
        n = rng.randint(0, 12)
        cases.append(([n], math.factorial(n)))
    cases.append(([0], 1))
    return cases


def g_fib(rng):
    cases = []
    for _ in range(4):
        n = rng.randint(0, 25)
        a, b = 0, 1
        for _ in range(n):
            a, b = b, a + b
        cases.append(([n], a))
    cases.append(([0], 0))
    return cases


def g_reverse_string(rng):
    cases = []
    for _ in range(4):
        s = "".join(rng.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(rng.randint(0, 12)))
        cases.append(([s], s[::-1]))
    cases.append((["abc"], "cba"))
    return cases


def g_count_vowels(rng):
    cases = []
    for _ in range(5):
        s = "".join(rng.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(rng.randint(1, 20)))
        cases.append(([s], sum(c in "aeiou" for c in s)))
    return cases


def g_sum_digits(rng):
    cases = []
    for _ in range(5):
        n = rng.randint(0, 10 ** 6)
        cases.append(([n], sum(int(c) for c in str(n))))
    return cases


def g_is_palindrome(rng):
    cases = []
    for _ in range(3):
        s = "".join(rng.choice("abc") for _ in range(rng.randint(1, 8)))
        cases.append(([s], s == s[::-1]))
    cases.append((["racecar"], True))
    cases.append((["abc"], False))
    return cases


def g_clamp(rng):
    cases = []
    for _ in range(5):
        x = rng.randint(-20, 20)
        lo = rng.randint(-20, 0)
        hi = rng.randint(0, 20)
        cases.append(([x, lo, hi], max(lo, min(hi, x))))
    return cases


def g_mean(rng):
    cases = []
    for _ in range(5):
        xs = [rng.randint(-30, 30) for _ in range(rng.randint(1, 8))]
        cases.append(([xs], float(sum(xs)) / len(xs)))
    return cases


def g_unique_sorted(rng):
    cases = []
    for _ in range(5):
        xs = [rng.randint(0, 12) for _ in range(rng.randint(1, 12))]
        cases.append(([xs], sorted(set(xs))))
    return cases


def g_base_convert(rng):
    digits = "0123456789abcdef"
    cases = []
    for _ in range(5):
        n = rng.randint(0, 4095)
        b = rng.randint(2, 16)
        if n == 0:
            s = "0"
        else:
            s, m = "", n
            while m:
                s = digits[m % b] + s
                m //= b
        cases.append(([n, b], s))
    return cases


def g_run_length_encode(rng):
    cases = []
    for _ in range(5):
        s = "".join(rng.choice("aabbc") for _ in range(rng.randint(1, 14)))
        out, i = "", 0
        while i < len(s):
            j = i
            while j < len(s) and s[j] == s[i]:
                j += 1
            out += "%s%d" % (s[i], j - i)
            i = j
        cases.append(([s], out))
    return cases


def g_is_anagram(rng):
    cases = []
    for _ in range(3):
        s = "".join(rng.choice("abcdef") for _ in range(rng.randint(1, 8)))
        t = list(s)
        rng.shuffle(t)
        cases.append(([s, "".join(t)], True))
    cases.append((["abc", "abd"], False))
    cases.append((["listen", "silent"], True))
    return cases


def g_binary_search(rng):
    cases = []
    for _ in range(5):
        xs = sorted(rng.sample(range(0, 60), rng.randint(1, 10)))
        target = xs[rng.randrange(len(xs))] if rng.random() < 0.6 else rng.randint(0, 59)
        idx = xs.index(target) if target in xs else -1
        cases.append(([xs, target], idx))
    return cases


def g_chunk(rng):
    cases = []
    for _ in range(5):
        xs = [rng.randint(0, 99) for _ in range(rng.randint(0, 9))]
        k = rng.randint(1, 4)
        cases.append(([xs, k], [xs[i:i + k] for i in range(0, len(xs), k)]))
    return cases


def g_roman(rng):
    table = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
             (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
             (5, "V"), (4, "IV"), (1, "I")]
    cases = []
    for _ in range(5):
        n = rng.randint(1, 3999)
        out, m = "", n
        for v, sym in table:
            while m >= v:
                out += sym
                m -= v
        cases.append(([n], out))
    return cases


def g_edit_distance(rng):
    def lev(a, b):
        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a, 1):
            cur = [i]
            for j, cb in enumerate(b, 1):
                cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                               prev[j - 1] + (ca != cb)))
            prev = cur
        return prev[-1]

    cases = []
    for _ in range(5):
        a = "".join(rng.choice("abc") for _ in range(rng.randint(0, 7)))
        b = "".join(rng.choice("abc") for _ in range(rng.randint(0, 7)))
        cases.append(([a, b], lev(a, b)))
    return cases


def g_matrix_transpose(rng):
    cases = []
    for _ in range(5):
        rows, cols = rng.randint(1, 4), rng.randint(1, 4)
        m = [[rng.randint(-9, 9) for _ in range(cols)] for _ in range(rows)]
        cases.append(([m], [list(r) for r in zip(*m)]))
    return cases


TASKS = [
    ("add", "add", "Write `add(a, b)` returning the sum of two integers.", g_add),
    ("gcd", "gcd", "Write `gcd(a, b)` returning the greatest common divisor of two positive integers.", g_gcd),
    ("is_prime", "is_prime", "Write `is_prime(n)` returning True if the integer n > 1 is prime, else False.", g_is_prime),
    ("factorial", "factorial", "Write `factorial(n)` returning n! for an integer n >= 0.", g_factorial),
    ("fib", "fib", "Write `fib(n)` returning the n-th Fibonacci number, 0-indexed: fib(0)=0, fib(1)=1.", g_fib),
    ("reverse_string", "reverse_string", "Write `reverse_string(s)` returning the string s reversed.", g_reverse_string),
    ("count_vowels", "count_vowels", "Write `count_vowels(s)` returning how many characters of s are lowercase vowels aeiou.", g_count_vowels),
    ("sum_digits", "sum_digits", "Write `sum_digits(n)` returning the sum of the decimal digits of a non-negative integer n.", g_sum_digits),
    ("is_palindrome", "is_palindrome", "Write `is_palindrome(s)` returning True if s reads the same forwards and backwards.", g_is_palindrome),
    ("clamp", "clamp", "Write `clamp(x, lo, hi)` returning x limited to the inclusive range [lo, hi].", g_clamp),
    ("mean", "mean", "Write `mean(xs)` returning the arithmetic mean of a non-empty list of numbers, as a float.", g_mean),
    ("unique_sorted", "unique_sorted", "Write `unique_sorted(xs)` returning the distinct elements of xs in ascending order.", g_unique_sorted),
    ("base_convert", "base_convert", "Write `base_convert(n, b)` returning n as a lowercase string in base b (2 <= b <= 16).", g_base_convert),
    ("run_length_encode", "run_length_encode", "Write `run_length_encode(s)` returning each run of a repeated character as the character followed by its count, e.g. 'aabbb' -> 'a2b3'.", g_run_length_encode),
    ("is_anagram", "is_anagram", "Write `is_anagram(a, b)` returning True if a and b are anagrams of each other.", g_is_anagram),
    ("binary_search", "binary_search", "Write `binary_search(xs, target)` returning the index of target in the ascending list xs, or -1 if absent.", g_binary_search),
    ("chunk", "chunk", "Write `chunk(xs, k)` returning xs split into consecutive lists of at most k elements (k >= 1).", g_chunk),
    ("roman", "roman", "Write `roman(n)` returning the Roman numeral for an integer 1 <= n <= 3999, in uppercase.", g_roman),
    ("edit_distance", "edit_distance", "Write `edit_distance(a, b)` returning the Levenshtein distance between strings a and b.", g_edit_distance),
    ("matrix_transpose", "matrix_transpose", "Write `matrix_transpose(m)` returning the transpose of a rectangular list-of-lists m.", g_matrix_transpose),
]


def build(seed):
    if len(TASKS) != 20:
        raise SystemExit("the bank must hold exactly 20 tasks, has %d" % len(TASKS))
    out = []
    for index, (tid, entry, prompt, gen) in enumerate(TASKS):
        rng = random.Random(seed * 1000 + index)
        cases = gen(rng)
        if len(cases) != 5:
            raise SystemExit("task %s: %d tests, want 5" % (tid, len(cases)))
        tests = [{"args": args, "expect": expect} for args, expect in cases]
        out.append({"id": tid, "entry": entry, "prompt": prompt, "tests": tests})
    return out


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=20261015)
    ap.add_argument("--out", default="tasks/tasks.json")
    args = ap.parse_args(argv[1:])

    bank = build(args.seed)
    text = json.dumps({"schema": "rl-code-env-rollouts/tasks/1",
                       "seed": args.seed, "tasks": bank},
                      indent=1, sort_keys=True) + "\n"
    with open(args.out, "w") as fh:
        fh.write(text)
    print("%s: %d tasks, %d tests, seed %d"
          % (args.out, len(bank), sum(len(t["tests"]) for t in bank), args.seed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
