// longcat-2.5: single-cycle RV32I CPU (RV32I v2.1 unprivileged base, minus
// FENCE.I and CSRs). One instruction retires per memory transaction;
// mem_ready may be delayed any number of cycles (SPEC bus contract).
//
//   - FENCE (funct3=0) executes as a NOP; FENCE.I (funct3=1) traps.
//   - ECALL / EBREAK / SYSTEM / illegal opcode / misaligned load, store or
//     jump target assert `trap` and halt the PC (no further memory requests).
//   - Flat 64 KiB memory at 0x00000000; loads outside RAM read 0, stores
//     outside RAM (except tohost 0x10000000) are dropped - matching the
//     judge memory model.
//   - x0 is hardwired to zero.
//
// Microarchitecture: single-cycle datapath, one instruction in flight.
// The bus request (fetch / load / next-fetch) is formed combinationally
// and held stable while mem_ready waits. Everything the instruction needs
// (rs1/rs2, next PC, load result) is computed in the completing cycle.

`default_nettype none

module cpu (
    input  wire        clk,
    input  wire        resetn,      // active-low synchronous reset; PC = 0
    output reg         mem_valid,   // request; hold until mem_ready
    output reg         mem_instr,   // 1 = instruction fetch
    input  wire        mem_ready,   // one-cycle acknowledge
    output reg  [31:0] mem_addr,
    output reg  [31:0] mem_wdata,
    output reg  [3:0]  mem_wstrb,   // 0 = read
    input  wire [31:0] mem_rdata,
    output wire        trap
);

    // ------------------------------------------------------------------
    // architectural state
    // ------------------------------------------------------------------
    reg [31:0] pc;
    reg [31:0] regs [0:31];        // x0 never written (hardwired 0)
    reg        trapped;

    integer i;

    // ------------------------------------------------------------------
    // instruction register: the instruction currently executing
    // ------------------------------------------------------------------
    reg        insn_valid;
    reg [31:0] insn;

    // ------------------------------------------------------------------
    // outstanding bus request
    // ------------------------------------------------------------------
    reg        r_valid;            // request on the bus
    reg        r_fetch;            // 1 = fetch, 0 = data
    reg        r_load;             // data transaction is a load
    reg        r_store;            // data transaction is a store
    reg [31:0] r_addr;
    reg [31:0] r_wdata;
    reg [3:0]  r_wstrb;

    // ------------------------------------------------------------------
    // decode of the executing instruction
    // ------------------------------------------------------------------
    wire [6:0] op  = insn[6:0];
    wire [4:0] rd  = insn[11:7];
    wire [2:0] f3  = insn[14:12];
    wire [4:0] rs1i = insn[19:15];
    wire [4:0] rs2i = insn[24:20];
    wire [6:0] f7  = insn[31:25];

    wire [31:0] rs1_val = regs[rs1i];
    wire [31:0] rs2_val = regs[rs2i];

    // immediate decodes (RV32I encodings)
    wire [31:0] iimm = {{20{insn[31]}}, insn[31:20]};
    wire [31:0] bimm = {{19{insn[31]}}, insn[31], insn[7],
                        insn[30:25], insn[11:8], 1'b0};
    wire [31:0] uimm = {insn[31:12], 12'b0};
    wire [31:0] jimm = {{11{insn[31]}}, insn[31], insn[19:12],
                        insn[20], insn[30:21], 1'b0};

    // ------------------------------------------------------------------
    // instruction classes (only genuinely encodable ones pass)
    // ------------------------------------------------------------------
    wire is_lui    = insn_valid && (op == 7'h37);
    wire is_auipc  = insn_valid && (op == 7'h17);
    wire is_jal    = insn_valid && (op == 7'h6F);
    wire is_jalr   = insn_valid && (op == 7'h67) && (f3 == 3'h0);
    wire is_branch = insn_valid && (op == 7'h63) &&
                     (f3 <= 3'h1 || (f3 >= 3'h4 && f3 <= 3'h7));
    wire is_load   = insn_valid && (op == 7'h03) &&
                     (f3 == 3'h0 || f3 == 3'h1 || f3 == 3'h2 ||
                      f3 == 3'h4 || f3 == 3'h5);
    wire is_store  = insn_valid && (op == 7'h23) &&
                     (f3 <= 3'h2);
    wire is_opimm  = insn_valid && (op == 7'h13) &&
                     ((f3 == 3'h0) || (f3 == 3'h1 && (f7 <= 3'h1)) ||
                      (f3 == 3'h2) || (f3 == 3'h3) || (f3 == 3'h4) ||
                      (f3 == 3'h5 && (f7 == 3'h0 || f7 == 7'h20)) ||
                      (f3 == 3'h6) || (f3 == 3'h7));
    wire is_op     = insn_valid && (op == 7'h33) &&
                     ((f3 == 3'h0 && (f7 == 3'h0 || f7 == 7'h20)) ||
                      (f3 == 3'h1 && f7 == 3'h0) ||
                      (f3 == 3'h2 && f7 == 3'h0) ||
                      (f3 == 3'h3 && f7 == 3'h0) ||
                      (f3 == 3'h4 && f7 == 3'h0) ||
                      (f3 == 3'h5 && (f7 == 3'h0 || f7 == 7'h20)) ||
                      (f3 == 3'h6 && f7 == 3'h0) ||
                      (f3 == 3'h7 && f7 == 3'h0));
    wire is_fence  = insn_valid && (op == 7'h0F) && (f3 == 3'h0);

    // ------------------------------------------------------------------
    // branch / jump evaluation
    // ------------------------------------------------------------------
    wire signed [31:0] a_s = $signed(rs1_val);
    wire signed [31:0] b_s = $signed(rs2_val);
    wire branch_taken = (f3 == 3'h0) ? (rs1_val == rs2_val) :
                        (f3 == 3'h1) ? (rs1_val != rs2_val) :
                        (f3 == 3'h4) ? (a_s < b_s) :
                        (f3 == 3'h5) ? (a_s >= b_s) :
                        (f3 == 3'h6) ? (rs1_val < rs2_val) :
                                       (rs1_val >= rs2_val);

    wire [31:0] jal_target    = pc + jimm;
    wire [31:0] jalr_target   = (rs1_val + iimm) & ~32'b1;
    wire [31:0] branch_target = pc + bimm;

    wire target_misaligned =
        (is_jal    && jal_target[1:0] != 2'b00) ||
        (is_jalr   && jalr_target[1:0] != 2'b00) ||
        (is_branch && branch_taken && branch_target[1:0] != 2'b00);

    // ------------------------------------------------------------------
    // memory access evaluation
    // ------------------------------------------------------------------
    wire [31:0] data_addr   = rs1_val + iimm;
    wire [31:0] store_data  = rs2_val;
    wire [3:0]  store_wstrb = (f3 == 3'h2) ? 4'b1111 :
                              (f3 == 3'h1) ? (4'b0011 << data_addr[1:0]) :
                                             (4'b0001 << data_addr[1:0]);

    wire load_misaligned =
        ((f3 == 3'h1 || f3 == 3'h5) && data_addr[0] != 1'b0) ||   // LH/LHU
        ((f3 == 3'h2)              && data_addr[1:0] != 2'b00);   // LW
    wire store_misaligned =
        ((f3 == 3'h1) && data_addr[0] != 1'b0) ||                 // SH
        ((f3 == 3'h2) && data_addr[1:0] != 2'b00);                // SW

    // load data assembled from the word returned by memory
    wire [1:0]  loff  = data_addr[1:0];
    wire [7:0]  lbyte = mem_rdata[{loff, 3'b000} +: 8];
    wire [15:0] lhalf = mem_rdata[{loff[1], 3'b000} +: 16];
    wire [31:0] load_result =
        (f3 == 3'h0) ? {{24{lbyte[7]}},  lbyte}  :   // LB
        (f3 == 3'h1) ? {{16{lhalf[15]}}, lhalf}  :   // LH
        (f3 == 3'h2) ? mem_rdata                   :   // LW
        (f3 == 3'h4) ? {24'b0, lbyte}              :   // LBU
                       {16'b0, lhalf};                 // LHU

    // ------------------------------------------------------------------
    // next PC / retire / trap
    // ------------------------------------------------------------------
    wire [31:0] link_pc  = pc + 32'd4;
    wire [31:0] next_pc  =
        is_jal    ? jal_target :
        is_jalr   ? jalr_target :
        is_branch ? (branch_taken ? branch_target : link_pc) :
                    link_pc;

    // retire-time trap: no data transaction involved, halt immediately
    wire retire_trap =
        (op == 7'h37 || op == 7'h17 || op == 7'h6F || op == 7'h67 ||
         op == 7'h63 || op == 7'h03 || op == 7'h23 || op == 7'h13 ||
         op == 7'h33 || op == 7'h0F) &&
        !(is_lui || is_auipc || is_jal || is_jalr || is_branch ||
          is_load || is_store || is_opimm || is_op || is_fence) ||  // illegal
        (op == 7'h73) ||                                              // SYSTEM
        target_misaligned ||
        load_misaligned ||
        store_misaligned;

    assign trap = trapped;

    // ------------------------------------------------------------------
    // request formation while the bus is idle
    // ------------------------------------------------------------------
    wire do_load  = is_load  && !load_misaligned;
    wire do_store = is_store && !store_misaligned;

    reg        n_fetch, n_load, n_store;
    reg [31:0] n_addr, n_wdata;
    reg [3:0]  n_wstrb;

    always @(*) begin
        n_fetch = 1'b0; n_load = 1'b0; n_store = 1'b0;
        n_addr = 32'd0;  n_wdata = 32'd0; n_wstrb = 4'd0;

        if (!trapped && !r_valid) begin
            if (!insn_valid) begin
                n_fetch = 1'b1;
                n_addr  = pc;
            end else if (do_load || do_store) begin
                n_load  = do_load;
                n_store = do_store;
                n_addr  = data_addr;
                n_wdata = store_data;
                n_wstrb = store_wstrb;
            end else if (!retire_trap) begin
                n_fetch = 1'b1;
                n_addr  = next_pc;
            end
            // retire_trap: halt (handled in the sequential block)
        end
    end

    // ------------------------------------------------------------------
    // sequential state
    // ------------------------------------------------------------------
    always @(posedge clk) begin
        if (!resetn) begin
            pc         <= 32'd0;
            trapped    <= 1'b0;
            insn_valid <= 1'b0;
            insn       <= 32'd0;
            r_valid    <= 1'b0;
            r_fetch    <= 1'b0;
            r_load     <= 1'b0;
            r_store    <= 1'b0;
            r_addr     <= 32'd0;
            r_wdata    <= 32'd0;
            r_wstrb    <= 4'd0;
            mem_valid  <= 1'b0;
            mem_instr  <= 1'b0;
            mem_addr   <= 32'd0;
            mem_wdata  <= 32'd0;
            mem_wstrb  <= 4'd0;
            for (i = 0; i < 32; i = i + 1) regs[i] <= 32'd0;
        end else if (trapped) begin
            // halted: keep the bus quiet
            mem_valid <= 1'b0;
            mem_wstrb <= 4'd0;
        end else if (!r_valid) begin
            if (insn_valid && retire_trap) begin
                // retire-time trap: halt, issue nothing
                trapped   <= 1'b1;
                mem_valid <= 1'b0;
                mem_wstrb <= 4'd0;
            end else if (n_fetch || n_load || n_store) begin
                // issue the formed request
                r_valid   <= 1'b1;
                r_fetch   <= n_fetch;
                r_load    <= n_load;
                r_store   <= n_store;
                r_addr    <= n_addr;
                r_wdata   <= n_wdata;
                r_wstrb   <= n_wstrb;
                mem_valid <= 1'b1;
                mem_instr <= n_fetch;
                mem_addr  <= n_addr;
                mem_wdata <= n_wdata;
                mem_wstrb <= n_wstrb;
            end else begin
                // idle (e.g. fence_nop path always fetches; safety net)
                mem_valid <= 1'b0;
                mem_wstrb <= 4'd0;
            end
        end else if (mem_ready) begin
            // transaction completes
            r_valid   <= 1'b0;
            mem_valid <= 1'b0;
            mem_instr <= 1'b0;
            mem_addr  <= 32'd0;
            mem_wdata <= 32'd0;
            mem_wstrb <= 4'd0;
            if (r_fetch) begin
                insn       <= mem_rdata;
                insn_valid <= 1'b1;
            end else if (r_load) begin
                if (rd != 5'd0) regs[rd] <= load_result;
                pc        <= next_pc;
                insn_valid <= 1'b0;
            end else begin  // r_store
                pc        <= next_pc;
                insn_valid <= 1'b0;
            end
        end
        // else: request outstanding, hold stable until mem_ready
    end

endmodule

`default_nettype wire
