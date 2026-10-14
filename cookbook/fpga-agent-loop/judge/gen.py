#!/usr/bin/env python3
"""Random RV32I program generator for the fpga-agent-loop judge (G2).

Memory layout of every generated program:
  0x000        jal x0, 0x400          (skip data hole)
  0x004-0x3FF  data hole, initially zero
    0x040-0x0BC  signature region: x1..x31 stored here by the epilogue
    0x100-0x3FC  scratch region for loads/stores (x0- or base-reg addressed)
  0x400-...    program body (deterministic coverage block, then random filler,
               then the epilogue)

The epilogue stores x1..x31 to the signature region and then stores 1 to
tohost (0x10000000). All generated loads/stores/branches/jumps are aligned
and in-range by construction, and every branch/jump target is a real
instruction boundary, so a correct program always ends via tohost.

Coverage (deterministic part, present in every program):
  - every RV32I instruction in the SPEC list
  - every branch taken and not taken, including BACKWARD branches
    (bounded counter loop; rv32ui has no backward control flow at all)
  - JAL and JALR both forward and backward (flag-guarded, run exactly twice)
  - every load/store width and sign via x0 base and a nonzero base register

Usage: gen.py --seed S --count K --len L [--out FILE | --outdir DIR]
  Fixed seed -> byte-identical .hex output (programs are pure functions of
  (program_seed, len)). Program i of a run uses program_seed(seed, i).
Default length: 500 body instructions (SPEC G2 default).
"""

import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from memh import MEM_WORDS, dump_memh

SIG_BASE = 0x040            # x1 -> 0x040 .. x31 -> 0x0B8
SCRATCH_LO, SCRATCH_HI = 0x100, 0x3FC   # inclusive byte range
CODE_BASE = 0x400
TOHOST = 0x10000000


def program_seed(base_seed, index):
    """Deterministic per-program seed: program i of --seed S run."""
    return base_seed * 1000003 + index


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


# ---- tiny two-pass assembler (labels + control flow) --------------------
class Asm:
    """Assemble a list of items into instruction words.

    Items:
      int                       pre-encoded word
      ("label", name)           define a label at this position
      ("br", f3, r1, r2, label) branch to label
      ("jal", rd, label)        JAL to label
      ("jalr_rel", rd, base, label)
                                auipc base,0; addi base,base,delta; jalr rd,base
                                (3 instructions; delta is label - auipc pc)
    """

    def __init__(self):
        self.items = []

    def emit(self, word):
        self.items.append(word)

    def label(self, name):
        self.items.append(("label", name))

    def br(self, f3, r1, r2, label):
        self.items.append(("br", f3, r1, r2, label))

    def jal(self, rd, label):
        self.items.append(("jal", rd, label))

    def jalr_rel(self, rd, base, label):
        self.items.append(("jalr_rel", rd, base, label))

    def assemble(self):
        pos = {}                 # label -> word index
        pc = 0
        sizes = []
        for it in self.items:
            if isinstance(it, int):
                sizes.append(1)
            elif it[0] == "label":
                pos[it[1]] = pc
                sizes.append(0)
            elif it[0] == "jalr_rel":
                sizes.append(3)
            else:
                sizes.append(1)
            pc += 4 * sizes[-1]      # pc tracks byte addresses
        end_pc = pc
        out = []
        pc = 0
        i = 0
        for it in self.items:
            n = sizes[i]
            i += 1
            if n == 0:
                continue
            if isinstance(it, int):
                out.append(it)
            elif it[0] == "br":
                out.append(_branch(it[1], it[2], it[3],
                                   pos[it[4]] - pc))
            elif it[0] == "jal":
                out.append(jal(it[1], pos[it[2]] - pc))
            elif it[0] == "jalr_rel":
                _, rd, base, label = it
                delta = pos[label] - pc       # pc is the auipc's own address
                assert -2048 <= delta <= 2047
                out += [auipc(base, 0),
                        addi(base, base, delta & 0xFFF),
                        jalr(rd, base, 0)]
            pc += 4 * n
        assert pc == end_pc
        return out


