/*
 * picorv32_cpu.v — Thin wrapper around YosysHQ/picorv32 for judge compatibility
 *
 * PicoRV32 commit: ef203c2b0a3fb793280f5114941416c425c5b461
 * Configuration per SPEC.md:
 *   ENABLE_COUNTERS=0, CATCH_MISALIGN=1, CATCH_ILLINSN=1,
 *   ENABLE_REGS_DUALPORT=1, COMPRESSED_ISA=0, BARREL_SHIFTER=1
 *
 * Maps picorv32's native memory interface to judge's cpu interface.
 * The trap signal maps directly.
 */

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

    // Instantiate picorv32 with judge-required parameters
    picorv32 #(
        .ENABLE_COUNTERS       (1'b0),
        .ENABLE_COUNTERS64     (1'b0),
        .ENABLE_REGS_16_31     (1'b1),
        .ENABLE_REGS_DUALPORT  (1'b1),
        .LATCHED_MEM_RDATA     (1'b0),
        .TWO_STAGE_SHIFT       (1'b1),
        .BARREL_SHIFTER        (1'b1),
        .TWO_CYCLE_COMPARE     (1'b0),
        .TWO_CYCLE_ALU         (1'b0),
        .COMPRESSED_ISA        (1'b0),
        .CATCH_MISALIGN        (1'b1),
        .CATCH_ILLINSN         (1'b1),
        .ENABLE_PCPI           (1'b0),
        .ENABLE_MUL            (1'b0),
        .ENABLE_FAST_MUL       (1'b0),
        .ENABLE_DIV            (1'b0),
        .ENABLE_IRQ            (1'b0),
        .ENABLE_IRQ_QREGS      (1'b1),
        .ENABLE_IRQ_TIMER      (1'b1),
        .ENABLE_TRACE          (1'b0),
        .REGS_INIT_ZERO        (1'b0),
        .MASKED_IRQ            (32'h0000_0000),
        .LATCHED_IRQ           (32'hffff_ffff),
        .PROGADDR_RESET        (32'h8000_0000),
        .PROGADDR_IRQ          (32'h0000_0010),
        .STACKADDR             (32'hffff_ffff)
    ) picorv32_core (
        .clk        (clk),
        .resetn     (resetn),
        .trap       (trap),

        .mem_valid  (mem_valid),
        .mem_instr  (mem_instr),
        .mem_ready  (mem_ready),
        .mem_addr   (mem_addr),
        .mem_wdata  (mem_wdata),
        .mem_wstrb  (mem_wstrb),
        .mem_rdata  (mem_rdata),

        // Unused interfaces - tie off
        .mem_la_read    (),
        .mem_la_write   (),
        .mem_la_addr    (),
        .mem_la_wdata   (),
        .mem_la_wstrb   (),

        .pcpi_valid     (),
        .pcpi_insn      (),
        .pcpi_rs1       (),
        .pcpi_rs2       (),
        .pcpi_wr        (1'b0),
        .pcpi_rd        (32'h0),
        .pcpi_wait      (1'b0),
        .pcpi_ready     (1'b0),

        .irq            (32'h0),
        .eoi            ()
    );

endmodule

// Include the full picorv32 core
`include "picorv32_core.v"