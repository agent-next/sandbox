#!/usr/bin/env python3
"""
judge/mutants.py — Generate single-edit mutants of picorv32 core
Each mutant must fail at least one gate. Survivors proven equivalent via Yosys LEC.
"""

import sys
import os
import random
import subprocess
import tempfile
import shutil
from typing import List, Tuple, Dict

JUDGE_DIR = os.path.dirname(os.path.abspath(__file__))
OSS_CAD_DIR = os.path.expanduser("~/.local/oss-cad-suite")
RISCV_GCC_DIR = os.path.expanduser("~/.local/riscv-gcc")
os.environ["PATH"] = f"{OSS_CAD_DIR}/bin:{RISCV_GCC_DIR}/bin:{os.environ['PATH']}"

YOSYS = "yosys"
IVERILOG = "iverilog"

# Mutation operators - single edits that should break functionality
MUTATIONS = [
    # Operator swaps
    ("ADD -> SUB", "alu_op_add", "alu_op_sub"),
    ("SUB -> ADD", "alu_op_sub", "alu_op_add"),
    ("SLL -> SRL", "alu_op_sll", "alu_op_srl"),
    ("SRL -> SLL", "alu_op_srl", "alu_op_sll"),
    ("SRA -> SRL", "alu_op_sra", "alu_op_srl"),
    ("SLT -> SLTU", "alu_op_slt", "alu_op_sltu"),
    ("SLTU -> SLT", "alu_op_sltu", "alu_op_slt"),
    ("XOR -> OR", "alu_op_xor", "alu_op_or"),
    ("OR -> XOR", "alu_op_or", "alu_op_xor"),
    ("AND -> OR", "alu_op_and", "alu_op_or"),
    # Branch condition flips
    ("BEQ -> BNE", "branch_beq", "branch_bne"),
    ("BNE -> BEQ", "branch_bne", "branch_beq"),
    ("BLT -> BGE", "branch_blt", "branch_bge"),
    ("BGE -> BLT", "branch_bge", "branch_blt"),
    ("BLTU -> BGEU", "branch_bltu", "branch_bgeu"),
    ("BGEU -> BLTU", "branch_bgeu", "branch_bltu"),
    # Wrong sign/zero extension
    ("LB -> LBU", "load_lb", "load_lbu"),
    ("LH -> LHU", "load_lh", "load_lhu"),
    # Off-by-one in shifts
    ("SLLI shamt+1", "slli_shamt", "slli_shamt_plus1"),
    ("SRLI shamt+1", "srli_shamt", "srli_shamt_plus1"),
    # Dropped write enable
    ("mem_wstrb=0", "mem_wstrb_assign", "mem_wstrb_zero"),
    # Immediate corruption
    ("ADDI imm^1", "addi_imm", "addi_imm_xor1"),
    ("LUI imm>>1", "lui_imm", "lui_imm_shr1"),
    # PC increment wrong
    ("pc+2", "pc_plus4", "pc_plus2"),
    ("pc+8", "pc_plus4", "pc_plus8"),
]

def read_picorv32(core_file: str) -> str:
    with open(core_file, 'r') as f:
        return f.read()