# ---- directed coverage block -------------------------------------------
def coverage_block():
    """Exercise every RV32I instruction in the SPEC list, each load/store
    width and sign, every branch taken and not taken (both directions),
    and JAL/JALR forward and backward."""
    a = Asm()
    # interesting operand seeds
    a.emit(lui(5, 0x80000))            # x5 = 0x80000000
    a.emit(addi(6, 0, -1))             # x6 = 0xFFFFFFFF
    a.emit(addi(7, 0, 1))              # x7 = 1
    a.emit(lui(8, 0x7FFFF))            # x8 = 0x7FFFF000
    a.emit(auipc(9, 0x12345))
    a.emit(addi(10, 0, -2048))         # x10 = 0xFFFFF800
    a.emit(addi(11, 0, 2047))
    a.emit(addi(28, 0, 2))             # x28 = 2 (pass flag compare value)
    # R-type ALU
    for w in [add(12, 5, 7), sub(12, 7, 5), sll(13, 7, 7),
              slt(14, 5, 7), slt(14, 7, 5), sltu(14, 5, 7), sltu(14, 7, 5),
              xor_(15, 5, 6), srl(16, 5, 7), sra(17, 5, 7), sra(17, 7, 5),
              or_(18, 5, 7), and_(19, 5, 6)]:
        a.emit(w)
    # I-type ALU
    for w in [addi(20, 5, 2047), slti(21, 5, 0), slti(21, 7, -1),
              sltiu(21, 5, 1), sltiu(21, 7, -1), xori(22, 6, -1),
              xori(22, 6, 0x555), ori(23, 5, 0x555), andi(24, 6, 0x555),
              slli(25, 5, 31), slli(25, 7, 5), srli(26, 5, 31),
              srli(26, 6, 4), srai(27, 5, 31), srai(27, 6, 4)]:
        a.emit(w)
    # loads/stores every width and sign, via x0 base and nonzero base
    for w in [addi(26, 0, -1),
              sw(26, 0, 0x100), lb(29, 0, 0x100), lbu(29, 0, 0x101),
              lh(29, 0, 0x100), lhu(29, 0, 0x102), lw(29, 0, 0x100),
              sb(26, 0, 0x105), sh(26, 0, 0x106), sw(26, 0, 0x108),
              lb(30, 0, 0x105), lh(30, 0, 0x106), lw(30, 0, 0x108)]:
        a.emit(w)
    a.emit(addi(31, 0, 0x200))          # nonzero base register
    for w in [sw(26, 31, 0x40), lw(29, 31, 0x40), sb(26, 31, 0x50),
              lbu(30, 31, 0x50), sh(26, 31, 0x52), lhu(30, 31, 0x52)]:
        a.emit(w)
    # each branch taken and not taken (forward)
    for w in [beq(0, 0, 8), addi(1, 1, 1),            # taken
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
              bgeu(7, 5, 8), addi(1, 1, 1)]:          # not taken
        a.emit(w)
    # JAL forward over one instruction
    a.emit(jal(2, 8))
    a.emit(addi(1, 1, 1))
    a.emit(addi(3, 0, 0x33))
    # JALR forward: base = pc(auipc)+16 -> lands on addi after the jalr
    a.jalr_rel(2, 4, "JALR_FW_TGT")
    a.emit(addi(1, 1, 1))
    a.label("JALR_FW_TGT")
    a.emit(addi(3, 3, 1))
    # backward branch, taken then not taken: bounded counter loop.
    # rv32ui has NO backward control flow; this is G2-specific coverage.
    a.emit(addi(26, 0, 5))             # loop counter
    a.label("LOOP_BWD")
    a.emit(addi(26, 26, -1))
    a.br(1, 26, 0, "LOOP_BWD")         # bne x26, x0, back: taken 4x, then not
    # backward JAL, flag-guarded (body executes exactly twice)
    a.emit(addi(27, 0, 0))             # pass flag
    a.label("JAL_BWD")
    a.emit(addi(27, 27, 1))
    a.br(0, 27, 28, "JAL_BWD_OVER")    # pass 2 (flag==2): skip the jal
    a.jal(29, "JAL_BWD")               # backward JAL, pass 1 only
    a.label("JAL_BWD_OVER")
    # backward JALR, flag-guarded (auipc/addi/jalr back to the label)
    a.emit(addi(27, 0, 0))
    a.label("JALR_BWD")
    a.emit(addi(27, 27, 1))
    a.br(0, 27, 28, "JALR_BWD_OVER")
    a.jalr_rel(0, 30, "JALR_BWD")      # backward JALR via auipc+addi, pass 1
    a.label("JALR_BWD_OVER")
    a.emit(fence())
    return a.assemble()


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


