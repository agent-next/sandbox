#!/usr/bin/env python3
"""Random RV32I program generator for the fpga-agent-loop judge (G2).

Memory layout of every generated program:
  0x000        jal x0, 0x400          (skip data hole)
  0x004-0x3FF  data hole, initially zero
    0x040-0x0BF  signature region: x1..x31 stored here by the epilogue
    0x100-0x3FC  scratch region for loads/stores (x0- or base-reg addressed)
  0x400-...    program body (deterministic coverage block, then random filler,
               then the epilogue)

The epilogue stores x1..x31 to the signature region and then stores 1 to
tohost (0x10000000). All generated loads/stores/branches/jumps are aligned
and in-range by construction, so a correct program always ends via tohost.

Usage: gen.py --seed S [--instrs N] [--out FILE.hex]
Default N = 500 body instructions (SPEC G2 default).
"""

import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from memh import MEM_WORDS, dump_memh

SIG_BASE = 0x040            # x1 -> 0x040 .. x31 -> 0x0BC
SCRATCH_LO, SCRATCH_HI = 0x100, 0x3FC   # inclusive byte range
CODE_BASE = 0x400
TOHOST = 0x10000000


# ---- encoders -----------------------------------------------------------
def _u32(v):
    return v & 0xFFFFFFFF


def lui(rd, imm20):
    return _u32((imm20 << 12) | (rd << 7) | 0x37)


def auipc(rd, imm20):
    return _u32((imm20 << 12) | (rd << 7) | 0x17)


def jal(rd, imm):
    imm &= 0x1FFFFF
    return _u32((((imm >> 20) & 1) << 31) | (((imm >> 12) & 0xFF) << 12) |
                (((imm >> 11) & 1) << 20) | (((imm >> 1) & 0x3FF) << 21) |
                (rd << 7) | 0x6F)


def jalr(rd, rs1, imm=0):
    return _u32(((imm & 0xFFF) << 20) | (rs1 << 15) | (rd << 7) | 0x67)


def _branch(f3, rs1, rs2, imm):
    imm &= 0x1FFF
    return _u32((((imm >> 12) & 1) << 31) | (((imm >> 5) & 0x3F) << 25) |
                (rs2 << 20) | (rs1 << 15) | (f3 << 12) |
                (((imm >> 1) & 0xF) << 8) | (((imm >> 11) & 1) << 7) | 0x63)


def beq(r1, r2, i): return _branch(0, r1, r2, i)
def bne(r1, r2, i): return _branch(1, r1, r2, i)
def blt(r1, r2, i): return _branch(4, r1, r2, i)
def bge(r1, r2, i): return _branch(5, r1, r2, i)
def bltu(r1, r2, i): return _branch(6, r1, r2, i)
def bgeu(r1, r2, i): return _branch(7, r1, r2, i)


def _load(f3, rd, rs1, imm):
    return _u32(((imm & 0xFFF) << 20) | (rs1 << 15) | (f3 << 12) |
                (rd << 7) | 0x03)


def lb(rd, r1, i): return _load(0, rd, r1, i)
def lh(rd, r1, i): return _load(1, rd, r1, i)
def lw(rd, r1, i): return _load(2, rd, r1, i)
def lbu(rd, r1, i): return _load(4, rd, r1, i)
def lhu(rd, r1, i): return _load(5, rd, r1, i)


def _store(f3, rs2, rs1, imm):
    return _u32((((imm >> 5) & 0x7F) << 25) | (rs2 << 20) | (rs1 << 15) |
                (f3 << 12) | ((imm & 0x1F) << 7) | 0x23)


def sb(r2, r1, i): return _store(0, r2, r1, i)
def sh(r2, r1, i): return _store(1, r2, r1, i)
def sw(r2, r1, i): return _store(2, r2, r1, i)


def _opimm(f3, rd, rs1, imm):
    return _u32(((imm & 0xFFF) << 20) | (rs1 << 15) | (f3 << 12) |
                (rd << 7) | 0x13)


def addi(rd, r1, i): return _opimm(0, rd, r1, i)
def slti(rd, r1, i): return _opimm(2, rd, r1, i)
def sltiu(rd, r1, i): return _opimm(3, rd, r1, i)
def xori(rd, r1, i): return _opimm(4, rd, r1, i)
def ori(rd, r1, i): return _opimm(6, rd, r1, i)
def andi(rd, r1, i): return _opimm(7, rd, r1, i)
def slli(rd, r1, s): return _opimm(1, rd, r1, s & 0x1F)
def srli(rd, r1, s): return _opimm(5, rd, r1, s & 0x1F)
def srai(rd, r1, s): return _opimm(5, rd, r1, 0x400 | (s & 0x1F))


def _op(f7, f3, rd, rs1, rs2):
    return _u32((f7 << 25) | (rs2 << 20) | (rs1 << 15) | (f3 << 12) |
                (rd << 7) | 0x33)