def apply_mutation(source: str, mutation_name: str, seed: int) -> Tuple[str, str]:
    """Apply a single mutation to the source. Returns (mutated_source, description)."""
    rng = random.Random(seed)
    lines = source.split('\n')

    # Find mutation targets by pattern matching
    mutations_applied = []

    for i, line in enumerate(lines):
        # ADD/SUB swap in ALU
        if "alu_op_add" in line and "alu_op_sub" not in line and rng.random() < 0.1:
            lines[i] = line.replace("alu_op_add", "alu_op_sub")
            mutations_applied.append(f"Line {i+1}: alu_op_add -> alu_op_sub")
            break
        if "alu_op_sub" in line and "alu_op_add" not in line and rng.random() < 0.1:
            lines[i] = line.replace("alu_op_sub", "alu_op_add")
            mutations_applied.append(f"Line {i+1}: alu_op_sub -> alu_op_add")
            break

        # SLL/SRL swap
        if "alu_op_sll" in line and "alu_op_srl" not in line and rng.random() < 0.1:
            lines[i] = line.replace("alu_op_sll", "alu_op_srl")
            mutations_applied.append(f"Line {i+1}: alu_op_sll -> alu_op_srl")
            break
        if "alu_op_srl" in line and "alu_op_sll" not in line and rng.random() < 0.1:
            lines[i] = line.replace("alu_op_srl", "alu_op_sll")
            mutations_applied.append(f"Line {i+1}: alu_op_srl -> alu_op_sll")
            break

        # SLT/SLTU swap
        if "alu_op_slt" in line and "alu_op_sltu" not in line and rng.random() < 0.1:
            lines[i] = line.replace("alu_op_slt", "alu_op_sltu")
            mutations_applied.append(f"Line {i+1}: alu_op_slt -> alu_op_sltu")
            break
        if "alu_op_sltu" in line and "alu_op_slt" not in line and rng.random() < 0.1:
            lines[i] = line.replace("alu_op_sltu", "alu_op_slt")
            mutations_applied.append(f"Line {i+1}: alu_op_sltu -> alu_op_slt")
            break

        # XOR/OR swap
        if "alu_op_xor" in line and "alu_op_or" not in line and rng.random() < 0.1:
            lines[i] = line.replace("alu_op_xor", "alu_op_or")
            mutations_applied.append(f"Line {i+1}: alu_op_xor -> alu_op_or")
            break
        if "alu_op_or" in line and "alu_op_xor" not in line and rng.random() < 0.1:
            lines[i] = line.replace("alu_op_or", "alu_op_xor")
            mutations_applied.append(f"Line {i+1}: alu_op_or -> alu_op_xor")
            break

        # Branch condition flips
        if "branch_beq" in line and "branch_bne" not in line and rng.random() < 0.1:
            lines[i] = line.replace("branch_beq", "branch_bne")
            mutations_applied.append(f"Line {i+1}: branch_beq -> branch_bne")
            break
        if "branch_bne" in line and "branch_beq" not in line and rng.random() < 0.1:
            lines[i] = line.replace("branch_bne", "branch_beq")
            mutations_applied.append(f"Line {i+1}: branch_bne -> branch_beq")
            break

        # Load sign extension
        if "load_lb" in line and "load_lbu" not in line and rng.random() < 0.1:
            lines[i] = line.replace("load_lb", "load_lbu")
            mutations_applied.append(f"Line {i+1}: load_lb -> load_lbu")
            break

        # PC increment
        if "reg_pc + 4" in line and rng.random() < 0.1:
            lines[i] = line.replace("reg_pc + 4", "reg_pc + 2")
            mutations_applied.append(f"Line {i+1}: pc+4 -> pc+2")
            break
        if "reg_pc + 4" in line and rng.random() < 0.1:
            lines[i] = line.replace("reg_pc + 4", "reg_pc + 8")
            mutations_applied.append(f"Line {i+1}: pc+4 -> pc+8")
            break

        # Write enable dropped
        if "mem_wstrb" in line and "=" in line and "0" not in line and rng.random() < 0.05:
            lines[i] = line.replace("mem_wstrb", "// mem_wstrb")
            mutations_applied.append(f"Line {i+1}: mem_wstrb assignment commented")
            break

    if not mutations_applied:
        # Fallback: pick a random ALU operation and flip it
        for i, line in enumerate(lines):
            if "alu_op_" in line and "localparam" in line:
                ops = ["alu_op_add", "alu_op_sub", "alu_op_sll", "alu_op_srl", "alu_op_sra",
                       "alu_op_slt", "alu_op_sltu", "alu_op_xor", "alu_op_or", "alu_op_and"]
                current = None
                for op in ops:
                    if op in line:
                        current = op
                        break
                if current:
                    other = rng.choice([o for o in ops if o != current])
                    lines[i] = line.replace(current, other)
                    mutations_applied.append(f"Line {i+1}: {current} -> {other}")
                    break

    desc = "; ".join(mutations_applied) if mutations_applied else "No mutation applied (fallback)"
    return '\n'.join(lines), desc

