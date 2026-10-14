#!/usr/bin/env python3
"""Generate the fixed G6 performance benchmark for the fpga-agent-loop judge.

SPEC G6: "cycles for a fixed benchmark program (bubble sort of 64 words +
checksum) under 0-latency memory - report CPI (not a gate)".

Program layout (same convention as gen.py):
  0x000        jal x0, 0x400          (skip data hole)
  0x040        checksum word          (written by the epilogue)
  0x100-0x1FC  the 64-word array      (fixed LCG data, sorted in place)
  0x400-...    code

The program bubble-sorts the array (unsigned order), then stores the
mod-2^32 sum of the sorted words to the checksum slot and 1 to tohost
(0x10000000). It is a pure function: regeneration is byte-identical.

Usage: gen_bench.py [--out bench.hex]   (default: tests/perf/bench.hex)
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen
from memh import MEM_WORDS, dump_memh

HERE = os.path.dirname(os.path.abspath(__file__))

ARRAY_ADDR = 0x100            # 64 words: 0x100..0x1FC
ARRAY_N = 64
CHECKSUM_ADDR = 0x040
CODE_BASE = 0x400
TOHOST = 0x10000000


def array_data():
    """64 fixed pseudo-random words (LCG), same on every run."""
    x, out = 0x12345678, []
    for _ in range(ARRAY_N):
        x = (x * 1103515245 + 12345) & 0xFFFFFFFF
        out.append(x)
    return out


def bench_code():
    """Bubble sort (unsigned) + mod-2^32 checksum + tohost write.

    Registers:
      x5  = array base (0x100)      x6  = n (64)         x7 = i
      x8  = j / k                   x9  = a[j]           x10 = a[j+1]
      x11 = n-1                     x12 = &a[j]          x14 = n-1-i
      x15 = running checksum        x16 = swap flag
    """
    a = gen.Asm()
    a.emit(gen.addi(5, 0, ARRAY_ADDR))      # x5 = array base
    a.emit(gen.addi(6, 0, ARRAY_N))         # x6 = n
    a.emit(gen.addi(11, 6, -1))             # x11 = n-1
    a.emit(gen.addi(7, 0, 0))               # i = 0
    a.label("OUTER")
    a.emit(gen.sub(14, 11, 7))              # x14 = n-1-i  (inner trip count)
    a.emit(gen.addi(8, 0, 0))               # j = 0
    a.label("INNER")
    a.br(5, 8, 14, "INNER_END")             # bge: j >= n-1-i -> done
    a.emit(gen.slli(12, 8, 2))              # x12 = j*4
    a.emit(gen.add(12, 12, 5))              # x12 = &a[j]
    a.emit(gen.lw(9, 12, 0))
    a.emit(gen.lw(10, 12, 4))
    a.br(7, 10, 9, "NOSWAP")                # bgeu: a[j+1] >= a[j] -> keep
    a.emit(gen.sw(10, 12, 0))
    a.emit(gen.sw(9, 12, 4))
    a.label("NOSWAP")
    a.emit(gen.addi(8, 8, 1))               # j++
    a.jal(0, "INNER")
    a.label("INNER_END")
    a.emit(gen.addi(7, 7, 1))               # i++
    a.br(4, 7, 11, "OUTER")                 # blt: i < n-1 -> outer
    # checksum = sum(a[0..63]) mod 2^32
    a.emit(gen.addi(15, 0, 0))              # sum = 0
    a.emit(gen.addi(8, 0, 0))               # k = 0
    a.label("SUM")
    a.emit(gen.slli(12, 8, 2))
    a.emit(gen.add(12, 12, 5))
    a.emit(gen.lw(9, 12, 0))
    a.emit(gen.add(15, 15, 9))
    a.emit(gen.addi(8, 8, 1))
    a.br(4, 8, 6, "SUM")                    # blt: k < n -> sum
    a.emit(gen.sw(15, 0, CHECKSUM_ADDR))    # checksum -> 0x040
    a.emit(gen.lui(10, TOHOST >> 12))       # tohost = 1, ends the test
    a.emit(gen.addi(11, 0, 1))
    a.emit(gen.sw(11, 10, 0))
    a.emit(gen.jal(0, 0))                   # safety: self-loop
    return a.assemble()


def generate():
    words = [0] * MEM_WORDS
    words[0] = gen.jal(0, CODE_BASE)
    for i, w in enumerate(array_data()):
        words[ARRAY_ADDR // 4 + i] = w
    code = bench_code()
    assert CODE_BASE // 4 + len(code) <= MEM_WORDS
    for i, w in enumerate(code):
        words[CODE_BASE // 4 + i] = w
    return words


def main(argv):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", default=os.path.join(HERE, "tests", "perf",
                                                 "bench.hex"))
    a = p.parse_args(argv[1:])
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    dump_memh(generate(), a.out)
    print("wrote %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
