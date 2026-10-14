// Reference control for the fpga-agent-loop judge (T1 known-good CPU).
//
// Thin wrapper around YosysHQ/picorv32 @ the pinned SHA recorded in
// judge/setup.sh (PICO_SHA); picorv32.v itself is fetched by setup.sh into
// $HOME/riscv-toolchain/picorv32/picorv32.v (sha256-checked there, never
// vendored into this repo) and is found via the PICORV32_DIR include path
// that grade.sh passes to both Verilator and yosys.
//
// Interface: exactly the SPEC.md `cpu` port list. Configuration:
//   RV32I only, no C/M extension, no IRQ, no CSRs (ENABLE_COUNTERS=0),
//   COMPRESSED_ISA=0, CATCH_MISALIGN=1, CATCH_ILLINSN=1,
//   ENABLE_REGS_DUALPORT=1, BARREL_SHIFTER=1.
//
// ECALL/EBREAK map to `trap`: with ENABLE_IRQ=0 and CATCH_ILLINSN=1,
// picorv32 routes instr_ecall_ebreak to cpu_state_trap like any other
// unsupported instruction (picorv32.v, cpu_state_ld_rs1 case).

// Fetched by setup.sh; found via the PICORV32_DIR include path passed
// by grade.sh (verilator -I / yosys read_verilog -I).
`include "picorv32.v"

`default_nettype none

module cpu (
    input  wire        clk,
    input  wire        resetn,
    output wire        mem_valid,
    output wire        mem_instr,
    input  wire        mem_ready,
    output wire [31:0] mem_addr,
    output wire [31:0] mem_wdata,
    output wire [ 3:0] mem_wstrb,
    input  wire [31:0] mem_rdata,
    output wire        trap
);

    picorv32 #(
        .ENABLE_COUNTERS      (0),
        .ENABLE_COUNTERS64    (0),
        .ENABLE_REGS_16_31    (1),
        .ENABLE_REGS_DUALPORT (1),
        .LATCHED_MEM_RDATA    (0),
        .TWO_STAGE_SHIFT      (0),
        .BARREL_SHIFTER       (1),
        .TWO_CYCLE_COMPARE    (0),
        .TWO_CYCLE_ALU        (0),
        .COMPRESSED_ISA       (0),
        .CATCH_MISALIGN       (1),
        .CATCH_ILLINSN        (1),
        .ENABLE_PCPI          (0),
        .ENABLE_MUL           (0),
        .ENABLE_FAST_MUL      (0),
        .ENABLE_DIV           (0),
        .ENABLE_IRQ           (0),
        .ENABLE_IRQ_QREGS     (0),
        .ENABLE_IRQ_TIMER    (0),
        .ENABLE_TRACE         (0),
        .REGS_INIT_ZERO       (0),
        .PROGADDR_RESET       (32'h 0000_0000)
    ) core (
        .clk       (clk),
        .resetn    (resetn),
        .mem_valid (mem_valid),
        .mem_instr (mem_instr),
        .mem_ready (mem_ready),
        .mem_addr  (mem_addr),
        .mem_wdata (mem_wdata),
        .mem_wstrb (mem_wstrb),
        .mem_rdata (mem_rdata),
        .trap      (trap)
    );

endmodule

`default_nettype wire