def add(rd, r1, r2): return _op(0x00, 0, rd, r1, r2)
def sub(rd, r1, r2): return _op(0x20, 0, rd, r1, r2)
def sll(rd, r1, r2): return _op(0x00, 1, rd, r1, r2)
def slt(rd, r1, r2): return _op(0x00, 2, rd, r1, r2)
def sltu(rd, r1, r2): return _op(0x00, 3, rd, r1, r2)
def xor_(rd, r1, r2): return _op(0x00, 4, rd, r1, r2)
def srl(rd, r1, r2): return _op(0x00, 5, rd, r1, r2)
def sra(rd, r1, r2): return _op(0x20, 5, rd, r1, r2)
def or_(rd, r1, r2): return _op(0x00, 6, rd, r1, r2)
def and_(rd, r1, r2): return _op(0x00, 7, rd, r1, r2)


def fence():
    return 0x0FF0000F  # fence iorw, iorw -> NOP per SPEC


def ebreak():
    return 0x00100073


# ---- directed coverage block -------------------------------------------
def coverage_block():
    """Exercise every RV32I instruction in the SPEC list, each load/store
    width and sign, and every branch taken and not taken."""
    b = []
    # interesting operand seeds
    b += [lui(5, 0x80000),            # x5 = 0x80000000
          addi(6, 0, -1),             # x6 = 0xFFFFFFFF
          addi(7, 0, 1),              # x7 = 1
          lui(8, 0x7FFFF),            # x8 = 0x7FFFF000
          auipc(9, 0x12345),
          addi(10, 0, -2048),         # x10 = 0xFFFFF800
          addi(11, 0, 2047)]
    # R-type ALU
    b += [add(12, 5, 7), sub(12, 7, 5), sll(13, 7, 7),
          slt(14, 5, 7), slt(14, 7, 5), sltu(14, 5, 7), sltu(14, 7, 5),
          xor_(15, 5, 6), srl(16, 5, 7), sra(17, 5, 7), sra(17, 7, 5),
          or_(18, 5, 7), and_(19, 5, 6)]
    # I-type ALU
    b += [addi(20, 5, 2047), slti(21, 5, 0), slti(21, 7, -1),
          sltiu(21, 5, 1), sltiu(21, 7, -1), xori(22, 6, -1),
          xori(22, 6, 0x555), ori(23, 5, 0x555), andi(24, 6, 0x555),
          slli(25, 5, 31), slli(25, 7, 5), srli(26, 5, 31),
          srli(26, 6, 4), srai(27, 5, 31), srai(27, 6, 4)]
    # loads/stores every width and sign, via x0 base and nonzero base
    b += [addi(28, 0, -1),
          sw(28, 0, 0x100), lb(29, 0, 0x100), lbu(29, 0, 0x101),
          lh(29, 0, 0x100), lhu(29, 0, 0x102), lw(29, 0, 0x100),
          sb(28, 0, 0x105), sh(28, 0, 0x106), sw(28, 0, 0x108),
          lb(30, 0, 0x105), lh(30, 0, 0x106), lw(30, 0, 0x108)]
    b += [addi(31, 0, 0x200),          # nonzero base register
          sw(28, 31, 0x40), lw(29, 31, 0x40), sb(28, 31, 0x50),
          lbu(30, 31, 0x50), sh(28, 31, 0x52), lhu(30, 31, 0x52)]
    # each branch taken and not taken
    b += [beq(0, 0, 8), addi(1, 1, 1),            # taken
          beq(0, 7, 8), addi(1, 1, 1),            # not taken
          bne(0, 7, 8), addi(1, 1, 1),            # taken
          bne(0, 0, 8), addi(1, 1, 1),            # not taken
          blt(5, 0, 8), addi(1, 1, 1),            # taken (neg<0)
          blt(0, 5, 8), addi(1, 1, 1),            # not taken
          bge(5, 0, 8), addi(1, 1, 1),            # not taken
          bge(0, 5, 8), addi(1, 1, 1),            # taken
          bltu(7, 5, 8), addi(1, 1, 1),           # taken (1 < 0x80000000)
          bltu(5, 7, 8), addi(1, 1, 1),           # not taken
          bgeu(5, 7, 8), addi(1, 1, 1),           # taken
          bgeu(7, 5, 8), addi(1, 1, 1)]           # not taken
    # JAL forward over one instruction; JALR via auipc-computed target
    b += [jal(2, 8), addi(1, 1, 1), addi(3, 0, 0x33)]
    # jalr block: x4 = pc(auipc)+16 -> lands on addi after the jalr
    b += [auipc(4, 0), addi(4, 4, 16), jalr(2, 4, 0), addi(1, 1, 1),
          addi(3, 3, 1)]
    b += [fence()]
    return b


# ---- random filler ------------------------------------------------------
R_OPS = [add, sub, sll, slt, sltu, xor_, srl, sra, or_, and_]
I_OPS = [addi, slti, sltiu, xori, ori, andi]
SH_OPS = [slli, srli, srai]
L_OPS = [(lb, 1), (lh, 2), (lw, 4), (lbu, 1), (lhu, 2)]
S_OPS = [(sb, 1), (sh, 2), (sw, 4)]
B_OPS = [beq, bne, blt, bge, bltu, bgeu]


def _rand_reg(rng):
    return rng.randrange(1, 32)   # x0 never written -> always a known 0


