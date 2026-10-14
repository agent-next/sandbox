#!/usr/bin/env python3
"""
judge/gen.py — Random RV32I program generator (stdlib only, seeded)
Generates programs that end by storing x1..x31 to a signature region,
then store 1 to tohost (0x10000000).
"""

import sys
import random
import struct
from typing import List, Tuple, Optional

# RV32I instructions we can generate
# Each instruction: (name, format, operands...)
# Formats: R, I, S, B, U, J

INSTRUCTIONS = [
    # R-type (rd, rs1, rs2)
    ('ADD', 'R'), ('SUB', 'R'), ('SLL', 'R'), ('SLT', 'R'), ('SLTU', 'R'),
    ('XOR', 'R'), ('SRL', 'R'), ('SRA', 'R'), ('OR', 'R'), ('AND', 'R'),
    # I-type ALU (rd, rs1, imm)
    ('ADDI', 'I'), ('SLTI', 'I'), ('SLTIU', 'I'), ('XORI', 'I'), ('ORI', 'I'), ('ANDI', 'I'),
    ('SLLI', 'I'), ('SRLI', 'I'), ('SRAI', 'I'),
    # Loads (rd, rs1, imm)
    ('LB', 'I'), ('LH', 'I'), ('LW', 'I'), ('LBU', 'I'), ('LHU', 'I'),
    # Stores (rs1, rs2, imm)
    ('SB', 'S'), ('SH', 'S'), ('SW', 'S'),
    # Branches (rs1, rs2, imm)
    ('BEQ', 'B'), ('BNE', 'B'), ('BLT', 'B'), ('BGE', 'B'), ('BLTU', 'B'), ('BGEU', 'B'),
    # Jumps
    ('JAL', 'J'), ('JALR', 'I'),
    # Upper immediates
    ('LUI', 'U'), ('AUIPC', 'U'),
]

# Registers we can use (x1-x31, x0 is hardwired zero)
REGS = list(range(1, 32))

# Signature region: 0x1000-0x2000 (4KB, 1024 words)
SIG_START = 0x1000
SIG_END = 0x2000
TOHOST_ADDR = 0x10000000

# Memory size
MEM_SIZE = 64 * 1024
TEXT_START = 0x0000
DATA_START = 0x1000

