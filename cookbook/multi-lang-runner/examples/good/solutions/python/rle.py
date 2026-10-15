#!/usr/bin/env python3
"""P2 rle: run-length encode, count+char pairs."""
import sys

def main():
    s = sys.stdin.read().rstrip("\n")
    if not s:
        return 0
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
    sys.stdout.write("".join(out) + "\n")
    return 0

if __name__ == "__main__":
    sys.exit(main())
