#!/usr/bin/env python3
"""Pure-Python (stdlib only) RV32I ISS — G2 oracle for the fpga-agent-loop judge.

Semantics match judge/SPEC.md exactly:
  - flat 64 KiB little-endian RAM at 0x0000_0000
  - store to 0x1000_0000 ends the test (recorded as "tohost")
  - ECALL / EBREAK / illegal opcode / misaligned load-store /
    misaligned jump target / misaligned fetch -> trap, CPU halts
  - loads outside RAM return 0, stores outside RAM (except tohost)
    are dropped; both match the Verilator memory model in tb.cpp
  - FENCE executes as a NOP

Usage:
  iss.py run PROG.hex [--dump OUT.hex] [--max-steps N]
prints one result line:  STATUS=<status> TOHOST=0x........ STEPS=n TRAP_PC=0x........
status is one of: PASS (tohost==1), FAIL (tohost!=1), TRAP, TIMEOUT
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from memh import MEM_WORDS, load_memh, dump_memh

TOHOST_ADDR = 0x10000000
MEM_SIZE = MEM_WORDS * 4  # 64 KiB in bytes


class Trap(Exception):
    pass


class RV32ISS:
    def __init__(self, words):
        self.mem = bytearray(MEM_SIZE)
        for i, w in enumerate(words[:MEM_WORDS]):
            self.mem[i * 4:i * 4 + 4] = (w & 0xFFFFFFFF).to_bytes(4, "little")
        self.regs = [0] * 32
        self.pc = 0
        self.tohost = None      # value written to 0x10000000
        self.trap = False
        self.trap_pc = 0
        self.steps = 0

    # ---- memory helpers -------------------------------------------------
    def _in_ram(self, addr):
        return 0 <= addr < MEM_SIZE

    def read32(self, addr):
        if not self._in_ram(addr):
            return 0
        return int.from_bytes(self.mem[addr:addr + 4], "little")

    def read_mem(self, addr, size, signed):
        # misalignment checked by caller before this is invoked
        if not self._in_ram(addr):
            return 0
        v = int.from_bytes(self.mem[addr:addr + size], "little")
        if signed and v & (1 << (size * 8 - 1)):
            v -= 1 << (size * 8)
        return v & 0xFFFFFFFF

    def write_mem(self, addr, value, size):
        if addr == TOHOST_ADDR:
            self.tohost = value & 0xFFFFFFFF
            return
        if not self._in_ram(addr):
            return  # dropped, matches tb.cpp
        self.mem[addr:addr + size] = (value & ((1 << size * 8) - 1)).to_bytes(size, "little")

    def setreg(self, rd, value):
        if rd:
            self.regs[rd] = value & 0xFFFFFFFF

    @staticmethod
    def s32(v):
        return v - (1 << 32) if v & 0x80000000 else v

    # ---- one instruction ------------------------------------------------
    def step(self):
        pc = self.pc
        if pc % 4 or not self._in_ram(pc):
            raise Trap()
        insn = self.read32(pc)
        npc = (pc + 4) & 0xFFFFFFFF
        op = insn & 0x7F
        rd = (insn >> 7) & 0x1F
        f3 = (insn >> 12) & 0x7
        rs1 = (insn >> 15) & 0x1F
        rs2 = (insn >> 20) & 0x1F
        f7 = insn >> 25
        self.pc = npc

        if op == 0x37:                      # LUI
            self.setreg(rd, insn & 0xFFFFF000)
        elif op == 0x17:                    # AUIPC
            self.setreg(rd, (pc + (insn & 0xFFFFF000)) & 0xFFFFFFFF)
        elif op == 0x6F:                    # JAL
            imm = (((insn >> 31) & 1) << 20) | (((insn >> 12) & 0xFF) << 12) | \
                  (((insn >> 20) & 1) << 11) | (((insn >> 21) & 0x3FF) << 1)
            if imm & (1 << 20):
                imm -= 1 << 21
            self.setreg(rd, npc)
            self._jump((pc + imm) & 0xFFFFFFFF)
        elif op == 0x67:                    # JALR
            if f3 != 0:
                raise Trap()
            imm = insn >> 20
            if imm & 0x800:
                imm -= 1 << 12
            tgt = ((self.regs[rs1] + imm) & 0xFFFFFFFF) & ~1
            self.setreg(rd, npc)
            self._jump(tgt)
        elif op == 0x63:                    # branches
            imm = (((insn >> 31) & 1) << 12) | (((insn >> 7) & 1) << 11) | \
                  (((insn >> 25) & 0x3F) << 5) | (((insn >> 8) & 0xF) << 1)
            if imm & (1 << 12):
                imm -= 1 << 13
            a, b = self.regs[rs1], self.regs[rs2]
            sa, sb = self.s32(a), self.s32(b)
            taken = {0x0: a == b, 0x1: a != b, 0x4: sa < sb,
                     0x5: sa >= sb, 0x6: a < b, 0x7: a >= b}.get(f3)
            if taken is None:
                raise Trap()
            if taken:
                self._jump((pc + imm) & 0xFFFFFFFF)
        elif op == 0x03:                    # loads
            imm = insn >> 20
            if imm & 0x800:
                imm -= 1 << 12
            addr = (self.regs[rs1] + imm) & 0xFFFFFFFF
            need = {0x0: 1, 0x1: 2, 0x2: 4, 0x4: 1, 0x5: 2}.get(f3)
            if need is None or addr % need:
                raise Trap()
            self.setreg(rd, self.read_mem(addr, need, f3 in (0x0, 0x1, 0x2)))
        elif op == 0x23:                    # stores
            imm = ((insn >> 25) << 5) | ((insn >> 7) & 0x1F)
            if imm & 0x800:
                imm -= 1 << 12
            addr = (self.regs[rs1] + imm) & 0xFFFFFFFF
            need = {0x0: 1, 0x1: 2, 0x2: 4}.get(f3)
            if need is None or addr % need:
                raise Trap()
            self.write_mem(addr, self.regs[rs2], need)
        elif op == 0x13:                    # OP-IMM
            imm = insn >> 20
            simm = imm - (1 << 12) if imm & 0x800 else imm
            a = self.regs[rs1]
            if f3 == 0x0:
                r = a + simm
            elif f3 == 0x1:                 # SLLI
                if f7 not in (0x00, 0x01):
                    raise Trap()
                r = a << (rs2 & 0x1F)
            elif f3 == 0x2:
                r = int(self.s32(a) < simm)
            elif f3 == 0x3:
                # SLTIU: sign-extend imm to 32 bits, then compare unsigned
                r = int(a < (simm & 0xFFFFFFFF))
            elif f3 == 0x4:
                r = a ^ (simm & 0xFFFFFFFF)
            elif f3 == 0x6:
                r = a | (simm & 0xFFFFFFFF)
            elif f3 == 0x7:
                r = a & (simm & 0xFFFFFFFF)
            elif f3 == 0x5:                 # SRLI / SRAI
                sh = rs2 & 0x1F
                if f7 == 0x00:
                    r = a >> sh
                elif f7 == 0x20:
                    r = self.s32(a) >> sh
                else:
                    raise Trap()
            else:
                raise Trap()
            self.setreg(rd, r)
        elif op == 0x33:                    # OP
            a, b = self.regs[rs1], self.regs[rs2]
            if f3 == 0x0:
                if f7 == 0x00:
                    r = a + b
                elif f7 == 0x20:
                    r = a - b
                else:
                    raise Trap()
            elif f3 == 0x1 and f7 == 0x00:
                r = a << (b & 0x1F)
            elif f3 == 0x2 and f7 == 0x00:
                r = int(self.s32(a) < self.s32(b))
            elif f3 == 0x3 and f7 == 0x00:
                r = int(a < b)
            elif f3 == 0x4 and f7 == 0x00:
                r = a ^ b
            elif f3 == 0x5:
                sh = b & 0x1F
                if f7 == 0x00:
                    r = a >> sh
                elif f7 == 0x20:
                    r = self.s32(a) >> sh
                else:
                    raise Trap()
            elif f3 == 0x6 and f7 == 0x00:
                r = a | b
            elif f3 == 0x7 and f7 == 0x00:
                r = a & b
            else:
                raise Trap()
            self.setreg(rd, r)
        elif op == 0x0F:                    # FENCE
            if f3 != 0:                     # FENCE.I is NOT in the ISA
                raise Trap()                # (SPEC: RV32I minus FENCE.I)
            pass                            # FENCE executes as a NOP
        elif op == 0x73:                    # ECALL / EBREAK / CSR -> trap
            raise Trap()
        else:
            raise Trap()

    def _jump(self, target):
        if target % 4:
            raise Trap()
        self.pc = target

    def run(self, max_steps=200000):
        while self.tohost is None and not self.trap and self.steps < max_steps:
            try:
                self.step()
            except Trap:
                self.trap = True
                self.trap_pc = self.pc if self.pc % 4 == 0 else self.pc & ~3
            self.steps += 1
        if self.trap:
            return "TRAP"
        if self.tohost is None:
            return "TIMEOUT"
        return "PASS" if self.tohost == 1 else "FAIL"

    def image(self):
        return [int.from_bytes(self.mem[i * 4:i * 4 + 4], "little")
                for i in range(MEM_WORDS)]


def main(argv):
    if len(argv) < 3 or argv[1] != "run":
        print(__doc__)
        return 2
    prog, dump, max_steps = argv[2], None, 200000
    i = 3
    while i < len(argv):
        if argv[i] == "--dump":
            dump = argv[i + 1]; i += 2
        elif argv[i] == "--max-steps":
            max_steps = int(argv[i + 1]); i += 2
        else:
            return 2
    iss = RV32ISS(load_memh(prog))
    status = iss.run(max_steps)
    if dump:
        dump_memh(iss.image(), dump)
    th = "--------" if iss.tohost is None else "0x%08x" % iss.tohost
    print("STATUS=%s TOHOST=%s STEPS=%d TRAP_PC=0x%08x"
          % (status, th, iss.steps, iss.trap_pc))
    return 0 if status in ("PASS", "FAIL", "TRAP") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
