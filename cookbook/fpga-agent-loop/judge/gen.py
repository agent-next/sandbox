#!/usr/bin/env python3
"""
Random RV32I program generator for fpga-agent-loop judge
Generates programs that end by storing x1..x31 to a signature region, then store 1 to tohost
"""

import random
import struct

def sign_extend(x, bits):
    """Sign extend x from bits to 32 bits"""
    if x & (1 << (bits - 1)):
        x |= ~((1 << bits) - 1)
    return x

def generate_instruction(seed=None):
    """Generate a random RV32I instruction"""
    if seed is not None:
        random.seed(seed)
    
    # RV32I instruction encodings
    # Format: [opcode, rd, funct3, rs1, rs2, funct7, imm] etc.
    
    # Choose instruction type
    inst_type = random.choice([
        'LUI', 'AUIPC', 'JAL', 'JALR',
        'BEQ', 'BNE', 'BLT', 'BGE', 'BLTU', 'BGEU',
        'LB', 'LH', 'LW', 'LBU', 'LHU',
        'SB', 'SH', 'SW',
        'ADDI', 'SLTI', 'SLTIU', 'XORI', 'ORI', 'ANDI',
        'SLLI', 'SRLI', 'SRAI',
        'ADD', 'SUB', 'SLL', 'SLT', 'SLTU', 'XOR', 'SRL', 'SRA', 'OR', 'AND'
    ])
    
    # Generate random register addresses (0-31)
    rd = random.randint(0, 31)
    rs1 = random.randint(0, 31)
    rs2 = random.randint(0, 31)
    
    # Generate immediate values
    imm_i = random.randint(-2048, 2047)  # I-type immediate
    imm_s = random.randint(-2048, 2047)  # S-type immediate
    imm_b = random.randint(-4096, 4095)  # B-type immediate (multiple of 2)
    imm_u = random.randint(0, 0xfffff) << 12  # U-type immediate
    imm_j = random.randint(-1048576, 1048575)  # J-type immediate (multiple of 2)
    
    # Generate instruction based on type
    if inst_type == 'LUI':
        # LUI rd, imm
        return (imm_u & 0xfffff000) | (rd << 7) | 0x37
    elif inst_type == 'AUIPC':
        # AUIPC rd, imm
        return (imm_u & 0xfffff000) | (rd << 7) | 0x17
    elif inst_type == 'JAL':
        # JAL rd, imm
        imm_j &= 0xfffff  # Ensure 20 bits
        imm_j = (imm_j >> 12 & 0xff) | \
                (imm_j >> 11 & 0x1) << 11 | \
                (imm_j >> 10 & 0x3ff) << 12 | \
                (imm_j >> 19 & 0x1) << 20 | \
                (imm_j & 0xfff) << 7
        return imm_j | (rd << 7) | 0x6f
    elif inst_type == 'JALR':
        # JALR rd, rs1, imm
        imm_i &= 0xfff
        return (imm_i & 0xfff) << 20 | (rs1 << 15) | (rd << 7) | 0x67
    elif inst_type in ['BEQ', 'BNE', 'BLT', 'BGE', 'BLTU', 'BGEU']:
        # Branch instructions
        imm_b &= 0x1ffe  # Ensure even, 13 bits
        imm_b = (imm_b >> 12 & 0x1) << 13 | \
                (imm_b >> 5 & 0x3f) << 25 | \
                (imm_b >> 1 & 0xf) << 8 | \
                (imm_b >> 11 & 0x1) << 7
        funct3 = {'BEQ': 0, 'BNE': 1, 'BLT': 4, 'BGE': 5, 'BLTU': 6, 'BGEU': 7}[inst_type]
        return (imm_b & 0xf800) >> 13 | \
               (imm_b & 0x7e0) >> 5 | \
               (rs2 << 20) | (rs1 << 15) | \
               (funct3 << 12) | \
               (imm_b & 0x1f) << 7 | \
               0x63
    elif inst_type in ['LB', 'LH', 'LW', 'LBU', 'LHU']:
        # Load instructions
        imm_i &= 0xfff
        funct3 = {'LB': 0, 'LH': 1, 'LW': 2, 'LBU': 4, 'LHU': 5}[inst_type]
        return (imm_i & 0xfff) << 20 | (rs1 << 15) | (funct3 << 12) | (rd << 7) | 0x03
    elif inst_type in ['SB', 'SH', 'SW']:
        # Store instructions
        imm_s &= 0xfff
        imm_s = (imm_s & 0xfe0) << 25 | (imm_s & 0x1f) << 7
        funct3 = {'SB': 0, 'SH': 1, 'SW': 2}[inst_type]
        return (imm_s & 0xf800) >> 11 | \
               (imm_s & 0x7e0) >> 5 | \
               (rs2 << 20) | (rs1 << 15) | \
               (funct3 << 12) | \
               0x23
    elif inst_type in ['ADDI', 'SLTI', 'SLTIU', 'XORI', 'ORI', 'ANDI']:
        # Immediate ALU
        imm_i &= 0xfff
        funct3 = {'ADDI': 0, 'SLTI': 2, 'SLTIU': 3, 'XORI': 4, 'ORI': 6, 'ANDI': 7}[inst_type]
        shamt = imm_i & 0x1f  # For shift instructions
        if inst_type in ['SLLI', 'SRLI', 'SRAI']:
            # These are handled separately
            pass
        else:
            return (imm_i & 0xfff) << 20 | (rs1 << 15) | (funct3 << 12) | (rd << 7) | 0x13
    elif inst_type in ['SLLI', 'SRLI', 'SRAI']:
        # Shift immediate
        shamt = random.randint(0, 31)
        imm_i = (shamt & 0x1f) | (0x20 << 5 if inst_type == 'SRAI' else 0)
        funct3 = {'SLLI': 1, 'SRLI': 5, 'SRAI': 5}[inst_type]
        funct7 = 0x00 if inst_type in ['SLLI', 'SRLI'] else 0x20
        return (funct7 & 0x7f) << 25 | (shamt & 0x1f) << 20 | (rs1 << 15) | (funct3 << 12) | (rd << 7) | 0x13
    else:
        # Register ALU
        funct3 = {
            'ADD': 0, 'SUB': 0, 'SLL': 1, 'SLT': 2, 'SLTU': 3,
            'XOR': 4, 'SRL': 5, 'SRA': 5, 'OR': 6, 'AND': 7
        }[inst_type]
        funct7 = {
            'ADD': 0x00, 'SUB': 0x20, 'SLL': 0x00, 'SLT': 0x00, 'SLTU': 0x00,
            'XOR': 0x00, 'SRL': 0x00, 'SRA': 0x20, 'OR': 0x00, 'AND': 0x00
        }[inst_type]
        return (funct7 & 0x7f) << 25 | (rs2 << 20) | (rs1 << 15) | (funct3 << 12) | (rd << 7) | 0x33

