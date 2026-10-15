#!/usr/bin/env python3
"""Independent oracle for the multi-lang-runner demo.

Written from the problem statements in SPEC.md. Shares no code with any
solution. Used by the judge to compute expected stdout for each case, and by
gencases.py to validate the generator.

Each function takes the exact stdin string and returns the exact stdout bytes.
"""
import sys


def sumsq(stdin_text):
    """Sum of squares, capped at 10^18."""
    lines = stdin_text.split("\n")
    n = int(lines[0])
    total = 0
    for i in range(1, n + 1):
        x = int(lines[i])
        total += x * x
        if total > 10 ** 18:
            total = 10 ** 18
            break
    return str(total) + "\n"


def rle(stdin_text):
    """Run-length encode: count+char pairs, e.g. 'aaabb' -> '3a2b'."""
    s = stdin_text.rstrip("\n")
    if not s:
        return ""
    out = []
    prev = s[0]
    count = 1
    for ch in s[1:]:
        if ch == prev:
            count += 1
        else:
            out.append(str(count))
            out.append(prev)
            prev = ch
            count = 1
    out.append(str(count))
    out.append(prev)
    return "".join(out) + "\n"


def primes(stdin_text):
    """Count primes p with lo <= p <= hi, via simple sieve up to hi."""
    parts = stdin_text.split()
    lo = int(parts[0])
    hi = int(parts[1])
    if hi < 2:
        return "0\n"
    sieve = bytearray([1]) * (hi + 1)
    sieve[0] = sieve[1] = 0
    i = 2
    while i * i <= hi:
        if sieve[i]:
            sieve[i * i::i] = bytearray(len(sieve[i * i::i]))
        i += 1
    count = sum(sieve[lo:hi + 1])
    return str(count) + "\n"


ORACLES = {
    "sumsq": sumsq,
    "rle": rle,
    "primes": primes,
}


def main():
    """Usage: oracle.py <problem>  (reads stdin, writes oracle stdout)."""
    if len(sys.argv) != 2 or sys.argv[1] not in ORACLES:
        sys.stderr.write("usage: oracle.py <sumsq|rle|primes>\n")
        return 2
    data = sys.stdin.read()
    sys.stdout.write(ORACLES[sys.argv[1]](data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