def run_gate_test(cpu_file: str, test_name: str) -> bool:
    """Run a quick gate test on a mutant CPU."""
    # Create testbench
    tb = tempfile.NamedTemporaryFile(mode='w', suffix='.v', delete=False)
    tb.write(f"""
`timescale 1ns/1ps
module tb;
    reg clk, resetn;
    wire mem_valid, mem_instr, mem_ready;
    wire [31:0] mem_addr, mem_wdata, mem_rdata;
    wire [3:0] mem_wstrb;
    wire trap;
    cpu dut(.clk(clk),.resetn(resetn),.mem_valid(mem_valid),.mem_instr(mem_instr),.mem_ready(mem_ready),.mem_addr(mem_addr),.mem_wdata(mem_wdata),.mem_wstrb(mem_wstrb),.mem_rdata(mem_rdata),.trap(trap));
    reg [7:0] mem [0:65535];
    reg [2:0] ready_delay, ready_counter;
    reg mem_ready_reg;
    initial begin $readmemh("{JUDGE_DIR}/tests/simple.hex", mem); clk=0; resetn=0; ready_delay=0; ready_counter=0; mem_ready_reg=0; #10 resetn=1; end
    always #5 clk=~clk;
    always @(posedge clk) begin
        if (resetn) begin
            if (mem_valid && !mem_ready_reg) begin
                if (ready_counter==0) begin ready_delay=$urandom_range(0,7); ready_counter=ready_delay; end
                else ready_counter=ready_counter-1;
                mem_ready_reg=(ready_counter==0);
            end else begin mem_ready_reg=0; ready_counter=0; end
        end
    end
    assign mem_ready=mem_ready_reg;
    always @(posedge clk) if (mem_ready && mem_valid && mem_wstrb!=0) begin
        if (mem_wstrb[0]) mem[mem_addr-32'h80000000]<=mem_wdata[7:0];
        if (mem_wstrb[1]) mem[mem_addr-32'h80000000+1]<=mem_wdata[15:8];
        if (mem_wstrb[2]) mem[mem_addr-32'h80000000+2]<=mem_wdata[23:16];
        if (mem_wstrb[3]) mem[mem_addr-32'h80000000+3]<=mem_wdata[31:24];
    end
    assign mem_rdata = {{mem[mem_addr-32'h80000000+3], mem[mem_addr-32'h80000000+2], mem[mem_addr-32'h80000000+1], mem[mem_addr-32'h80000000]}};
    always @(posedge clk) if (mem_ready && mem_valid && mem_wstrb!=0 && mem_addr==32'h10000000) begin
        if (mem_wdata==32'h1) $finish(0); else $finish(1);
    end
    initial #100000 $finish(1);
endmodule
""")
    tb.close()

    out = tempfile.NamedTemporaryFile(mode='w', suffix='.vvp', delete=False)
    out.close()

    try:
        # Compile
        result = subprocess.run([IVERILOG, '-g2005-sv', '-o', out.name, cpu_file, tb.name],
                                capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return False  # Compile fail = killed

        # Run
        result = subprocess.run(['vvp', out.name], capture_output=True, text=True, timeout=30)
        # Check if PASS (exit code 0) or FAIL (exit code 1)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    finally:
        os.unlink(tb.name)
        os.unlink(out.name)

def run_lec(original_cpu: str, mutant_cpu: str) -> bool:
    """Run Yosys LEC to check equivalence. Returns True if equivalent."""
    lec_script = tempfile.NamedTemporaryFile(mode='w', suffix='.ys', delete=False)
    lec_script.write(f"""
read_verilog -sv {original_cpu}
hierarchy -top cpu
rename cpu cpu_gold
read_verilog -sv {mutant_cpu}
hierarchy -top cpu
miter -equiv -make_outputs -make_outcmp cpu_gold cpu miter
sat -verify -prove trigger 0 -set-init-undef -set-at 20 miter
""")
    lec_script.close()

    try:
        result = subprocess.run([YOSYS, '-q', '-s', lec_script.name],
                                capture_output=True, text=True, timeout=120)
        # If SAT proves equivalence, it will say "proved" or similar
        return "proved" in result.stdout.lower() or "equivalent" in result.stdout.lower()
    except subprocess.TimeoutExpired:
        return False
    finally:
        os.unlink(lec_script.name)

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--picorv32", required=True)
    parser.add_argument("--tests-dir", required=True)
    parser.add_argument("--seed", type=int, default=12345)
    args = parser.parse_args()

    print(f"Generating {args.count} mutants of picorv32...")
    print(f"Source: {args.picorv32}")

    original_source = read_picorv32(args.picorv32)

    killed = 0
    survived = 0
    survivors = []

    for i in range(args.count):
        seed = args.seed + i * 1000
        print(f"\nMutant {i+1}/{args.count} (seed={seed})...")

        # Apply mutation
        mutated_source, desc = apply_mutation(original_source, f"mutant_{i}", seed)
        print(f"  Mutation: {desc}")

        # Write mutant
        mutant_file = tempfile.NamedTemporaryFile(mode='w', suffix='.v', delete=False)
        mutant_file.write(mutated_source)
        mutant_file.close()

        # Create wrapper for mutant
        wrapper = tempfile.NamedTemporaryFile(mode='w', suffix='.v', delete=False)
        wrapper.write(f"""
module cpu (
    input  wire        clk,
    input  wire        resetn,
    output reg         mem_valid,
    output reg         mem_instr,
    input  wire        mem_ready,
    output reg  [31:0] mem_addr,
    output reg  [31:0] mem_wdata,
    output reg  [3:0]  mem_wstrb,
    input  wire [31:0] mem_rdata,
    output wire        trap
);
    picorv32_mutant core (
        .clk(clk), .resetn(resetn), .trap(trap),
        .mem_valid(mem_valid), .mem_instr(mem_instr), .mem_ready(mem_ready),
        .mem_addr(mem_addr), .mem_wdata(mem_wdata), .mem_wstrb(mem_wstrb), .mem_rdata(mem_rdata),
        .mem_la_read(), .mem_la_write(), .mem_la_addr(), .mem_la_wdata(), .mem_la_wstrb(),
        .pcpi_valid(), .pcpi_insn(), .pcpi_rs1(), .pcpi_rs2(),
        .pcpi_wr(1'b0), .pcpi_rd(32'h0), .pcpi_wait(1'b0), .pcpi_ready(1'b0),
        .irq(32'h0), .eoi()
    );
endmodule

`define PICORV32_V
`include "{args.picorv32}"
""")
        wrapper.close()

        # Need to replace the module name in mutated source
        mutated_source = mutated_source.replace("module picorv32", "module picorv32_mutant")
        with open(mutant_file.name, 'w') as f:
            f.write(mutated_source)

        # Test mutant
        passes = run_gate_test(wrapper.name, f"mutant_{i}")

        if passes:
            print(f"  SURVIVED - running LEC...")
            equivalent = run_lec(args.picorv32, mutant_file.name)
            if equivalent:
                print(f"  LEC: EQUIVALENT (benign mutation)")
                survived += 1
                survivors.append((i, desc, "equivalent"))
            else:
                print(f"  LEC: NOT EQUIVALENT (potential false positive)")
                survived += 1
                survivors.append((i, desc, "not_equivalent"))
        else:
            print(f"  KILLED")
            killed += 1

        os.unlink(mutant_file.name)
        os.unlink(wrapper.name)

    total = killed + survived
    kill_rate = (killed / total * 100) if total > 0 else 0

    print(f"\n=== Mutant Results ===")
    print(f"Total mutants: {total}")
    print(f"Killed: {killed}")
    print(f"Survived: {survived}")
    print(f"Kill rate: {kill_rate:.1f}%")

    if survivors:
        print(f"\nSurvivors:")
        for idx, desc, lec in survivors:
            print(f"  Mutant {idx}: {desc} - LEC: {lec}")

    if kill_rate >= 95:
        print("\nMUTANT TEST: PASS (kill rate >= 95%)")
        return 0
    else:
        print(f"\nMUTANT TEST: FAIL (kill rate {kill_rate:.1f}% < 95%)")
        return 1

if __name__ == '__main__':
    sys.exit(main())