def _base_off(rng, align):
    """(base, off) pair: base is a 12-bit-aligned scratch address loaded
    into x31, off a non-negative aligned offset; base+off <= SCRATCH_HI."""
    base = rng.randrange(SCRATCH_LO, SCRATCH_LO + 0x100, align)
    off = rng.randrange(0, (SCRATCH_HI - base) // align + 1) * align
    return base, off


# filler unit kinds -> number of instructions each emits
_U_INSNS = {"BR": 1, "JAL": 1, "JALR": 3}


def random_units(rng, n_target):
    """Random filler. Each unit is (kind, payload); control-flow units
    carry their own target choice so every emitted offset is computed from
    TRUE instruction positions (unit length = instructions emitted).
    Branches/jumps are forward-only here (backward control flow lives in
    the deterministic coverage block, where it is provably terminating);
    targets are always the start of a later unit, never offset 0."""
    units = []
    n = 0
    while n < n_target:
        k = rng.random()
        if k < 0.30:                                   # R-type
            units.append(("I", [rng.choice(R_OPS)(_rand_reg(rng),
                                                  _rand_reg(rng),
                                                  _rand_reg(rng))]))
        elif k < 0.55:                                 # I-type ALU
            if rng.random() < 0.3:
                units.append(("I", [rng.choice(SH_OPS)(_rand_reg(rng),
                                                       _rand_reg(rng),
                                                       rng.randrange(32))]))
            else:
                units.append(("I", [rng.choice(I_OPS)(_rand_reg(rng),
                                                     _rand_reg(rng),
                                                     rng.randrange(-2048, 2048))]))
        elif k < 0.67:                                 # load
            op, al = rng.choice(L_OPS)
            if rng.random() < 0.6:
                units.append(("I", [op(_rand_reg(rng), 0,
                                       _scratch_addr(rng, al))]))
            else:
                base, off = _base_off(rng, al)
                units.append(("I", [addi(31, 0, base),
                                    op(_rand_reg(rng), 31, off)]))
        elif k < 0.75:                                 # store
            op, al = rng.choice(S_OPS)
            if rng.random() < 0.6:
                units.append(("I", [op(_rand_reg(rng), 0,
                                       _scratch_addr(rng, al))]))
            else:
                base, off = _base_off(rng, al)
                units.append(("I", [addi(31, 0, base),
                                    op(_rand_reg(rng), 31, off)]))
        elif k < 0.85:                                 # forward branch
            f3 = rng.choice((0, 1, 4, 5, 6, 7))        # valid branch funct3
            units.append(("BR", (f3, _rand_reg(rng), _rand_reg(rng),
                                 rng.randrange(1, 5))))
        elif k < 0.90:                                 # JAL forward
            units.append(("JAL", (_rand_reg(rng), rng.randrange(1, 5))))
        elif k < 0.94:                                 # JALR (3-insn unit)
            units.append(("JALR", (_rand_reg(rng), _rand_reg(rng),
                                   rng.randrange(1, 4))))
        elif k < 0.97:                                 # LUI / AUIPC
            f = lui if rng.random() < 0.5 else auipc
            units.append(("I", [f(_rand_reg(rng), rng.randrange(0x100000))]))
        else:
            units.append(("I", [fence()]))
        kind, payload = units[-1]
        n += len(payload) if kind == "I" else _U_INSNS[kind]

    # true instruction positions (byte addresses)
    pcs = []
    pc = 0
    for kind, payload in units:
        ninsn = len(payload) if kind == "I" else _U_INSNS[kind]
        pcs.append(pc)
        pc += 4 * ninsn
    end_pc = pc

    out = []
    nunits = len(units)
    for i, (kind, payload) in enumerate(units):
        # target: start of a strictly later unit (or the filler end);
        # clamped so every control unit has a target with offset != 0
        def tgt_pc(i, skip):
            j = min(i + skip, nunits)      # nunits -> end of filler
            return end_pc if j == nunits else pcs[j]

        if kind == "BR":
            f3, r1, r2, skip = payload
            out.append(_branch(f3, r1, r2, tgt_pc(i, skip) - pcs[i]))
        elif kind == "JAL":
            rd, skip = payload
            out.append(jal(rd, tgt_pc(i, skip) - pcs[i]))
        elif kind == "JALR":
            rd, base, skip = payload
            delta = tgt_pc(i, skip) - pcs[i]   # bytes, from the auipc
            assert -2048 <= delta <= 2047
            out += [auipc(base, 0),
                    addi(base, base, delta & 0xFFF),
                    jalr(rd, base, 0)]
        else:
            out += payload
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
    p.add_argument("--count", type=int, default=1,
                   help="number of programs (program i uses program_seed(seed, i))")
    p.add_argument("--len", type=int, default=500,
                   help="body instruction count per program (SPEC default 500)")
    p.add_argument("--out", default=None,
                   help="output .hex (single program only)")
    p.add_argument("--outdir", default=None,
                   help="output directory: writes prog_<pseed>.hex per program")
    a = p.parse_args(argv[1:])
    if a.count < 1:
        p.error("--count must be >= 1")
    if a.count > 1 and not a.outdir:
        p.error("--count > 1 requires --outdir")
    if a.count == 1 and not (a.out or a.outdir):
        a.out = "-"                # single program to stdout by default
    for i in range(a.count):
        pseed = program_seed(a.seed, i)
        words = generate(pseed, a.len)
        if a.outdir:
            dump_memh(words, os.path.join(a.outdir, "prog_%d.hex" % pseed))
        elif a.out == "-":
            from memh import words_to_memh
            sys.stdout.write(words_to_memh(words))
        else:
            dump_memh(words, a.out)
    if a.outdir:
        print("%d program(s) written to %s" % (a.count, a.outdir))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
