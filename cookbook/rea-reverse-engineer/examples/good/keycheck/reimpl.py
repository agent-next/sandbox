#!/usr/bin/env python3
"""reimpl.py -- Python re-implementation of the stripped `keycheck` binary.

Recovered rule: the key is XXXXX-XXXXX-XXXXX over the 32-symbol alphabet
"ABCDEFGHJKLMNPQRSTUVWXYZ23456789".  With v[i] the alphabet index of each
of the 15 key characters, the key is accepted iff
    (v[0] + v[5] + v[10]) % 32 == 9
    v[7] == (v[0] ^ v[14])
    sum(v[i] * (i % 5 + 1)) % 29 == 11
Prints OK / DENIED like the binary.
"""
import re
import sys

ALPHA = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

raw = sys.stdin.buffer.readline(64)[:63]
key = re.split(rb"[\r\n]", raw)[0].decode("latin-1")

ok = False
if len(key) == 17 and key[5] == "-" and key[11] == "-":
    v = [ALPHA.find(c) for i, c in enumerate(key) if i not in (5, 11)]
    if all(x >= 0 for x in v):
        w = sum(x * (i % 5 + 1) for i, x in enumerate(v))
        ok = ((v[0] + v[5] + v[10]) % 32 == 9
              and v[7] == (v[0] ^ v[14])
              and w % 29 == 11)

sys.stdout.write("OK\n" if ok else "DENIED\n")
sys.exit(0 if ok else 1)