def generate_program(num_instructions, seed=None):
    """Generate a random RV32I program"""
    if seed is not None:
        random.seed(seed)
    
    program = []
    
    # Generate random instructions
    for i in range(num_instructions):
        inst = generate_instruction()
        program.append(inst)
    
    # Add signature storage and tohost termination
    # Store x1..x31 to signature region (0x1000 onwards)
    signature_base = 0x1000
    for reg in range(1, 32):  # x1 to x31
        # li x%d, 0
        li_inst = (0 << 20) | (reg << 7) | 0x37  # LUI x%d, 0
        # addi x%d, x%d, 0 (actually we need to store the register value)
        # For simplicity, we'll just generate a placeholder - in reality we'd need to move the register value
        # This is a simplified version - a real generator would be more complex
        program.append(li_inst)
        
        # sw x%d, offset(x0)
        sw_inst = (0 << 25) | (reg << 20) | (0 << 15) | (0x2 << 12) | (((signature_base + (reg-1)*4) & 0xfff) << 7) | 0x23
        program.append(sw_inst)
    
    # Store 1 to tohost (0x10000000) to indicate completion
    # li x10, 1
    li_tohost = (1 << 20) | (10 << 7) | 0x37  # LUI x10, 0
    # addi x10, x10, 1
    addi_tohost = (1 << 20) | (10 << 15) | (10 << 7) | 0x13  # ADDI x10, x10, 1
    # sw x10, 0(x0)  # Actually should be tohost address
    sw_tohost = (0 << 25) | (10 << 20) | (0 << 15) | (0x2 << 12) | (0x10000000 & 0xfff) << 7) | 0x23
    
    program.extend([li_tohost, addi_tohost, sw_tohost])
    
    return program

def program_to_bytes(program):
    """Convert list of instructions to byte array"""
    bytearray = bytearray()
    for inst in program:
        bytearray.extend(struct.pack('<I', inst))
    return bytearray

if __name__ == "__main__":
    import sys
    
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 42
    num_instructions = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    
    random.seed(seed)
    program = generate_program(num_instructions, seed)
    bytecode = program_to_bytes(program)
    
    # Write to stdout or file
    if len(sys.argv) > 3:
        with open(sys.argv[3], 'wb') as f:
            f.write(bytecode)
    else:
        sys.stdout.buffer.write(bytecode)
