#!/usr/bin/env python3
"""Generate single-edit mutants of the fetched picorv32.v (judge power test).

Each mutant is a (name, search, replace) edit applied to a fresh copy of
$HOME/riscv-toolchain/picorv32/picorv32.v; the SPEC-interface wrapper
judge/ref/picorv32_cpu.v then includes the mutated file via the
PICORV32_DIR_OVERRIDE include path. grade.sh must FAIL every mutant on at
least one gate - a surviving mutant means the judge is too weak (or the
edit is a semantic no-op, which must be shown equivalent).

T1 shipped the three mandatory mutants (branch flip, dropped wstrb lane,
ignored mem_ready); T2 added the two J-immediate mutants + bimm control.
T3 brings the total to 32: operator swaps, off-by-ones, sign/zero-extension
drops, dropped write enables, branch-condition flips, and targeted
G2/G3 hits. Every anchor is checked against the pinned picorv32.v and the
script fails loudly (exit != 0) if any anchor is missing or not unique.

Usage:
    mutants.py                      write mutants to mutants_out/<name>/picorv32.v
    mutants.py --outdir DIR         write mutants under DIR instead
    mutants.py --list               print one mutant name per line
    mutants.py --describe           print the mutant table with rationale

Grading a mutant (each dir shadows the include path so the SPEC wrapper
picks up the mutated core):
    PICORV32_DIR=$PWD/mutants_out/<name> ./grade.sh ref/picorv32_cpu.v
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "mutants_out")
PICO_V = os.path.join(os.path.expanduser("~"),
                      "riscv-toolchain", "picorv32", "picorv32.v")

# (name, search, replace, why it must be caught)
MUTANTS = [
    (
        "branch-flip",
        """		case (1'b1)
			instr_beq:
				alu_out_0 = alu_eq;
			instr_bne:
				alu_out_0 = !alu_eq;""",
        """		case (1'b1)
			instr_beq:
				alu_out_0 = !alu_eq;
			instr_bne:
				alu_out_0 = alu_eq;""",
        "BEQ/BNE conditions swapped: rv32ui branch tests must fail (G1)",
    ),
    (
        "wstrb-lane-drop",
        "mem_la_wstrb = 4'b1111;",
        "mem_la_wstrb = 4'b0111;",
        "SW drops byte lane 0: every full-word store corrupts memory (G1)",
    ),
    (
        "ignore-mem-ready",
        "assign mem_xfer = (mem_valid && mem_ready) || (mem_la_use_prefetched_high_word && mem_do_rinst);",
        "assign mem_xfer = (mem_valid) || (mem_la_use_prefetched_high_word && mem_do_rinst);",
        "mem_ready ignored: only survives if the tb never stretches a "
        "request - G4's random latency must break it",
    ),
    (
        "bimm-sign-drop",
        "					decoded_imm <= $signed({mem_rdata_q[31], mem_rdata_q[7], mem_rdata_q[30:25], mem_rdata_q[11:8], 1'b0});",
        "					decoded_imm <= {1'b0, mem_rdata_q[7], mem_rdata_q[30:25], mem_rdata_q[11:8], 1'b0};",
        "branch immediate sign bit dropped: backward branches decode as "
        "large forward jumps. CAUGHT BY G1 (6/40): this judge's no-CSR "
        "riscv_test.h FAIL macro and some test bodies do use backward "
        "branches - kept as a G1/G4-killer documenting that corner",
    ),
    (
        "jal-sign-drop",
        "			{ decoded_imm_j[31:20], decoded_imm_j[10:1], decoded_imm_j[11], decoded_imm_j[19:12], decoded_imm_j[0] } <= $signed({mem_rdata_latched[31:12], 1'b0});",
        "			{ decoded_imm_j[31:20], decoded_imm_j[10:1], decoded_imm_j[11], decoded_imm_j[19:12], decoded_imm_j[0] } <= {1'b0, mem_rdata_latched[30:12], 1'b0};",
        "JAL immediate sign bit (imm[20]) forced to 0: backward JALs "
        "decode as +1 MiB-ish forward jumps. Executed rv32ui JALs are all "
        "small forward jumps (imm bits >= 8 never set; the negative JALs "
        "in the images sit in data regions and never execute), so G1 "
        "passes and only G2's backward JAL catches it (T2 power test)",
    ),
    (
        "jal-imm-hi-zero",
        "			{ decoded_imm_j[31:20], decoded_imm_j[10:1], decoded_imm_j[11], decoded_imm_j[19:12], decoded_imm_j[0] } <= $signed({mem_rdata_latched[31:12], 1'b0});",
        "			{ decoded_imm_j[31:20], decoded_imm_j[10:1], decoded_imm_j[11], decoded_imm_j[19:12], decoded_imm_j[0] } <= $signed({mem_rdata_latched[31:20], 8'b0, 1'b0});",
        "JAL immediate bits imm[19:12] forced to 0 (by zeroing their "
        "source, insn[19:12], on the RHS - the LHS must stay a plain "
        "lvalue or Verilator rejects the build): any JAL with an offset "
        "offset >= 4 KiB (or a backward JAL, whose 21-bit two's-complement "
        "encoding has imm[19:12] all ones) jumps to the wrong address. "
        "rv32ui's executed JALs are all < 256 B forward, so G1 passes; "
        "G2's coverage block contains a backward JAL and the filler "
        "mixes JALs into long programs (T2 power test)",
    ),
    # ---- T3: operator swaps ---------------------------------------------
    (
        "add-sub-swap",
        "		alu_add_sub = instr_sub ? reg_op1 - reg_op2 : reg_op1 + reg_op2;",
        "		alu_add_sub = instr_sub ? reg_op1 + reg_op2 : reg_op1 - reg_op2;",
        "ADD/SUB (and ADDI: it shares alu_add_sub) operands swapped: "
        "addition subtracts, subtraction adds (G1)",
    ),
    (
        "and-or-swap",
        "instr_andi || instr_and:\n\t\t\t\talu_out = reg_op1 & reg_op2;",
        "instr_andi || instr_and:\n\t\t\t\talu_out = reg_op1 | reg_op2;",
        "AND/ANDI compute OR (G1)",
    ),
    (
        "xor-and-swap",
        "instr_xori || instr_xor:\n\t\t\t\talu_out = reg_op1 ^ reg_op2;",
        "instr_xori || instr_xor:\n\t\t\t\talu_out = reg_op1 & reg_op2;",
        "XOR/XORI compute AND (G1)",
    ),
    (
        "sll-shr-swap",
        "		alu_shl = reg_op1 << reg_op2[4:0];",
        "		alu_shl = reg_op1 >> reg_op2[4:0];",
        "SLL/SLLI shift right instead of left (G1)",
    ),
    # ---- T3: sign/zero-extension -----------------------------------------
    (
        "lts-unsigned",
        "		alu_lts = $signed(reg_op1) < $signed(reg_op2);",
        "		alu_lts = reg_op1 < reg_op2;",
        "signed compare becomes unsigned: SLT/SLTI/BLT/BGE wrong for "
        "negative operands (G1)",
    ),
    (
        "sra-sign-drop",
        "		alu_shr = $signed({instr_sra || instr_srai ? reg_op1[31] : 1'b0, reg_op1}) >>> reg_op2[4:0];",
        "		alu_shr = $signed({instr_sra || instr_srai ? 1'b0 : 1'b0, reg_op1}) >>> reg_op2[4:0];",
        "SRA/SRAI lose their sign-fill bit and become SRL (G1)",
    ),
    (
        "imm-i-unsign",
        "				decoded_imm <= $signed(mem_rdata_q[31:20]);",
        "				decoded_imm <= {20'b0, mem_rdata_q[31:20]};",
        "I-immediate (JALR/loads/OP-IMM) zero-extended: negative "
        "immediates decode large-positive (G1)",
    ),
    (
        "lb-unsign",
        "latched_is_lb: reg_out <= $signed(mem_rdata_word[7:0]);",
        "latched_is_lb: reg_out <= mem_rdata_word[7:0];",
        "LB returns zero-extended byte (G1 lb)",
    ),
    (
        "lh-unsign",
        "latched_is_lh: reg_out <= $signed(mem_rdata_word[15:0]);",
        "latched_is_lh: reg_out <= mem_rdata_word[15:0];",
        "LH returns zero-extended halfword (G1 lh)",
    ),
    # ---- T3: off-by-one ---------------------------------------------------
    (
        "lui-shift-16",
        "				decoded_imm <= mem_rdata_q[31:12] << 12;",
        "				decoded_imm <= mem_rdata_q[31:12] << 16;",
        "U-immediate shifted by 16 not 12: LUI/AUIPC off by 4 bits (G1)",
    ),
    (
        "bimm-x2",
        "					decoded_imm <= $signed({mem_rdata_q[31], mem_rdata_q[7], mem_rdata_q[30:25], mem_rdata_q[11:8], 1'b0});",
        "					decoded_imm <= $signed({mem_rdata_q[31], mem_rdata_q[7], mem_rdata_q[30:25], mem_rdata_q[11:8], 2'b00});",
        "branch immediate one bit too wide: all branch offsets doubled "
        "(G1)",
    ),
    (
        "store-addr-plus4",
        "reg_op1 <= reg_op1 + decoded_imm;\n\t\t\t\t\t\tset_mem_do_wdata = 1;",
        "reg_op1 <= reg_op1 + decoded_imm + 4;\n\t\t\t\t\t\tset_mem_do_wdata = 1;",
        "store address computed one word too high (G1 ld_st/sw)",
    ),
    (
        "load-addr-plus4",
        "reg_op1 <= reg_op1 + decoded_imm;\n\t\t\t\t\t\tset_mem_do_rdata = 1;",
        "reg_op1 <= reg_op1 + decoded_imm + 4;\n\t\t\t\t\t\tset_mem_do_rdata = 1;",
        "load address computed one word too high (G1 lw/ld_st)",
    ),
    (
        "pc-plus8",
        "irq_delay <= irq_active;\n\t\t\t\t\treg_next_pc <= current_pc + (compressed_instr ? 2 : 4);",
        "irq_delay <= irq_active;\n\t\t\t\t\treg_next_pc <= current_pc + (compressed_instr ? 2 : 8);",
        "sequential fetch advances PC by 8: every second instruction "
        "skipped (G1)",
    ),
    # ---- T3: dropped write enable ----------------------------------------
    (
        "drop-link-we",
        "latched_branch: begin\n\t\t\t\t\tcpuregs_wrdata = reg_pc + (latched_compr ? 2 : 4);\n\t\t\t\t\tcpuregs_write = 1;",
        "latched_branch: begin\n\t\t\t\t\tcpuregs_wrdata = reg_pc + (latched_compr ? 2 : 4);\n\t\t\t\t\tcpuregs_write = 0;",
        "JAL/JALR branch correctly but never write the link register "
        "(G1 jal/jalr)",
    ),
    (
        "drop-reg-we",
        "latched_store && !latched_branch: begin\n\t\t\t\t\tcpuregs_wrdata = latched_stalu ? alu_out_q : reg_out;\n\t\t\t\t\tcpuregs_write = 1;",
        "latched_store && !latched_branch: begin\n\t\t\t\t\tcpuregs_wrdata = latched_stalu ? alu_out_q : reg_out;\n\t\t\t\t\tcpuregs_write = 0;",
        "register file write enable dropped: no instruction writes rd "
        "(G1)",
    ),
    (
        "read-becomes-write",
        "						mem_wstrb <= 0;",
        "						mem_wstrb <= 4'b1111;",
        "the read/fetch request launch drives wstrb=1111 instead of 0: "
        "every load and every instruction fetch writes stale mem_wdata "
        "into mem[addr], corrupting memory (G1 - first fetch already "
        "scribbles over instruction memory)",
    ),
    # ---- T3: branch-condition flips ---------------------------------------
    (
        "bge-cond-flip",
        "instr_bge:\n\t\t\t\talu_out_0 = !alu_lts;",
        "instr_bge:\n\t\t\t\talu_out_0 = alu_lts;",
        "BGE behaves as BLT (G1 bge)",
    ),
    (
        "bgeu-cond-flip",
        "instr_bgeu:\n\t\t\t\talu_out_0 = !alu_ltu;",
        "instr_bgeu:\n\t\t\t\talu_out_0 = alu_ltu;",
        "BGEU behaves as BLTU (G1 bgeu)",
    ),
    (
        "eq-ne-flip",
        "		alu_eq = reg_op1 == reg_op2;",
        "		alu_eq = reg_op1 != reg_op2;",
        "equality comparator inverted: BEQ/BNE both flip (G1)",
    ),
    # ---- T3: decode + targeted gate hits ----------------------------------
    (
        "rs1-rs2-swap",
        "			decoded_rs1 <= mem_rdata_latched[19:15];\n			decoded_rs2 <= mem_rdata_latched[24:20];",
        "			decoded_rs1 <= mem_rdata_latched[24:20];\n			decoded_rs2 <= mem_rdata_latched[19:15];",
        "rs1/rs2 fields swapped in the decoder (G1)",
    ),
    (
        "fence-undecoded",
        "instr_fence <= (mem_rdata_q[6:0] == 7'b0001111 && !mem_rdata_q[14:12]);",
        "instr_fence <= (mem_rdata_q[6:0] == 7'b0001110 && !mem_rdata_q[14:12]);",
        "FENCE (opcode 0x0F) no longer decodes: FENCE traps. rv32ui has "
        "no plain FENCE (fence_i excluded), so G1 passes; G2's coverage "
        "block contains one (G2)",
    ),
    (
        "trap-stuck-lo",
        "cpu_state_trap: begin\n\t\t\t\ttrap <= 1;",
        "cpu_state_trap: begin\n\t\t\t\ttrap <= 0;",
        "the trap output is never asserted: the CPU still halts but the "
        "tb sees no trap - killed by G3's --expect-trap tests",
    ),
    (
        "ebreak-uncaught",
        "instr_ecall_ebreak <= ((mem_rdata_q[6:0] == 7'b1110011 && !mem_rdata_q[31:21] && !mem_rdata_q[19:7]) ||",
        "instr_ecall_ebreak <= ((mem_rdata_q[6:0] == 7'b1110011 && !mem_rdata_q[31:20] && !mem_rdata_q[19:7]) ||",
        "the SYSTEM-imm window shrinks from bits[31:21] to [31:20]: "
        "EBREAK (imm=1) is no longer *specially* decoded. SURVIVOR BY "
        "CONSTRUCTION in the judge's config (WITH_PCPI=0, ENABLE_IRQ=0, "
        "CATCH_ILLINSN=1): EBREAK still traps through the instr_trap "
        "illegal-instruction path (picorv32.v:1585), and instr_ecall_ebreak "
        "has no other observable fanout, so no directed test can see the "
        "edit. Proven equivalent by lec.sh netlist identity (yosys "
        "optimizes the signal away on BOTH sides)",
    ),
    (
        "lw-misalign-blind",
        "if (mem_wordsize == 0 && reg_op1[1:0] != 0) begin",
        "if (mem_wordsize == 0 && reg_op1[1:0] != 2'b11) begin",
        "misaligned-word check misses addr%4==3: the lw_misaligned G3 "
        "test (addr 0x103) no longer traps",
    ),
    (
        "sb-lane-shift",
        "				mem_la_wstrb = 4'b0001 << reg_op1[1:0];",
        "				mem_la_wstrb = 4'b0010 << reg_op1[1:0];",
        "SB writes one byte lane up (G1 sb)",
    ),
]


def load_reference():
    with open(PICO_V) as f:
        return f.read()


def apply_edit(src, search, replace):
    if src.count(search) != 1:
        raise SystemExit(
            "edit anchor not unique (%d hits) - pin drifted?" % src.count(search))
    return src.replace(search, replace)


def main(argv):
    out_dir = OUT_DIR
    if "--outdir" in argv:
        i = argv.index("--outdir")
        try:
            out_dir = argv[i + 1]
        except IndexError:
            raise SystemExit("--outdir needs an argument")
    if "--list" in argv:
        for name, _, _, _ in MUTANTS:
            print(name)
        return 0
    if "--describe" in argv:
        for name, _, _, why in MUTANTS:
            print("%-20s %s" % (name, why))
        return 0
    os.makedirs(out_dir, exist_ok=True)
    src = load_reference()
    for name, search, replace, why in MUTANTS:
        mdir = os.path.join(out_dir, name)
        os.makedirs(mdir, exist_ok=True)
        out = os.path.join(mdir, "picorv32.v")
        with open(out, "w") as f:
            f.write(apply_edit(src, search, replace))
        print("wrote %s  (%s)" % (out, why))
    print("%d mutants written to %s" % (len(MUTANTS), out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
