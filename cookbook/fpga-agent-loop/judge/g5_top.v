// IO-reducing wrapper for gate G5 (SPEC.md): the ~105-bit native memory
// interface of `cpu` is bound to an internal 16 KiB scratch RAM, so the
// synthesized top level has only 3 pins (clk, resetn, trap) and P&R does
// not depend on pin availability or a pinout. Combinational mem_ready
// (1-cycle) and word-addressed read/write mirror the judge memory model.
//
// NOT used for simulation — grading simulation uses tb.cpp. This file only
// exists so `yosys synth_ecp5 -top top` sees a closed system.

`default_nettype none

module top (
    input  wire clk,
    input  wire resetn,
    output wire trap
);
    wire        mem_valid;
    wire        mem_instr;
    wire        mem_ready;
    wire [31:0] mem_addr;
    wire [31:0] mem_wdata;
    wire [ 3:0] mem_wstrb;
    wire [31:0] mem_rdata;

    // 16 KiB internal scratch RAM (word address comes from mem_addr[13:2];
    // the upper bits of mem_addr are outside the wrapped region and are
    // intentionally ignored — G5 measures the CPU, not an address decoder).
    reg [31:0] mem [0:4095];

    assign mem_ready = mem_valid;
    assign mem_rdata = mem[mem_addr[13:2]];

    always @(posedge clk) begin
        if (mem_valid && mem_ready) begin
            if (mem_wstrb[0]) mem[mem_addr[13:2]][ 7: 0] <= mem_wdata[ 7: 0];
            if (mem_wstrb[1]) mem[mem_addr[13:2]][15: 8] <= mem_wdata[15: 8];
            if (mem_wstrb[2]) mem[mem_addr[13:2]][23:16] <= mem_wdata[23:16];
            if (mem_wstrb[3]) mem[mem_addr[13:2]][31:24] <= mem_wdata[31:24];
        end
    end

    cpu dut (
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
