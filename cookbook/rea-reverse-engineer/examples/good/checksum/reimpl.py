#!/usr/bin/env python3
"""reimpl.py -- Python re-implementation of the stripped `checksum` binary.

Recovered algorithm (from REA/Ghidra pseudocode of the core routine):
    h = 0xCBF29CE484222325
    for each input byte b:
        h ^= b
        h = rotl64(h, 5)
        h += 0x9E3779B97F4A7C15
        h ^= h >> 29
    print("%016x\n" % h)
"""
import sys

MASK = (1 << 64) - 1

h = 0xCBF29CE484222325
for b in sys.stdin.buffer.read(1 << 20):
    h ^= b
    h = ((h << 5) | (h >> 59)) & MASK
    h = (h + 0x9E3779B97F4A7C15) & MASK
    h ^= h >> 29
sys.stdout.write("%016x\n" % h)
