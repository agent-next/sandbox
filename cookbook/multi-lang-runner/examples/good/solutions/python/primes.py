#!/usr/bin/env python3
"""P3 primes: count primes p with lo <= p <= hi, simple sieve."""
import sys

def main():
    data = sys.stdin.read().split()
    if len(data) < 2:
        return 1
    lo = int(data[0])
    hi = int(data[1])
    if hi < 2:
        sys.stdout.write("0\n")
        return 0
    sieve = bytearray([1]) * (hi + 1)
    sieve[0] = sieve[1] = 0
    i = 2
    while i * i <= hi:
        if sieve[i]:
            sieve[i * i::i] = bytearray(len(sieve[i * i::i]))
        i += 1
    count = sum(sieve[lo:hi + 1])
    sys.stdout.write(str(count) + "\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
