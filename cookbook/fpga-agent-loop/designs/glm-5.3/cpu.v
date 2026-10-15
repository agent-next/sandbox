// cpu.v — RV32I core for the fpga-agent-loop judge (design glm-5.3).
//
// Fused fetch/execute multicycle FSM, written from SPEC.md alone.
//
//   * Three states: FETCH, MEM (data phase of a load/store), TRAP (halted).
//   * The in-flight instruction is decoded straight off mem_rdata during the
//     fetch bus cycle; every non-memory instruction (ALU, LUI, AUIPC, branch,
//     JAL, JALR, FENCE) executes at the very edge the fetch completes.  With
//     zero-latency memory that costs 1 cycle per ALU/branch/jump instruction
//     and 2 per load/store.
//   * One 32x32 register file, asynchronous read / synchronous write, x0
//     never written so it reads as constant zero.
//   * Traps (illegal opcode or encoding, ECALL/EBREAK/SYSTEM, misaligned
//     load/store, misaligned taken-branch/JAL/JALR target) are decided at the
//     fetch-completing edge; no data request is ever issued for a trapping
//     instruction and the bus stays quiet after trap.
//
// All bus outputs are held stable for the whole request; the request is
// retired at the posedge on which mem_ready is high, sampling mem_rdata
// (valid only in that cycle).