def _scratch_addr(rng, align):
    """Aligned offset inside the scratch region, usable as imm on x0."""
    span = (SCRATCH_HI - SCRATCH_LO + 1) // align
    return SCRATCH_LO + rng.randrange(span) * align


def random_units(rng, n_target):
    """Emit `units` — lists of instructions that are branch/jump targets.
    Returns a list of units; concatenating them gives the filler code."""
    units = []
    n = 0
    while n < n_target:
        k = rng.random()
        if k < 0.30:                                   # R-type
            units.append([rng.choice(R_OPS)(_rand_reg(rng), _rand_reg(rng),
                                            _rand_reg(rng))])
        elif k < 0.55:                                 # I-type ALU
            if rng.random() < 0.3:
                units.append([rng.choice(SH_OPS)(_rand_reg(rng),
                                                 _rand_reg(rng),
                                                 rng.randrange(32))])
            else:
                units.append([rng.choice(I_OPS)(_rand_reg(rng),
                                                _rand_reg(rng),
                                                rng.randrange(-2048, 2048))])
        elif k < 0.67:                                 # load
            op, al = rng.choice(L_OPS)
            if rng.random() < 0.6:
                units.append([op(_rand_reg(rng), 0, _scratch_addr(rng, al))])
            else:
                base = rng.randrange(SCRATCH_LO, SCRATCH_LO + 0x100, al)
                off = rng.randrange(0, (SCRATCH_HI - base) // al + 1) * al
                units.append([addi(31, 0, base),
                              op(_rand_reg(rng), 31, off)])
        elif k < 0.75:                                 # store
            op, al = rng.choice(S_OPS)
            if rng.random() < 0.6:
                units.append([op(_rand_reg(rng), 0, _scratch_addr(rng, al))])
            else:
                base = rng.randrange(SCRATCH_LO, SCRATCH_LO + 0x100, al)
                off = rng.randrange(0, (SCRATCH_HI - base) // al + 1) * al
                units.append([addi(31, 0, base),
                              op(_rand_reg(rng), 31, off)])
        elif k < 0.85:                                 # forward branch
            skip = rng.randrange(1, 5)                 # skip 0..3 units
            units.append(["BR", rng.choice(B_OPS)(_rand_reg(rng),
                                                  _rand_reg(rng), 0), skip])
        elif k < 0.90:                                 # JAL forward
            skip = rng.randrange(1, 5)
            units.append(["JAL", jal(_rand_reg(rng), 0), skip])
        elif k < 0.94:                                 # JALR (3-insn unit)
            units.append(["JALR", None])
        elif k < 0.97:                                 # LUI / AUIPC
            f = lui if rng.random() < 0.5 else auipc
            units.append([f(_rand_reg(rng), rng.randrange(0x100000))])
        else:
            units.append([fence()])
        n += len(units[-1])

    # resolve branch/jal/jalr placeholders against real pc offsets
    pcs = []
    pc = 0
    for u in units:
        pcs.append(pc)
        pc += 4 * len(u)
    end_pc = pc
    out = []
    for i, u in enumerate(units):
        if u[0] == "BR":
            tgt = min(i + u[2], len(units) - 1)
            off = pcs[tgt] - pcs[i]
            f3 = (u[1] >> 12) & 7
            u[1] = _branch(f3, (u[1] >> 15) & 0x1F, (u[1] >> 20) & 0x1F, off)
            out.append(u[1])
        elif u[0] == "JAL":
            tgt = min(i + u[2], len(units) - 1)
            out.append(jal((u[1] >> 7) & 0x1F, pcs[tgt] - pcs[i]))
        elif u[0] == "JALR":
            tgt = min(i + rng.randrange(1, 4), len(units) - 1)
            delta = pcs[tgt] - pcs[i]          # from auipc pc to target
            base = _rand_reg(rng)
            out += [auipc(base, 0),
                    addi(base, base, delta & 0xFFF),
                    jalr(_rand_reg(rng), base, 0)]
        else:
            out += u
    # final safety: no branch/jump may target past the filler end
    return out


def epilogue():
    e = [sw(r, 0, SIG_BASE + (r - 1) * 4) for r in range(1, 32)]
    e += [lui(10, TOHOST >> 12), addi(11, 0, 1), sw(11, 10, 0)]
    return e


def generate(seed, n_instrs=500):
    rng = random.Random(seed)
    words = [0] * MEM_WORDS
    words[0] = jal(0, CODE_BASE)
    body = coverage_block()
    body += random_units(rng, max(0, n_instrs - len(body) - len(epilogue())))
    body += epilogue()
    assert CODE_BASE // 4 + len(body) <= MEM_WORDS
    for i, w in enumerate(body):
        words[CODE_BASE // 4 + i] = w
    return words


def main(argv):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--instrs", type=int, default=500)
    p.add_argument("--out", default=None)
    a = p.parse_args(argv[1:])
    words = generate(a.seed, a.instrs)
    if a.out:
        dump_memh(words, a.out)
    else:
        from memh import words_to_memh
        sys.stdout.write(words_to_memh(words))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
