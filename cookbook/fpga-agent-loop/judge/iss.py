#!/usr/bin/env python3
"""
judge/iss.py — Pure Python RV32I instruction set simulator (stdlib only)
Implements the RV32I base ISA (minus FENCE.I, CSRs) for differential testing.
"""

import sys
import struct
from typing import Dict, List, Tuple, Optional

# RV32I opcodes and funct3/funct7
OPCODES = {
    'LUI': 0b0110111,
    'AUIPC': 0b0010111,
    'JAL': 0b1101111,
    'JALR': 0b1100111,
    'BRANCH': 0b1100011,
    'LOAD': 0b0000011,
    'STORE': 0b0100011,
    'OP_IMM': 0b0010011,
    'OP': 0b0110011,
    'FENCE': 0b0001111,
    'SYSTEM': 0b1110011,
}

FUNCT3 = {
    'BEQ': 0, 'BNE': 1, 'BLT': 4, 'BGE': 5, 'BLTU': 6, 'BGEU': 7,
    'LB': 0, 'LH': 1, 'LW': 2, 'LBU': 4, 'LHU': 5,
    'SB': 0, 'SH': 1, 'SW': 2,
    'ADDI': 0, 'SLTI': 2, 'SLTIU': 3, 'XORI': 4, 'ORI': 6, 'ANDI': 7,
    'SLLI': 1, 'SRLI': 5, 'SRAI': 5,
    'ADD': 0, 'SLL': 1, 'SLT': 2, 'SLTU': 3, 'XOR': 4, 'SRL': 5, 'OR': 6, 'AND': 7,
    'SUB': 0, 'SRA': 5,
}

FUNCT7 = {
    'SUB': 0b0100000,
    'SRA': 0b0100000,
    'SRL': 0b0000000,
    'SRAI': 0b0100000,
    'SRLI': 0b0000000,
}

def sign_extend(val: int, bits: int) -> int:
    """Sign-extend val from bits to 32-bit."""
    sign_bit = 1 << (bits - 1)
    return (val ^ sign_bit) - sign_bit

def sext_imm_i(imm: int) -> int:
    return sign_extend(imm & 0xFFF, 12)

def sext_imm_s(imm: int) -> int:
    return sign_extend(imm & 0xFFF, 12)

def sext_imm_b(imm: int) -> int:
    # B-type: imm[12|10:5|4:1|11]
    return sign_extend(((imm & 0x800) << 4) | ((imm & 0x7E0) << 20) | ((imm & 0x1E) << 7) | ((imm & 0x100) >> 4), 13)

def sext_imm_u(imm: int) -> int:
    return imm & 0xFFFFF000

def sext_imm_j(imm: int) -> int:
    # J-type: imm[20|10:1|11|19:12]
    return sign_extend(((imm & 0x80000) << 11) | ((imm & 0xFF000) >> 12) | (imm & 0x100000) | ((imm & 0x7FE) << 20), 21)

