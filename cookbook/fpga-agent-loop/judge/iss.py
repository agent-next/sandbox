#!/usr/bin/env python3
"""
Simple RISC-V RV32I Instruction Set Simulator (ISS)
For use as oracle in G2 differential testing
"""

import sys
import struct

class RV32ISS:
    def __init__(self):
        # 32 integer registers (x0-x31)
        self.regs = [0] * 32
        # Program counter
        self.pc = 0
        # 64 KiB memory (0x0000_0000 to 0x0000_FFFF)
        self.mem = [0] * (64 * 1024)
        # To-host address for test termination
        self.tohost_addr = 0x10000000
        # Test signature start address (where CPU will write signature)
        self.signature_addr = 0x1000  # Start of signature region
        self.signature_len = 32 * 4   # 32 registers * 4 bytes
        
    def load_program(self, program_bytes):
        """Load program into memory at address 0"""
        if len(program_bytes) > len(self.mem) * 4:
            raise ValueError("Program too large for memory")
        
        # Convert bytes to 32-bit words (little-endian)
        for i in range(0, len(program_bytes), 4):
            if i + 4 <= len(program_bytes):
                word = struct.unpack('<I', program_bytes[i:i+4])[0]
                addr = i // 4
                if addr < len(self.mem):
                    self.mem[addr] = word
    
    def sign_extend(self, x, bits):
        """Sign extend x from bits to 32 bits"""
        if x & (1 << (bits - 1)):
            x |= ~((1 << bits) - 1)
        return x
    
    def step(self):
        """Execute one instruction"""
        if self.pc < 0 or self.pc >= len(self.mem):
            raise Exception(f"PC out of range: 0x{self.pc:08x}")
        
        # Fetch instruction
        insn = self.mem[self.pc]
        self.pc += 4  # Normal PC increment
        
        # Decode and execute
        opcode = insn & 0x7f
        
        if opcode == 0x37:  # LUI
            rd = (insn >> 7) & 0x1f
            imm = insn & 0xfffff000
            self.regs[rd] = self.sign_extend(imm, 32)
            
        elif opcode == 0x17:  # AUIPC
            rd = (insn >> 7) & 0x1f
            imm = insn & 0xfffff000
            self.regs[rd] = self.sign_extend(self.pc - 4 + imm, 32)
            
        elif opcode == 0x6f:  # JAL
            rd = (insn >> 7) & 0x1f
            imm = ((insn >> 12) & 0xff) | \
                  ((insn >> 20) & 0x7fe0) | \
                  ((insn >> 19) & 0x800) | \
                  ((insn >> 31) & 0x7ffff000)
            imm = self.sign_extend(imm, 21)
            self.regs[rd] = self.pc
            self.pc += imm
            
        elif opcode == 0x67:  # JALR
            rd = (insn >> 7) & 0x1f
            rs1 = (insn >> 15) & 0x1f
            imm = (insn >> 20) & 0xfff
            imm = self.sign_extend(imm, 12)
            addr = self.regs[rs1] + imm
            self.regs[rd] = self.pc
            self.pc = addr & ~1  # Ensure aligned
            
        elif opcode == 0x63:  # Branch
            rs1 = (insn >> 15) & 0x1f
            rs2 = (insn >> 20) & 0x1f
            imm = ((insn >> 8) & 0xf) | \
                  ((insn >> 25) & 0x3f0) | \
                  ((insn >> 7) & 0x40) | \
                  ((insn >> 31) & 0x800)
            imm = self.sign_extend(imm, 13)
            
            rs1_val = self.regs[rs1]
            rs2_val = self.regs[rs2]
            
            funct3 = (insn >> 12) & 0x7
            taken = False
            if funct3 == 0x0:  # BEQ
                taken = (rs1_val == rs2_val)
            elif funct3 == 0x1:  # BNE
                taken = (rs1_val != rs2_val)
            elif funct3 == 0x4:  # BLT
                taken = self.sign_extend(rs1_val, 32) < self.sign_extend(rs2_val, 32)
            elif funct3 == 0x5:  # BGE
                taken = self.sign_extend(rs1_val, 32) >= self.sign_extend(rs2_val, 32)
            elif funct3 == 0x6:  # BLTU
                taken = rs1_val < rs2_val
            elif funct3 == 0x7:  # BGEU
                taken = rs1_val >= rs2_val
                
            if taken:
                self.pc += imm
                
        elif opcode == 0x03:  # Load
            rd = (insn >> 7) & 0x1f
            rs1 = (insn >> 15) & 0x1f
            imm = (insn >> 20) & 0xfff
            imm = self.sign_extend(imm, 12)
            addr = self.regs[rs1] + imm
            
            funct3 = (insn >> 12) & 0x7
            if funct3 == 0x0:  # LB
                self.regs[rd] = self.sign_extend(self.mem[addr // 4] & 0xff, 8)
            elif funct3 == 0x1:  # LH
                self.regs[rd] = self.sign_extend((self.mem[addr // 4] >> 8) & 0xffff, 16)
            elif funct3 == 0x2:  # LW
                self.regs[rd] = self.mem[addr // 4]
            elif funct3 == 0x4:  # LBU
                self.regs[rd] = self.mem[addr // 4] & 0xff
            elif funct3 == 0x5:  # LHU
                self.regs[rd] = (self.mem[addr // 4] >> 8) & 0xffff
                
        elif opcode == 0x23:  # Store
            rs1 = (insn >> 15) & 0x1f
            rs2 = (insn >> 20) & 0x1f
            imm = (insn >> 25) & 0xfe0
            imm |= (insn >> 7) & 0x1f
            imm = self.sign_extend(imm, 13)
            addr = self.regs[rs1] + imm
            
            funct3 = (insn >> 12) & 0x7
            if funct3 == 0x0:  # SB
                self.mem[addr // 4] = (self.mem[addr // 4] & ~(0xff << ((addr % 4) * 8))) | \
                                       ((self.regs[rs2] & 0xff) << ((addr % 4) * 8))
            elif funct3 == 0x1:  # SH
                self.mem[addr // 4] = (self.mem[addr // 4] & ~(0xffff << ((addr % 4) * 8))) | \
                                       ((self.regs[rs2] & 0xffff) << ((addr % 4) * 8))
            elif funct3 == 0x2:  # SW
                self.mem[addr // 4] = self.regs[rs2]
                
        elif opcode == 0x13:  # Immediate ALU
            rd = (insn >> 7) & 0x1f
            rs1 = (insn >> 15) & 0x1f
            imm = (insn >> 20) & 0xfff
            imm = self.sign_extend(imm, 12)
            
            funct3 = (insn >> 12) & 0x7
            rs1_val = self.regs[rs1]
            if funct3 == 0x0:  # ADDI
                self.regs[rd] = rs1_val + imm
            elif funct3 == 0x2:  # SLTI
                self.regs[rd] = 1 if self.sign_extend(rs1_val, 32) < self.sign_extend(imm, 32) else 0
            elif funct3 == 0x3:  # SLTIU
                self.regs[rd] = 1 if rs1_val < (imm & 0xffffffff) else 0
            elif funct3 == 0x4:  # XORI
                self.regs[rd] = rs1_val ^ imm
            elif funct3 == 0x6:  # ORI
                self.regs[rd] = rs1_val | imm
            elif funct3 == 0x7:  # ANDI
                self.regs[rd] = rs1_val & imm
            elif funct3 == 0x1:  # SLLI
                shamt = imm & 0x1f
                self.regs[rd] = rs1_val << shamt
            elif funct3 == 0x5:  # SRLI/SRAI
                shamt = imm & 0x1f
                if (imm >> 10) & 0x1:  # SRAI
                    self.regs[rd] = self.sign_extend(rs1_val, 32) >> shamt
                else:  # SRLI
                    self.regs[rd] = rs1_val >> shamt
                    
        elif opcode == 0x33:  # Register ALU
            rd = (insn >> 7) & 0x1f
            rs1 = (insn >> 15) & 0x1f
            rs2 = (insn >> 20) & 0x1f
            
            funct3 = (insn >> 12) & 0x7
            funct7 = (insn >> 25) & 0x7f
            rs1_val = self.regs[rs1]
            rs2_val = self.regs[rs2]
            
            if funct3 == 0x0:  # ADD/SUB
                if funct7 == 0x00:  # ADD
                    self.regs[rd] = rs1_val + rs2_val
                elif funct7 == 0x20:  # SUB
                    self.regs[rd] = rs1_val - rs2_val
            elif funct3 == 0x1:  # SLL
                shamt = rs2_val & 0x1f
                self.regs[rd] = rs1_val << shamt
            elif funct3 == 0x2:  # SLT
                self.regs[rd] = 1 if self.sign_extend(rs1_val, 32) < self.sign_extend(rs2_val, 32) else 0
            elif funct3 == 0x3:  # SLTU
                self.regs[rd] = 1 if rs1_val < rs2_val else 0
            elif funct3 == 0x4:  # XOR
                self.regs[rd] = rs1_val ^ rs2_val
            elif funct3 == 0x5:  # SRL/SRA
                shamt = rs2_val & 0x1f
                if funct7 == 0x00:  # SRL
                    self.regs[rd] = rs1_val >> shamt
                elif funct7 == 0x20:  # SRA
                    self.regs[rd] = self.sign_extend(rs1_val, 32) >> shamt
            elif funct3 == 0x6:  # OR
                self.regs[rd] = rs1_val | rs2_val
            elif funct3 == 0x7:  # AND
                self.regs[rd] = rs1_val & rs2_val
                
        elif opcode == 0x73:  # ECALL/EBREAK
            # For simplicity, treat as trap (would normally check CSRs)
            if (insn >> 20) & 0xfff == 0x000:  # ECALL
                # In a real system, this would change mode - for now just continue
                pass
            elif (insn >> 20) & 0xfff == 0x001:  # EBREAK
                # Breakpoint - stop execution
                return False
                
        # Check for tohost write (test completion)
        if self.pc >= self.tohost_addr // 4:
            # Check if we wrote to tohost
            tohost_word = self.mem[self.tohost_addr // 4]
            tohost_byte = (tohost_word >> ((self.tohost_addr % 4) * 8)) & 0xff
            if tohost_byte == 1:
                # Test passed
                return None  # Special value indicating test completion
            elif tohost_byte != 0:
                # Test failed (encoded in lower bits)
                return False
                
        return True  # Continue execution
    
    def run(self, max_instructions=100000):
        """Run program until completion or max instructions"""
        for _ in range(max_instructions):
            result = self.step()
            if result is False:
                return False  # Test failed
            elif result is None:
                return True   # Test passed
            elif not result:
                break         # Exception occurred
        return False  # Timeout
    
    def get_signature(self):
        """Get the register signature from memory"""
        signature = []
        for i in range(self.signature_len // 4):
            addr = (self.signature_addr // 4) + i
            if addr < len(self.mem):
                signature.append(self.mem[addr])
        return signature

def simulate_program(program_bytes):
    """Simulate a program and return (success, signature)"""
    iss = RV32ISS()
    iss.load_program(program_bytes)
    success = iss.run()
    if success is not False:  # Success or timeout (we'll treat timeout as failure for now)
        signature = iss.get_signature()
        return True, signature
    else:
        return False, None

if __name__ == "__main__":
    # Simple test - add two numbers
    # li x5, 5
    # li x6, 7
    # add x7, x5, x6
    # sw x7, 0(x0)
    # li x10, 1
    # sw x10, 0(x10000000)  # tohost = 1
    program = bytearray([
        0x05, 0x05, 0x02, 0x03,  # li x5, 5
        0x07, 0x06, 0x02, 0x03,  # li x6, 7
        0x05, 0x06, 0x07, 0x03,  # add x7, x5, x6
        0x07, 0x00, 0x02, 0x23,  # sw x7, 0(x0)
        0x01, 0x0a, 0x02, 0x03,  # li x10, 1
        0x00, 0x00, 0x00, 0x23,  # sw x10, 0(x0) - wrong addr, should be tohost
        0x00, 0x00, 0x00, 0x23,  # sw x10, 0(x0) - placeholder
        0x00, 0x00, 0x00, 0x23,  # sw x10, 0(x0) - placeholder
        0x00, 0x00, 0x00, 0x23,  # sw x10, 0(x0) - placeholder
        0x01, 0x00, 0x00, 0x23,  # sw x10, 0(x0) - tohost write
    ])
    
    # Fix the tohost address
    program[36] = 0x00  # addr low byte
    program[37] = 0x00  # addr byte 2
    program[38] = 0x00  # addr byte 3
    program[39] = 0x10  # addr high byte (0x10000000)
    
    success, signature = simulate_program(program)
    print(f"Success: {success}")
    if signature:
        print(f"Signature: {[hex(x) for x in signature]}")