def encode_r(opcode: int, funct3: int, funct7: int, rd: int, rs1: int, rs2: int) -> int:
    return (funct7 << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode

def encode_i(opcode: int, funct3: int, rd: int, rs1: int, imm: int) -> int:
    return ((imm & 0xFFF) << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | opcode

def encode_s(opcode: int, funct3: int, rs1: int, rs2: int, imm: int) -> int:
    return (((imm >> 5) & 0x7F) << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | ((imm & 0x1F) << 7) | opcode

def encode_b(opcode: int, funct3: int, rs1: int, rs2: int, imm: int) -> int:
    # B-type: imm[12|10:5|4:1|11]
    imm12 = (imm >> 12) & 1
    imm10_5 = (imm >> 5) & 0x3F
    imm4_1 = (imm >> 1) & 0xF
    imm11 = (imm >> 11) & 1
    return (imm12 << 31) | (imm10_5 << 25) | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (imm4_1 << 8) | (imm11 << 7) | opcode

def encode_u(opcode: int, rd: int, imm: int) -> int:
    return (imm & 0xFFFFF000) | (rd << 7) | opcode

def encode_j(opcode: int, rd: int, imm: int) -> int:
    # J-type: imm[20|10:1|11|19:12]
    imm20 = (imm >> 20) & 1
    imm10_1 = (imm >> 1) & 0x3FF
    imm11 = (imm >> 11) & 1
    imm19_12 = (imm >> 12) & 0xFF
    return (imm20 << 31) | (imm19_12 << 12) | (imm11 << 20) | (imm10_1 << 21) | (rd << 7) | opcode

# Opcode constants
OP_R = 0b0110011
OP_I_ALU = 0b0010011
OP_LOAD = 0b0000011
OP_STORE = 0b0100011
OP_BRANCH = 0b1100011
OP_JAL = 0b1101111
OP_JALR = 0b1100111
OP_LUI = 0b0110111
OP_AUIPC = 0b0010111

# Funct3 values
F3_BEQ = 0; F3_BNE = 1; F3_BLT = 4; F3_BGE = 5; F3_BLTU = 6; F3_BGEU = 7
F3_LB = 0; F3_LH = 1; F3_LW = 2; F3_LBU = 4; F3_LHU = 5
F3_SB = 0; F3_SH = 1; F3_SW = 2
F3_ADDI = 0; F3_SLTI = 2; F3_SLTIU = 3; F3_XORI = 4; F3_ORI = 6; F3_ANDI = 7
F3_SLLI = 1; F3_SRLI = 5; F3_SRAI = 5
F3_ADD = 0; F3_SLL = 1; F3_SLT = 2; F3_SLTU = 3; F3_XOR = 4; F3_SRL = 5; F3_OR = 6; F3_AND = 7
F3_SUB = 0; F3_SRA = 5

# Funct7 values
F7_SUB = 0b0100000
F7_SRA = 0b0100000
F7_SRL = 0b0000000
F7_SRAI = 0b0100000
F7_SRLI = 0b0000000

class ProgramGenerator:
    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.program: List[int] = []
        self.labels: dict = {}  # label_name -> pc_offset
        self.pending_branches: List[Tuple[int, int, str]] = []  # (pc_offset, target_label, branch_type)
        self.label_counter = 0
        self.used_regs = set(REGS)
        self.reg_values = {r: 0 for r in REGS}  # Track known register values

    def new_label(self) -> str:
        name = f"L{self.label_counter}"
        self.label_counter += 1
        return name

    def add_inst(self, inst: int):
        self.program.append(inst)

    def current_pc(self) -> int:
        return len(self.program) * 4

    def emit_r(self, name: str, rd: int, rs1: int, rs2: int):
        if name == 'ADD':
            self.add_inst(encode_r(OP_R, F3_ADD, 0, rd, rs1, rs2))
        elif name == 'SUB':
            self.add_inst(encode_r(OP_R, F3_SUB, F7_SUB, rd, rs1, rs2))
        elif name == 'SLL':
            self.add_inst(encode_r(OP_R, F3_SLL, 0, rd, rs1, rs2))
        elif name == 'SLT':
            self.add_inst(encode_r(OP_R, F3_SLT, 0, rd, rs1, rs2))
        elif name == 'SLTU':
            self.add_inst(encode_r(OP_R, F3_SLTU, 0, rd, rs1, rs2))
        elif name == 'XOR':
            self.add_inst(encode_r(OP_R, F3_XOR, 0, rd, rs1, rs2))
        elif name == 'SRL':
            self.add_inst(encode_r(OP_R, F3_SRL, F7_SRL, rd, rs1, rs2))
        elif name == 'SRA':
            self.add_inst(encode_r(OP_R, F3_SRA, F7_SRA, rd, rs1, rs2))
        elif name == 'OR':
            self.add_inst(encode_r(OP_R, F3_OR, 0, rd, rs1, rs2))
        elif name == 'AND':
            self.add_inst(encode_r(OP_R, F3_AND, 0, rd, rs1, rs2))

    def emit_i_alu(self, name: str, rd: int, rs1: int, imm: int):
        if name == 'ADDI':
            self.add_inst(encode_i(OP_I_ALU, F3_ADDI, rd, rs1, imm))
        elif name == 'SLTI':
            self.add_inst(encode_i(OP_I_ALU, F3_SLTI, rd, rs1, imm))
        elif name == 'SLTIU':
            self.add_inst(encode_i(OP_I_ALU, F3_SLTIU, rd, rs1, imm))
        elif name == 'XORI':
            self.add_inst(encode_i(OP_I_ALU, F3_XORI, rd, rs1, imm))
        elif name == 'ORI':
            self.add_inst(encode_i(OP_I_ALU, F3_ORI, rd, rs1, imm))
        elif name == 'ANDI':
            self.add_inst(encode_i(OP_I_ALU, F3_ANDI, rd, rs1, imm))
        elif name == 'SLLI':
            self.add_inst(encode_i(OP_I_ALU, F3_SLLI, rd, rs1, (imm & 0x1F) | (F7_SRLI << 5)))
        elif name == 'SRLI':
            self.add_inst(encode_i(OP_I_ALU, F3_SRLI, rd, rs1, (imm & 0x1F) | (F7_SRLI << 5)))
        elif name == 'SRAI':
            self.add_inst(encode_i(OP_I_ALU, F3_SRAI, rd, rs1, (imm & 0x1F) | (F7_SRAI << 5)))
        elif name == 'JALR':
            self.add_inst(encode_i(OP_JALR, 0, rd, rs1, imm))
        elif name in ('LB', 'LH', 'LW', 'LBU', 'LHU'):
            funct3 = {'LB': F3_LB, 'LH': F3_LH, 'LW': F3_LW, 'LBU': F3_LBU, 'LHU': F3_LHU}[name]
            self.add_inst(encode_i(OP_LOAD, funct3, rd, rs1, imm))

    def emit_s(self, name: str, rs1: int, rs2: int, imm: int):
        funct3 = {'SB': F3_SB, 'SH': F3_SH, 'SW': F3_SW}[name]
        self.add_inst(encode_s(OP_STORE, funct3, rs1, rs2, imm))

    def emit_b(self, name: str, rs1: int, rs2: int, target_label: str):
        funct3 = {'BEQ': F3_BEQ, 'BNE': F3_BNE, 'BLT': F3_BLT, 'BGE': F3_BGE, 'BLTU': F3_BLTU, 'BGEU': F3_BGEU}[name]
        pc = self.current_pc()
        self.add_inst(encode_b(OP_BRANCH, funct3, rs1, rs2, 0))  # placeholder
        self.pending_branches.append((pc, target_label, name))

    def emit_j(self, name: str, rd: int, target_label: str):
        pc = self.current_pc()
        self.add_inst(encode_j(OP_JAL, rd, 0))  # placeholder
        self.pending_branches.append((pc, target_label, name))

    def emit_u(self, name: str, rd: int, imm: int):
        opcode = {'LUI': OP_LUI, 'AUIPC': OP_AUIPC}[name]
        self.add_inst(encode_u(opcode, rd, imm))

    def resolve_branches(self):
        """Resolve all pending branch targets."""
        label_addrs = {name: addr for name, addr in self.labels.items()}
        for pc, target_label, branch_type in self.pending_branches:
            if target_label not in label_addrs:
                # Create a default target (next instruction)
                target_addr = pc + 4
            else:
                target_addr = label_addrs[target_label]

            offset = target_addr - pc
            # Check offset fits in 12/20 bits
            if branch_type in ('BEQ', 'BNE', 'BLT', 'BGE', 'BLTU', 'BGEU'):
                if offset < -2048 or offset > 2046:
                    offset = 0
                inst = self.program[pc // 4]
                rs1 = (inst >> 15) & 0x1F
                rs2 = (inst >> 20) & 0x1F
                funct3 = (inst >> 12) & 0x7
                self.program[pc // 4] = encode_b(OP_BRANCH, funct3, rs1, rs2, offset)
            elif branch_type in ('JAL',):
                if offset < -524288 or offset > 524286:
                    offset = 0
                inst = self.program[pc // 4]
                rd = (inst >> 7) & 0x1F
                self.program[pc // 4] = encode_j(OP_JAL, rd, offset)

    def set_label(self, name: str):
        self.labels[name] = self.current_pc()

    def random_reg(self, exclude: List[int] = None) -> int:
        exclude = exclude or []
        choices = [r for r in REGS if r not in exclude]
        return self.rng.choice(choices)

    def random_imm(self, bits: int = 12) -> int:
        if bits == 12:
            return self.rng.randint(-2048, 2047)
        elif bits == 20:
            return self.rng.randint(-524288, 524287)
        elif bits == 5:
            return self.rng.randint(0, 31)
        return 0

    def generate_program(self, num_instructions: int) -> bytes:
        """Generate a random program."""
        # Reserve space for signature store at the end
        # We'll store x1-x31 to signature region, then write tohost

        for i in range(num_instructions):
            # Occasionally create a label for branches to target
            if i > 0 and self.rng.random() < 0.05:
                label = self.new_label()
                self.set_label(label)

            # Pick a random instruction
            inst_name, fmt = self.rng.choice(INSTRUCTIONS)

            if fmt == 'R':
                rd = self.random_reg()
                rs1 = self.random_reg()
                rs2 = self.random_reg()
                self.emit_r(inst_name, rd, rs1, rs2)
            elif fmt == 'I':
                rd = self.random_reg()
                rs1 = self.random_reg()
                if inst_name in ('SLLI', 'SRLI', 'SRAI'):
                    imm = self.random_imm(5)
                else:
                    imm = self.random_imm(12)
                self.emit_i_alu(inst_name, rd, rs1, imm)
            elif fmt == 'S':
                rs1 = self.random_reg()
                rs2 = self.random_reg()
                imm = self.random_imm(12)
                self.emit_s(inst_name, rs1, rs2, imm)
            elif fmt == 'B':
                rs1 = self.random_reg()
                rs2 = self.random_reg()
                target = self.new_label()
                self.emit_b(inst_name, rs1, rs2, target)
                # Place the target label a few instructions ahead
                # We'll set it after a few more instructions
            elif fmt == 'J':
                rd = self.random_reg()
                target = self.new_label()
                self.emit_j(inst_name, rd, target)
            elif fmt == 'U':
                rd = self.random_reg()
                imm = self.random_imm(20) & 0xFFFFF000
                self.emit_u(inst_name, rd, imm)

        # Add some labels for any remaining pending branches
        for pc, target_label, _ in self.pending_branches:
            if target_label not in self.labels:
                self.set_label(target_label)

        self.resolve_branches()

        # Now add the signature store sequence
        # Store x1-x31 to signature region (0x1000-0x107C)
        for reg in range(1, 32):
            # Use LUI + ADDI to form address, then SW
            # Address = 0x1000 + (reg-1)*4
            addr = SIG_START + (reg - 1) * 4
            upper = (addr + 0x800) & 0xFFFFF000
            lower = addr - upper
            if lower > 2047:
                lower -= 4096

            tmp_reg = self.random_reg(exclude=[reg])
            self.emit_u('LUI', tmp_reg, upper)
            self.emit_i_alu('ADDI', tmp_reg, tmp_reg, lower)
            self.emit_s('SW', tmp_reg, reg, 0)

        # Write 1 to tohost (0x10000000) to end test
        tmp_reg = self.random_reg()
        self.emit_u('LUI', tmp_reg, 0x10000000)
        self.emit_i_alu('ADDI', tmp_reg, tmp_reg, 0)
        self.emit_i_alu('ADDI', tmp_reg, 0, 1)  # x1 = 1 (use a known reg)
        # Actually let's use x1 for the value 1
        self.emit_i_alu('ADDI', 1, 0, 1)
        self.emit_s('SW', tmp_reg, 1, 0)

        # Add an infinite loop at the end (in case tohost doesn't stop simulation)
        loop_label = self.new_label()
        self.set_label(loop_label)
        self.emit_b('BEQ', 0, 0, loop_label)  # beq x0, x0, loop

        self.resolve_branches()

        # Convert to bytes
        return struct.pack('<' + 'I' * len(self.program), *self.program)


def generate_hex(seed: int, num_instructions: int, output_file: str):
    """Generate a hex file from a random program."""
    gen = ProgramGenerator(seed)
    program_bytes = gen.generate_program(num_instructions)

    # Write as Verilog hex format
    with open(output_file, 'w') as f:
        f.write(f"@{TEXT_START:08x}\n")
        for i in range(0, len(program_bytes), 4):
            word = struct.unpack('<I', program_bytes[i:i+4])[0]
            f.write(f"{word:08x}\n")

    return program_bytes


def main():
    if len(sys.argv) < 4:
        print("Usage: gen.py <seed> <num_instructions> <output_hex>")
        sys.exit(1)

    seed = int(sys.argv[1])
    num_instructions = int(sys.argv[2])
    output_file = sys.argv[3]

    generate_hex(seed, num_instructions, output_file)
    print(f"Generated {output_file} with seed {seed}, {num_instructions} instructions")


if __name__ == '__main__':
    main()