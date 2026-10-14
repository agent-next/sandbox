#!/usr/bin/env python3
"""Generate the directed trap-test programs for judge gate G3 (SPEC.md).

Each program first proves the CPU executes (two ALU ops), then issues one
trapping instruction; a "poison" store to tohost follows. A correct CPU
asserts `trap` and halts before the poison store; a CPU that fails to trap
either writes a non-1 value to tohost or runs to the timeout - the testbench
flags both as failure under --expect-trap.

Output: judge/tests/trap/<name>.hex, one memh image (word 0 = PC 0x0).

Deterministic and dependency-free: re-running never changes the images.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


# ---- minimal RV32I encoder ------------------------------------------------

def addi(rd, rs1, imm):
    return ((imm & 0xFFF) << 20) | (rs1 << 15) | (0 << 12) | (rd << 7) | 0x13


def lui(rd, imm20):
    return ((imm20 & 0xFFFFF) << 12) | (rd << 7) | 0x37


def lw(rd, rs1, imm):
    return ((imm & 0xFFF) << 20) | (rs1 << 15) | (0b010 << 12) | (rd << 7) | 0x03


def sw(rs2, rs1, imm):
    return (((imm >> 5) & 0x7F) << 25) | (rs2 << 20) | (rs1 << 15) | \
           (0b010 << 12) | (imm & 0x1F) << 7 | 0x23


def jalr(rd, rs1, imm):
    return ((imm & 0xFFF) << 20) | (rs1 << 15) | (0 << 12) | (rd << 7) | 0x67


def jal_self():
    return 0x0000006F  # jal x0, 0 -> tight self-loop


X0, X1, X5, X6, X8 = 0, 1, 5, 6, 8

# poison: sw x6, 0(x5)  -> writes 0x100 to tohost (never 1 -> FAIL if reached)
POISON = sw(X6, X5, 0)

# prologue: x1 = 1, x5 = 0x10000000 (tohost), x6 = 0x100 (scratch data area)
PROLOGUE = [
    addi(X1, X0, 1),
    lui(X5, 0x10000),
    addi(X6, X0, 0x100),
]


def program(trap_insn, extra_prologue=()):
    words = list(PROLOGUE) + list(extra_prologue)
    words.append(trap_insn)
    words.append(POISON)
    words.append(jal_self())
    return words


TRAP_TESTS = {
    # illegal opcode 0b1111111 (0xFFFFFFFF is not a legal RV32I instruction)
    "illinsn":        program(0xFFFFFFFF),
    # ECALL (SYSTEM, imm=0) / EBREAK (SYSTEM, imm=1)
    "ecall":          program(0x00000073),
    "ebreak":         program(0x00100073),
    # misaligned LW: lw x7, 3(x6) -> address 0x103, PC-relative data at 0x100
    "lw_misaligned":  program(lw(7, X6, 3)),
    # misaligned SW: sw x6, 3(x6) -> address 0x103
    "sw_misaligned":  program(sw(X6, X6, 3)),
    # misaligned jump target: jalr x0, 0(x8) with x8 = 2 -> fetch at 0x2
    "jump_misaligned": program(jalr(X0, X8, 0), extra_prologue=[addi(X8, X0, 2)]),
}


def to_memh(words):
    out = ["@0"]
    out += ["%08x" % (w & 0xFFFFFFFF) for w in words]
    return "\n".join(out) + "\n"


def main(argv):
    outdir = os.path.join(HERE, "tests", "trap")
    if len(argv) > 1:
        outdir = argv[1]
    os.makedirs(outdir, exist_ok=True)
    for name, words in sorted(TRAP_TESTS.items()):
        path = os.path.join(outdir, name + ".hex")
        with open(path, "w") as f:
            f.write(to_memh(words))
        print("%s: %d words" % (name, len(words)))
    print("wrote %d trap tests to %s" % (len(TRAP_TESTS), outdir))


if __name__ == "__main__":
    main(sys.argv)
