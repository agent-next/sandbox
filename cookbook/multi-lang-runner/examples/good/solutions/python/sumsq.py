#!/usr/bin/env python3
"""P1 sumsq: sum of squares, capped at 10^18."""
import sys

def main():
    data = sys.stdin.read().split()
    if not data:
        return 1
    n = int(data[0])
    total = 0
    for i in range(1, n + 1):
        x = int(data[i])
        total += x * x
        if total > 10 ** 18:
            total = 10 ** 18
            break
    sys.stdout.write(str(total) + "\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