module cpu (
    input  wire        clk,
    input  wire        resetn,      // active-low synchronous reset, PC = 0
    output wire        mem_valid,   // request; held until mem_ready
    output wire        mem_instr,   // 1 = instruction fetch
    input  wire        mem_ready,   // one-cycle acknowledge
    output wire [31:0] mem_addr,    // word-aligned fetch / byte data address
    output wire [31:0] mem_wdata,
    output wire [3:0]  mem_wstrb,   // 0 = read, else write byte lanes
    input  wire [31:0] mem_rdata,   // valid only in the mem_ready cycle
    output wire        trap         // sticky halt on trap conditions
);

    // ------------------------------------------------------------------
    // state
    // ------------------------------------------------------------------
    localparam [1:0] S_FETCH = 2'd0,   // fetching an instruction at pc_q
                     S_MEM   = 2'd1,   // load/store data phase (addr_q held)
                     S_TRAP  = 2'd2;   // halted: no further bus activity

    reg [1:0]  state;
    reg [31:0] pc_q;            // fetch address of the in-flight instruction
    reg [31:0] daddr_q;         // load/store address (data phase)
    reg [3:0]  dwstrb_q;        // store lanes pending in S_MEM (0 = load)
    reg [31:0] dwdata_q;        // store data pending in S_MEM
    reg [4:0]  drd_q;           // destination register of the pending load
    reg [2:0]  dsize_q;         // load width/sign pending in S_MEM
    reg        trap_q;

    wire       fetch_done = (state == S_FETCH) && mem_ready;
    wire       mem_done   = (state == S_MEM)   && mem_ready;

    assign mem_valid = (state == S_FETCH) || (state == S_MEM);
    assign mem_instr = (state == S_FETCH);
    assign mem_wstrb = (state == S_MEM) ? dwstrb_q : 4'h0;
    assign mem_addr  = (state == S_FETCH) ? pc_q    : daddr_q;
    assign mem_wdata = (state == S_MEM)   ? dwdata_q : 32'h0;
    assign trap      = trap_q;

    // ------------------------------------------------------------------
    // register file: async read, sync write, x0 = 0
    // ------------------------------------------------------------------
    reg [31:0] regs [0:31];
    integer i;

    wire [4:0] d_rd  = mem_rdata[11:7];
    wire [4:0] d_rs1 = mem_rdata[19:15];
    wire [4:0] d_rs2 = mem_rdata[24:20];

    wire [31:0] rs1_val = (d_rs1 != 0) ? regs[d_rs1] : 32'h0;
    wire [31:0] rs2_val = (d_rs2 != 0) ? regs[d_rs2] : 32'h0;

    // instruction fields
    wire [6:0]  d_op  = mem_rdata[6:0];
    wire [2:0]  d_f3  = mem_rdata[14:12];
    wire [6:0]  d_f7  = mem_rdata[31:25];

    // immediates
    wire [31:0] imm_i = {{20{mem_rdata[31]}}, mem_rdata[31:20]};
    wire [31:0] imm_s = {{20{mem_rdata[31]}}, mem_rdata[31:25],
                          mem_rdata[11:7]};
    wire [31:0] imm_b = {{19{mem_rdata[31]}}, mem_rdata[31], mem_rdata[7],
                          mem_rdata[30:25], mem_rdata[11:8], 1'b0};
    wire [31:0] imm_u = {mem_rdata[31:12], 12'h0};
    wire [31:0] imm_j = {{11{mem_rdata[31]}}, mem_rdata[31], mem_rdata[19:12],
                          mem_rdata[20], mem_rdata[30:21], 1'b0};

    // ------------------------------------------------------------------
    // legality decode (bit-exact with the judge ISS)
    // ------------------------------------------------------------------
    wire op_lui   = (d_op == 7'b0110111);
    wire op_auipc = (d_op == 7'b0010111);
    wire op_jal   = (d_op == 7'b1101111);
    wire op_jalr  = (d_op == 7'b1100111) && (d_f3 == 3'b000);
    wire op_br    = (d_op == 7'b1100011) && (d_f3 != 3'b010)
                                          && (d_f3 != 3'b011);
    wire op_load  = (d_op == 7'b0000011) && (d_f3 != 3'b011)
                                          && (d_f3 != 3'b110)
                                          && (d_f3 != 3'b111);
    wire op_store = (d_op == 7'b0100011) && (d_f3 != 3'b100)
                                          && (d_f3 != 3'b101)
                                          && (d_f3 != 3'b110)
                                          && (d_f3 != 3'b111);
    // OP-IMM: SLLI legal iff f7[6:1]==0 (f7 = 0x00 or 0x01);
    //         SRLI/SRAI legal iff f7 = 0x00 or 0x20; other f3 unconstrained
    wire op_imm   = (d_op == 7'b0010011) &&
                    ((d_f3 == 3'b001) ? (d_f7[6:1] == 6'b000000) :
                     (d_f3 == 3'b101) ? (d_f7[6] == 1'b0 &&
                                         d_f7[4:0] == 5'b00000) :
                     1'b1);
    // R-type: ADD/SUB and SRL/SRA legal iff f7 = 0x00 or 0x20; every other
    // f3 requires f7 == 0
    wire op_rr    = (d_op == 7'b0110011) &&
                    ((d_f3 == 3'b000 || d_f3 == 3'b101)
                        ? (d_f7[6] == 1'b0 && d_f7[4:0] == 5'b00000)
                        : (d_f7 == 7'b0000000));
    wire op_fence = (d_op == 7'b0001111) && (d_f3 == 3'b000);  // FENCE = NOP
    wire op_sys   = (d_op == 7'b1110011);   // ECALL/EBREAK/CSR: always trap

    wire ill_insn = ~(op_lui | op_auipc | op_jal | op_jalr | op_br | op_load |
                      op_store | op_imm | op_rr | op_fence);

    // ------------------------------------------------------------------
    // operand fetch / ALU
    // ------------------------------------------------------------------
    wire        is_rr    = (d_op == 7'b0110011);
    wire [31:0] alu_b    = is_rr ? rs2_val : imm_i;
    wire [4:0]  shamt    = is_rr ? rs2_val[4:0] : imm_i[4:0];

    wire [31:0] add_r    = rs1_val + alu_b;
    wire [31:0] sub_r    = rs1_val - rs2_val;
    wire [31:0] and_r    = rs1_val & alu_b;
    wire [31:0] or_r     = rs1_val | alu_b;
    wire [31:0] xor_r    = rs1_val ^ alu_b;
    wire        lt_s     = $signed(rs1_val) < $signed(alu_b);
    wire        lt_u     = rs1_val < alu_b;
    wire [31:0] sll_r    = rs1_val << shamt;
    wire [31:0] srl_r    = rs1_val >> shamt;
    wire [31:0] sra_r    = $signed(rs1_val) >>> shamt;

    reg  [31:0] alu_r;
    always @* begin
        case (d_f3)
            3'b000:  alu_r = (is_rr && d_f7[5]) ? sub_r : add_r;
            3'b001:  alu_r = sll_r;
            3'b010:  alu_r = {31'b0, lt_s};
            3'b011:  alu_r = {31'b0, lt_u};
            3'b100:  alu_r = xor_r;
            3'b101:  alu_r = d_f7[5] ? sra_r : srl_r;
            3'b110:  alu_r = or_r;
            default: alu_r = and_r;                     // 3'b111
        endcase
    end

    // ------------------------------------------------------------------
    // branch / jump resolution
    // ------------------------------------------------------------------
    wire       eq_rs    = (rs1_val == rs2_val);
    wire       lt_rs    = $signed(rs1_val) < $signed(rs2_val);
    wire       ltu_rs   = rs1_val < rs2_val;

    reg        br_taken;
    always @* begin
        case (d_f3)
            3'b000:  br_taken = eq_rs;                  // BEQ
            3'b001:  br_taken = !eq_rs;                 // BNE
            3'b100:  br_taken = lt_rs;                  // BLT
            3'b101:  br_taken = !lt_rs;                 // BGE
            3'b110:  br_taken = ltu_rs;                 // BLTU
            default: br_taken = !ltu_rs;                // BGEU
        endcase
    end

    wire [31:0] pc_next  = pc_q + 32'd4;
    wire [31:0] br_tgt   = pc_q + imm_b;
    wire [31:0] jal_tgt  = pc_q + imm_j;
    wire [31:0] jalr_tgt = (rs1_val + imm_i) & 32'hFFFFFFFE;

    // ------------------------------------------------------------------
    // effective addresses, store lanes, alignment / trap decision
    // ------------------------------------------------------------------
    wire [31:0] ld_ea = rs1_val + imm_i;
    wire [31:0] st_ea = rs1_val + imm_s;

    // misaligned data access (checked before any data request is issued)
    wire ld_mis = (d_f3 == 3'b010) ? (ld_ea[1:0] != 2'b00) :   // LW
                  (d_f3[1:0] == 2'b01) ? ld_ea[0] :            // LH/LHU
                  1'b0;                                        // LB/LBU
    wire st_mis = (d_f3 == 3'b010) ? (st_ea[1:0] != 2'b00) :   // SW
                  (d_f3 == 3'b001) ? st_ea[0] :                // SH
                  1'b0;                                        // SB

    // misaligned control transfer (branch: only when taken)
    wire br_mis  = (br_tgt[1:0]  != 2'b00);
    wire jal_mis = (jal_tgt[1:0] != 2'b00);
    wire jlr_mis = jalr_tgt[1];

    wire trap_insn = ill_insn | op_sys
                   | (op_load  & ld_mis)
                   | (op_store & st_mis)
                   | (op_jal   & jal_mis)
                   | (op_jalr  & jlr_mis)
                   | (op_br    & br_taken & br_mis);

    // next fetch address
    wire [31:0] new_pc = op_jal                  ? jal_tgt  :
                         op_jalr                 ? jalr_tgt :
                         (op_br & br_taken)      ? br_tgt   : pc_next;

    // register writeback at the fetch-completing edge
    wire        wb_en = (op_lui | op_auipc | op_jal | op_jalr | op_imm | op_rr)
                        && (d_rd != 5'd0);
    wire [31:0] wb_val = op_lui   ? imm_u            :
                         op_auipc ? (pc_q + imm_u)   :
                         (op_jal | op_jalr) ? pc_next :
                         alu_r;

    // store lanes / lane-shifted data (latched at the fetch-completing edge)
    wire [3:0]  st_strb = (d_f3 == 3'b000) ? (4'b0001 << st_ea[1:0]) :
                          (d_f3 == 3'b001) ? (st_ea[1] ? 4'b1100 : 4'b0011) :
                          4'b1111;
    wire [31:0] st_word = (d_f3 == 3'b000) ? (rs2_val << {st_ea[1:0], 3'b000}) :
                          (d_f3 == 3'b001) ? (rs2_val << {st_ea[1],   4'b0000}) :
                          rs2_val;

    // ------------------------------------------------------------------
    // load-data extraction (at the data-completing edge)
    // ------------------------------------------------------------------
    wire [4:0]  ld_sh  = (dsize_q[1:0] == 2'b00) ? {daddr_q[1:0], 3'b000} :
                         (dsize_q[1:0] == 2'b01) ? {daddr_q[1],   4'b0000} :
                         5'b00000;
    wire [31:0] ld_raw = mem_rdata >> ld_sh;

    reg [31:0] ld_val;
    always @* begin
        case (dsize_q)
            3'b000:  ld_val = {{24{ld_raw[7]}},  ld_raw[7:0]};   // LB
            3'b001:  ld_val = {{16{ld_raw[15]}}, ld_raw[15:0]};  // LH
            3'b100:  ld_val = {24'b0, ld_raw[7:0]};              // LBU
            3'b101:  ld_val = {16'b0, ld_raw[15:0]};             // LHU
            default: ld_val = ld_raw;                            // LW
        endcase
    end

    // ------------------------------------------------------------------
    // state machine
    // ------------------------------------------------------------------
    always @(posedge clk) begin
        if (!resetn) begin
            state   <= S_FETCH;
            pc_q    <= 32'h00000000;
            trap_q  <= 1'b0;
            dwstrb_q <= 4'h0;
        end else if (!trap_q) begin
            if (fetch_done) begin
                pc_q <= new_pc;
                if (trap_insn) begin
                    trap_q <= 1'b1;
                    state  <= S_TRAP;
                end else if (op_load || op_store) begin
                    daddr_q  <= op_load ? ld_ea : st_ea;
                    dwstrb_q <= op_store ? st_strb : 4'h0;
                    dwdata_q <= st_word;
                    drd_q    <= d_rd;
                    dsize_q  <= d_f3;
                    state    <= S_MEM;
                end else begin
                    state <= S_FETCH;
                    if (wb_en)
                        regs[d_rd] <= wb_val;
                end
            end else if (mem_done) begin
                state <= S_FETCH;
                if ((dwstrb_q == 4'h0) && (drd_q != 5'd0))
                    regs[drd_q] <= ld_val;      // load writeback
            end
        end
    end

    // register file is zeroed at startup; x0 is never written afterwards
    initial begin
        for (i = 0; i < 32; i = i + 1)
            regs[i] = 32'b0;
    end

endmodule
