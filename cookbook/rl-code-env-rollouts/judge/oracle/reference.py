"""The judge's own reference implementations for all 20 tasks.

This module is the acceptance oracle for the task bank.  It shares no code
with `tasks/gen_tasks.py` and is written independently: different algorithms
where the generator used a loop, a table-driven Roman numeral encoder, a
memoised Levenshtein, and so on.  Gate 1 (`bank_valid`) requires the bank's
stored expectations to agree with these on all 100 tests, so a bank whose
`expect` values drifted from the task descriptions cannot be graded at all.

The functions are looked up by name from the bank's `entry` field.
"""

import math
from functools import lru_cache


def add(a, b):
    return sum((a, b))


def gcd(a, b):
    return math.gcd(a, b)


def is_prime(n):
    if n < 2:
        return False
    return all(n % k for k in range(2, int(math.isqrt(n)) + 1))


def factorial(n):
    return math.prod(range(2, n + 1)) if n > 1 else 1


def fib(n):
    # Fast doubling: different algorithm from the generator's iterative loop.
    def fd(k):
        if k == 0:
            return 0, 1
        a, b = fd(k >> 1)
        c = a * (2 * b - a)
        d = a * a + b * b
        return (d, c + d) if k & 1 else (c, d)
    return fd(n)[0]


def reverse_string(s):
    return "".join(reversed(s))


def count_vowels(s):
    return len([c for c in s if c in ("a", "e", "i", "o", "u")])


def sum_digits(n):
    return sum(map(int, str(n)))


def is_palindrome(s):
    return all(s[i] == s[-1 - i] for i in range(len(s) // 2))


def clamp(x, lo, hi):
    return min(hi, max(lo, x))


def mean(xs):
    return sum(xs) / float(len(xs))


def unique_sorted(xs):
    out = []
    for x in sorted(xs):
        if not out or out[-1] != x:
            out.append(x)
    return out


def base_convert(n, b):
    if n == 0:
        return "0"
    digits = "0123456789abcdef"
    out = []
    while n > 0:
        n, r = divmod(n, b)
        out.append(digits[r])
    return "".join(reversed(out))


def run_length_encode(s):
    if not s:
        return ""
    out = []
    prev, count = s[0], 1
    for c in s[1:]:
        if c == prev:
            count += 1
        else:
            out.append("%s%d" % (prev, count))
            prev, count = c, 1
    out.append("%s%d" % (prev, count))
    return "".join(out)


def is_anagram(a, b):
    from collections import Counter
    return Counter(a) == Counter(b)


def binary_search(xs, target):
    lo, hi = 0, len(xs)
    while lo < hi:
        mid = (lo + hi) // 2
        if xs[mid] < target:
            lo = mid + 1
        else:
            hi = mid
    return lo if lo < len(xs) and xs[lo] == target else -1


def chunk(xs, k):
    return [xs[i:i + k] for i in range(0, len(xs), k)]


_ROMAN = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
          (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
          (5, "V"), (4, "IV"), (1, "I")]


def roman(n):
    out = []
    for value, sym in _ROMAN:
        count, n = divmod(n, value)
        out.append(sym * count)
    return "".join(out)


@lru_cache(maxsize=None)
def edit_distance(a, b):
    if not a:
        return len(b)
    if not b:
        return len(a)
    return min(edit_distance(a[:-1], b) + 1,
               edit_distance(a, b[:-1]) + 1,
               edit_distance(a[:-1], b[:-1]) + (a[-1] != b[-1]))


def matrix_transpose(m):
    return [list(col) for col in zip(*m)]


# entry name -> callable
REFERENCE = {
    "add": add, "gcd": gcd, "is_prime": is_prime, "factorial": factorial,
    "fib": fib, "reverse_string": reverse_string, "count_vowels": count_vowels,
    "sum_digits": sum_digits, "is_palindrome": is_palindrome, "clamp": clamp,
    "mean": mean, "unique_sorted": unique_sorted, "base_convert": base_convert,
    "run_length_encode": run_length_encode, "is_anagram": is_anagram,
    "binary_search": binary_search, "chunk": chunk, "roman": roman,
    "edit_distance": edit_distance, "matrix_transpose": matrix_transpose,
}


def run_entry(entry, args):
    """Call the reference for `entry` on `args`; raises if unknown."""
    return REFERENCE[entry](*args)
