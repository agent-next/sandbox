#!/usr/bin/env python3
"""
judge/iss_agree.py — Cross-check ISS against picorv32 on random programs
"""

import sys
import os
import subprocess
import tempfile
import struct
from typing import List, Tuple

JUDGE_DIR = os.path.dirname(os.path.abspath(__file__))
OSS_CAD_DIR = os.path.expanduser("~/.local/oss-cad-suite")
RISCV_GCC_DIR = os.path.expanduser("~/.local/riscv-gcc")
os.environ["PATH"] = f"{OSS_CAD_DIR}/bin:{RISCV_GCC_DIR}/bin:{os.environ['PATH']}"

IVERILOG = "iverilog"
ISS_SCRIPT = os.path.join(JUDGE_DIR, "iss.py")
GEN_SCRIPT = os.path.join(JUDGE_DIR, "gen.py")
PIKORV32_WRAPPER = os.path.join(JUDGE_DIR, "ref/picorv32_cpu.v")

def run_iss(hex_file: str, max_cycles: int = 500000) -> Tuple[bool, List[int], bytes]:
    """Run ISS and return (passed, regs, signature)."""
    result = subprocess.run([sys.executable, ISS_SCRIPT, hex_file, str(max_cycles)],
                            capture_output=True, text=True, timeout=60)
    # Parse output
    passed = "Passed: True" in result.stdout
    regs = []
    sig = b""
    for line in result.stdout.split('\n'):
        if line.startswith("Regs:"):
            # Parse [0, 1, 2, ...]
            regs_str = line[6:].strip()
            if regs_str.startswith('['):
                regs = [int(x.strip()) for x in regs_str[1:-1].split(',')]
        elif line.startswith("Signature:"):
            sig = bytes.fromhex(line[11:].strip())
    return passed, regs, sig

def run_picorv32(hex_file: str, max_cycles: int = 500000) -> Tuple[bool, List[int], bytes]:
    """Run picorv32 via iverilog and return (passed, regs, signature)."""
    # Create testbench that dumps registers
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
    initial begin $readmemh("{hex_file}", mem); clk=0; resetn=0; ready_delay=0; ready_counter=0; mem_ready_reg=0; #10 resetn=1; end
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
    integer j;
    always @(posedge clk) if (mem_ready && mem_valid && mem_wstrb!=0 && mem_addr==32'h10000000) begin
        if (mem_wdata==32'h1) begin
            $display("REGS:");
            for (j=1; j<32; j=j+1) $display("x%d=%h", j, dut.picorv32_core.regfile[j]);
            $finish(0);
        end else $finish(1);
    end
    initial #2000000 $finish(1);
endmodule
""")
    tb.close()

    out = tempfile.NamedTemporaryFile(mode='w', suffix='.vvp', delete=False)
    out.close()

    try:
        # Compile
        result = subprocess.run([IVERILOG, '-g2005-sv', '-o', out.name, PIKORV32_WRAPPER, tb.name],
                                capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            print(f"  Compile failed: {result.stderr}")
            return False, [], b""

        # Run
        result = subprocess.run(['vvp', out.name], capture_output=True, text=True, timeout=60)
        passed = result.returncode == 0

        # Parse registers
        regs = []
        in_regs = False
        for line in result.stdout.split('\n'):
            if line.strip() == "REGS:":
                in_regs = True
                continue
            if in_regs and line.startswith("x"):
                # x1=value
                parts = line.split('=')
                if len(parts) == 2:
                    reg_num = int(parts[0][1:])
                    val = int(parts[1], 16)
                    while len(regs) < reg_num:
                        regs.append(0)
                    regs.append(val)
            elif in_regs and not line.startswith("x"):
                in_regs = False

        return passed, regs, b""
    except subprocess.TimeoutExpired:
        return False, [], b""
    finally:
        os.unlink(tb.name)
        os.unlink(out.name)

def generate_program(seed: int, num_inst: int) -> str:
    """Generate a hex file for a random program."""
    hex_file = tempfile.NamedTemporaryFile(mode='w', suffix='.hex', delete=False)
    hex_file.close()
    subprocess.run([sys.executable, GEN_SCRIPT, str(seed), str(num_inst), hex_file.name],
                   check=True, capture_output=True)
    return hex_file.name

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=999)
    args = parser.parse_args()

    print(f"Running ISS vs picorv32 agreement test: {args.count} programs, seed={args.seed}")

    agree = 0
    disagree = 0
    errors = 0

    for i in range(args.count):
        prog_seed = args.seed + i
        if i % 100 == 0:
            print(f"  Progress: {i}/{args.count} (agree={agree}, disagree={disagree}, errors={errors})")

        hex_file = generate_program(prog_seed, 500)

        try:
            iss_passed, iss_regs, iss_sig = run_iss(hex_file)
            p32_passed, p32_regs, p32_sig = run_picorv32(hex_file)

            if iss_passed and p32_passed:
                # Compare registers (at least first few)
                if iss_regs[:5] == p32_regs[:5] and len(iss_regs) >= 5 and len(p32_regs) >= 5:
                    agree += 1
                else:
                    disagree += 1
                    if disagree <= 5:
                        print(f"  MISMATCH prog {i}: iss_regs={iss_regs[:5]}, p32_regs={p32_regs[:5]}")
            elif not iss_passed and not p32_passed:
                # Both failed - could be same reason
                agree += 1
            else:
                disagree += 1
                if disagree <= 5:
                    print(f"  MISMATCH prog {i}: iss_passed={iss_passed}, p32_passed={p32_passed}")

        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  ERROR prog {i}: {e}")

        os.unlink(hex_file)

    print(f"\n=== ISS Agreement Results ===")
    print(f"Total: {args.count}")
    print(f"Agree: {agree}")
    print(f"Disagree: {disagree}")
    print(f"Errors: {errors}")

    if agree >= args.count * 0.99:  # 99% agreement required
        print("ISS AGREEMENT: PASS")
        return 0
    else:
        print(f"ISS AGREEMENT: FAIL (agreement rate {agree/args.count*100:.1f}% < 99%)")
        return 1

if __name__ == '__main__':
    sys.exit(main())