class RV32I_ISS:
    def __init__(self, mem_size: int = 64 * 1024):
        self.mem_size = mem_size
        self.mem = bytearray(mem_size)
        self.regs = [0] * 32
        self.pc = 0
        self.tohost_addr = 0x10000000
        self.trap = False
        self.trap_cause = 0  # 0=illegal, 1=ecall, 2=ebreak, 3=misaligned_load, 4=misaligned_store, 5=misaligned_jump

    def load_hex(self, hex_file: str, base: int = 0x80000000) -> None:
        """Load a Verilog hex file into memory."""
        with open(hex_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line.startswith('@'):
                    addr = int(line[1:], 16) - base
                elif line:
                    words = line.split()
                    for w in words:
                        if addr < self.mem_size:
                            val = int(w, 16)
                            self.mem[addr:addr+4] = struct.pack('<I', val)
                            addr += 4

    def load_program(self, program_bytes: bytes, base: int = 0) -> None:
        """Load raw program bytes into memory at base."""
        self.mem[base:base+len(program_bytes)] = program_bytes

    def read_mem(self, addr: int, width: int) -> int:
        """Read memory with sign/zero extension."""
        if addr + width > self.mem_size:
            self.trap = True
            self.trap_cause = 3  # misaligned load
            return 0
        val = struct.unpack('<I', self.mem[addr:addr+4] + b'\x00' * (4 - width))[0]
        if width == 1:
            return sign_extend(val & 0xFF, 8)
        elif width == 2:
            return sign_extend(val & 0xFFFF, 16)
        return val

    def read_mem_unsigned(self, addr: int, width: int) -> int:
        """Read memory zero-extended."""
        if addr + width > self.mem_size:
            self.trap = True
            self.trap_cause = 3
            return 0
        val = struct.unpack('<I', self.mem[addr:addr+4] + b'\x00' * (4 - width))[0]
        if width == 1:
            return val & 0xFF
        elif width == 2:
            return val & 0xFFFF
        return val

    def write_mem(self, addr: int, width: int, val: int) -> None:
        """Write memory."""
        if addr + width > self.mem_size:
            self.trap = True
            self.trap_cause = 4  # misaligned store
            return
        if width == 1:
            self.mem[addr] = val & 0xFF
        elif width == 2:
            struct.pack_into('<H', self.mem, addr, val & 0xFFFF)
        else:
            struct.pack_into('<I', self.mem, addr, val & 0xFFFFFFFF)

    def fetch(self) -> int:
        """Fetch 32-bit instruction at PC."""
        if self.pc + 4 > self.mem_size:
            self.trap = True
            self.trap_cause = 0
            return 0
        return struct.unpack('<I', self.mem[self.pc:self.pc+4])[0]

    def decode(self, inst: int) -> Tuple[str, dict]:
        """Decode instruction, return (name, fields)."""
        opcode = inst & 0x7F
        rd = (inst >> 7) & 0x1F
        funct3 = (inst >> 12) & 0x7
        rs1 = (inst >> 15) & 0x1F
        rs2 = (inst >> 20) & 0x1F
        funct7 = (inst >> 25) & 0x7F
        funct5 = (inst >> 25) & 0x1F

        # Immediate fields
        imm_i = (inst >> 20) & 0xFFF
        imm_s = ((inst >> 25) << 5) | ((inst >> 7) & 0x1F)
        imm_b = ((inst >> 31) << 12) | (((inst >> 7) & 1) << 11) | (((inst >> 25) & 0x3F) << 5) | (((inst >> 8) & 0xF) << 1)
        imm_u = inst & 0xFFFFF000
        imm_j = ((inst >> 31) << 20) | (((inst >> 12) & 0xFF) << 12) | (((inst >> 20) & 1) << 11) | (((inst >> 21) & 0x3FF) << 1)

        if opcode == OPCODES['LUI']:
            return 'LUI', {'rd': rd, 'imm': imm_u}
        elif opcode == OPCODES['AUIPC']:
            return 'AUIPC', {'rd': rd, 'imm': imm_u}
        elif opcode == OPCODES['JAL']:
            return 'JAL', {'rd': rd, 'imm': sext_imm_j(imm_j)}
        elif opcode == OPCODES['JALR']:
            return 'JALR', {'rd': rd, 'rs1': rs1, 'imm': sext_imm_i(imm_i)}
        elif opcode == OPCODES['BRANCH']:
            if funct3 == FUNCT3['BEQ']: return 'BEQ', {'rs1': rs1, 'rs2': rs2, 'imm': sext_imm_b(imm_b)}
            if funct3 == FUNCT3['BNE']: return 'BNE', {'rs1': rs1, 'rs2': rs2, 'imm': sext_imm_b(imm_b)}
            if funct3 == FUNCT3['BLT']: return 'BLT', {'rs1': rs1, 'rs2': rs2, 'imm': sext_imm_b(imm_b)}
            if funct3 == FUNCT3['BGE']: return 'BGE', {'rs1': rs1, 'rs2': rs2, 'imm': sext_imm_b(imm_b)}
            if funct3 == FUNCT3['BLTU']: return 'BLTU', {'rs1': rs1, 'rs2': rs2, 'imm': sext_imm_b(imm_b)}
            if funct3 == FUNCT3['BGEU']: return 'BGEU', {'rs1': rs1, 'rs2': rs2, 'imm': sext_imm_b(imm_b)}
        elif opcode == OPCODES['LOAD']:
            if funct3 == FUNCT3['LB']: return 'LB', {'rd': rd, 'rs1': rs1, 'imm': sext_imm_i(imm_i)}
            if funct3 == FUNCT3['LH']: return 'LH', {'rd': rd, 'rs1': rs1, 'imm': sext_imm_i(imm_i)}
            if funct3 == FUNCT3['LW']: return 'LW', {'rd': rd, 'rs1': rs1, 'imm': sext_imm_i(imm_i)}
            if funct3 == FUNCT3['LBU']: return 'LBU', {'rd': rd, 'rs1': rs1, 'imm': sext_imm_i(imm_i)}
            if funct3 == FUNCT3['LHU']: return 'LHU', {'rd': rd, 'rs1': rs1, 'imm': sext_imm_i(imm_i)}
        elif opcode == OPCODES['STORE']:
            if funct3 == FUNCT3['SB']: return 'SB', {'rs1': rs1, 'rs2': rs2, 'imm': sext_imm_s(imm_s)}
            if funct3 == FUNCT3['SH']: return 'SH', {'rs1': rs1, 'rs2': rs2, 'imm': sext_imm_s(imm_s)}
            if funct3 == FUNCT3['SW']: return 'SW', {'rs1': rs1, 'rs2': rs2, 'imm': sext_imm_s(imm_s)}
        elif opcode == OPCODES['OP_IMM']:
            if funct3 == FUNCT3['ADDI']: return 'ADDI', {'rd': rd, 'rs1': rs1, 'imm': sext_imm_i(imm_i)}
            if funct3 == FUNCT3['SLTI']: return 'SLTI', {'rd': rd, 'rs1': rs1, 'imm': sext_imm_i(imm_i)}
            if funct3 == FUNCT3['SLTIU']: return 'SLTIU', {'rd': rd, 'rs1': rs1, 'imm': sext_imm_i(imm_i)}
            if funct3 == FUNCT3['XORI']: return 'XORI', {'rd': rd, 'rs1': rs1, 'imm': sext_imm_i(imm_i)}
            if funct3 == FUNCT3['ORI']: return 'ORI', {'rd': rd, 'rs1': rs1, 'imm': sext_imm_i(imm_i)}
            if funct3 == FUNCT3['ANDI']: return 'ANDI', {'rd': rd, 'rs1': rs1, 'imm': sext_imm_i(imm_i)}
            if funct3 == FUNCT3['SLLI'] and funct7 == 0: return 'SLLI', {'rd': rd, 'rs1': rs1, 'shamt': imm_i & 0x1F}
            if funct3 == FUNCT3['SRLI']:
                if funct7 == 0: return 'SRLI', {'rd': rd, 'rs1': rs1, 'shamt': imm_i & 0x1F}
                if funct7 == 0x20: return 'SRAI', {'rd': rd, 'rs1': rs1, 'shamt': imm_i & 0x1F}
        elif opcode == OPCODES['OP']:
            if funct3 == FUNCT3['ADD'] and funct7 == 0: return 'ADD', {'rd': rd, 'rs1': rs1, 'rs2': rs2}
            if funct3 == FUNCT3['ADD'] and funct7 == 0x20: return 'SUB', {'rd': rd, 'rs1': rs1, 'rs2': rs2}
            if funct3 == FUNCT3['SLL'] and funct7 == 0: return 'SLL', {'rd': rd, 'rs1': rs1, 'rs2': rs2}
            if funct3 == FUNCT3['SLT'] and funct7 == 0: return 'SLT', {'rd': rd, 'rs1': rs1, 'rs2': rs2}
            if funct3 == FUNCT3['SLTU'] and funct7 == 0: return 'SLTU', {'rd': rd, 'rs1': rs1, 'rs2': rs2}
            if funct3 == FUNCT3['XOR'] and funct7 == 0: return 'XOR', {'rd': rd, 'rs1': rs1, 'rs2': rs2}
            if funct3 == FUNCT3['SRL'] and funct7 == 0: return 'SRL', {'rd': rd, 'rs1': rs1, 'rs2': rs2}
            if funct3 == FUNCT3['SRL'] and funct7 == 0x20: return 'SRA', {'rd': rd, 'rs1': rs1, 'rs2': rs2}
            if funct3 == FUNCT3['OR'] and funct7 == 0: return 'OR', {'rd': rd, 'rs1': rs1, 'rs2': rs2}
            if funct3 == FUNCT3['AND'] and funct7 == 0: return 'AND', {'rd': rd, 'rs1': rs1, 'rs2': rs2}
        elif opcode == OPCODES['FENCE']:
            return 'FENCE', {}
        elif opcode == OPCODES['SYSTEM']:
            if funct3 == 0 and funct7 == 0:
                if rs2 == 0: return 'ECALL', {}
                if rs2 == 1: return 'EBREAK', {}
        return 'ILLEGAL', {'inst': inst}

    def execute(self, name: str, fields: dict) -> None:
        """Execute decoded instruction."""
        if name == 'ILLEGAL':
            self.trap = True
            self.trap_cause = 0
            return

        if name == 'LUI':
            self.regs[fields['rd']] = fields['imm'] & 0xFFFFFFFF
        elif name == 'AUIPC':
            self.regs[fields['rd']] = (self.pc + fields['imm']) & 0xFFFFFFFF
        elif name == 'JAL':
            self.regs[fields['rd']] = (self.pc + 4) & 0xFFFFFFFF
            self.pc = (self.pc + fields['imm']) & 0xFFFFFFFF
            return  # PC already updated
        elif name == 'JALR':
            target = (self.regs[fields['rs1']] + fields['imm']) & ~1
            if target & 3:
                self.trap = True
                self.trap_cause = 5  # misaligned jump
                return
            self.regs[fields['rd']] = (self.pc + 4) & 0xFFFFFFFF
            self.pc = target
            return
        elif name in ('BEQ', 'BNE', 'BLT', 'BGE', 'BLTU', 'BGEU'):
            rs1_val = self.regs[fields['rs1']]
            rs2_val = self.regs[fields['rs2']]
            taken = False
            if name == 'BEQ': taken = rs1_val == rs2_val
            elif name == 'BNE': taken = rs1_val != rs2_val
            elif name == 'BLT': taken = sign_extend(rs1_val, 32) < sign_extend(rs2_val, 32)
            elif name == 'BGE': taken = sign_extend(rs1_val, 32) >= sign_extend(rs2_val, 32)
            elif name == 'BLTU': taken = rs1_val < rs2_val
            elif name == 'BGEU': taken = rs1_val >= rs2_val
            if taken:
                self.pc = (self.pc + fields['imm']) & 0xFFFFFFFF
                return
        elif name == 'LB':
            addr = (self.regs[fields['rs1']] + fields['imm']) & 0xFFFFFFFF
            if addr & 3:
                self.trap = True
                self.trap_cause = 3
                return
            self.regs[fields['rd']] = self.read_mem(addr, 1)
        elif name == 'LH':
            addr = (self.regs[fields['rs1']] + fields['imm']) & 0xFFFFFFFF
            if addr & 1:
                self.trap = True
                self.trap_cause = 3
                return
            self.regs[fields['rd']] = self.read_mem(addr, 2)
        elif name == 'LW':
            addr = (self.regs[fields['rs1']] + fields['imm']) & 0xFFFFFFFF
            if addr & 3:
                self.trap = True
                self.trap_cause = 3
                return
            self.regs[fields['rd']] = self.read_mem(addr, 4)
        elif name == 'LBU':
            addr = (self.regs[fields['rs1']] + fields['imm']) & 0xFFFFFFFF
            if addr & 3:
                self.trap = True
                self.trap_cause = 3
                return
            self.regs[fields['rd']] = self.read_mem_unsigned(addr, 1)
        elif name == 'LHU':
            addr = (self.regs[fields['rs1']] + fields['imm']) & 0xFFFFFFFF
            if addr & 1:
                self.trap = True
                self.trap_cause = 3
                return
            self.regs[fields['rd']] = self.read_mem_unsigned(addr, 2)
        elif name == 'SB':
            addr = (self.regs[fields['rs1']] + fields['imm']) & 0xFFFFFFFF
            if addr & 3:
                self.trap = True
                self.trap_cause = 4
                return
            self.write_mem(addr, 1, self.regs[fields['rs2']])
        elif name == 'SH':
            addr = (self.regs[fields['rs1']] + fields['imm']) & 0xFFFFFFFF
            if addr & 1:
                self.trap = True
                self.trap_cause = 4
                return
            self.write_mem(addr, 2, self.regs[fields['rs2']])
        elif name == 'SW':
            addr = (self.regs[fields['rs1']] + fields['imm']) & 0xFFFFFFFF
            if addr & 3:
                self.trap = True
                self.trap_cause = 4
                return
            self.write_mem(addr, 4, self.regs[fields['rs2']])
        elif name == 'ADDI':
            self.regs[fields['rd']] = (self.regs[fields['rs1']] + fields['imm']) & 0xFFFFFFFF
        elif name == 'SLTI':
            self.regs[fields['rd']] = 1 if sign_extend(self.regs[fields['rs1']], 32) < sign_extend(fields['imm'], 32) else 0
        elif name == 'SLTIU':
            self.regs[fields['rd']] = 1 if self.regs[fields['rs1']] < (fields['imm'] & 0xFFFFFFFF) else 0
        elif name == 'XORI':
            self.regs[fields['rd']] = self.regs[fields['rs1']] ^ (fields['imm'] & 0xFFFFFFFF)
        elif name == 'ORI':
            self.regs[fields['rd']] = self.regs[fields['rs1']] | (fields['imm'] & 0xFFFFFFFF)
        elif name == 'ANDI':
            self.regs[fields['rd']] = self.regs[fields['rs1']] & (fields['imm'] & 0xFFFFFFFF)
        elif name == 'SLLI':
            self.regs[fields['rd']] = (self.regs[fields['rs1']] << fields['shamt']) & 0xFFFFFFFF
        elif name == 'SRLI':
            self.regs[fields['rd']] = self.regs[fields['rs1']] >> fields['shamt']
        elif name == 'SRAI':
            self.regs[fields['rd']] = sign_extend(self.regs[fields['rs1']], 32) >> fields['shamt']
        elif name == 'ADD':
            self.regs[fields['rd']] = (self.regs[fields['rs1']] + self.regs[fields['rs2']]) & 0xFFFFFFFF
        elif name == 'SUB':
            self.regs[fields['rd']] = (self.regs[fields['rs1']] - self.regs[fields['rs2']]) & 0xFFFFFFFF
        elif name == 'SLL':
            self.regs[fields['rd']] = (self.regs[fields['rs1']] << (self.regs[fields['rs2']] & 0x1F)) & 0xFFFFFFFF
        elif name == 'SLT':
            self.regs[fields['rd']] = 1 if sign_extend(self.regs[fields['rs1']], 32) < sign_extend(self.regs[fields['rs2']], 32) else 0
        elif name == 'SLTU':
            self.regs[fields['rd']] = 1 if self.regs[fields['rs1']] < self.regs[fields['rs2']] else 0
        elif name == 'XOR':
            self.regs[fields['rd']] = self.regs[fields['rs1']] ^ self.regs[fields['rs2']]
        elif name == 'SRL':
            self.regs[fields['rd']] = self.regs[fields['rs1']] >> (self.regs[fields['rs2']] & 0x1F)
        elif name == 'SRA':
            self.regs[fields['rd']] = sign_extend(self.regs[fields['rs1']], 32) >> (self.regs[fields['rs2']] & 0x1F)
        elif name == 'OR':
            self.regs[fields['rd']] = self.regs[fields['rs1']] | self.regs[fields['rs2']]
        elif name == 'AND':
            self.regs[fields['rd']] = self.regs[fields['rs1']] & self.regs[fields['rs2']]
        elif name == 'FENCE':
            pass  # NOP
        elif name == 'ECALL':
            self.trap = True
            self.trap_cause = 1
            return
        elif name == 'EBREAK':
            self.trap = True
            self.trap_cause = 2
            return

        # Default PC increment
        self.pc = (self.pc + 4) & 0xFFFFFFFF
        self.regs[0] = 0  # x0 hardwired to 0

    def run(self, max_cycles: int = 1000000) -> Tuple[bool, int]:
        """Run until trap or tohost write. Returns (success, cycles)."""
        cycles = 0
        while cycles < max_cycles and not self.trap:
            inst = self.fetch()
            if inst == 0:
                break
            name, fields = self.decode(inst)
            self.execute(name, fields)
            cycles += 1

            # Check for tohost write (end of test)
            if self.mem[self.tohost_addr:self.tohost_addr+4] != b'\x00\x00\x00\x00':
                tohost_val = struct.unpack('<I', self.mem[self.tohost_addr:self.tohost_addr+4])[0]
                if tohost_val != 0:
                    return tohost_val == 1, cycles

        return not self.trap, cycles

    def get_signature(self, sig_start: int, sig_end: int) -> bytes:
        """Get memory signature region."""
        return bytes(self.mem[sig_start:sig_end])

    def get_regs(self) -> List[int]:
        """Get register file."""
        return self.regs[:]


def run_iss(hex_file: str, max_cycles: int = 1000000) -> Tuple[bool, int, List[int], bytes]:
    """Run ISS on a hex file. Returns (passed, cycles, regs, signature)."""
    iss = RV32I_ISS()
    iss.load_hex(hex_file)
    passed, cycles = iss.run(max_cycles)
    regs = iss.get_regs()
    # Signature region at 0x1000-0x2000 (4KB)
    sig = iss.get_signature(0x1000, 0x2000)
    return passed, cycles, regs, sig


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: iss.py <hex_file> [max_cycles]")
        sys.exit(1)
    hex_file = sys.argv[1]
    max_cycles = int(sys.argv[2]) if len(sys.argv) > 2 else 1000000
    passed, cycles, regs, sig = run_iss(hex_file, max_cycles)
    print(f"Passed: {passed}, Cycles: {cycles}")
    print(f"Regs: {regs}")
    print(f"Signature: {sig.hex()}")