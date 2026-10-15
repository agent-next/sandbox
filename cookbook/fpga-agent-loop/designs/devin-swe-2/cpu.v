// RV32I CPU for the fpga-agent-loop judge (SPEC.md).
//
// Non-pipelined, 3-state core:
//   ST_EXEC  - decode+execute `instr`; combinationally issues the NEXT
//              transaction on the bus: for ALU/branch/jump/FENCE ops that
//              is the fetch of next_pc (so those retire 1 instr/cycle),
//              for loads/stores it is the data access.
//   ST_FETCH - issue the fetch at `pc` (used after reset and after a
//              load/store completes, since the bus was busy with data).
//   ST_HALT  - trap asserted, bus quiet forever.
//
// Cycle cost (0-latency memory): ALU/branch/jump = 1, load/store = 2.
//
// Semantics match judge/iss.py exactly, including: misaligned jump/branch
// target traps at the jump; out-of-range/unaligned fetch traps (out-of-
// range fetches return 0 -> illegal instruction -> trap); loads outside
// RAM read 0 and stores outside RAM are dropped (the tb does that); FENCE
// is a NOP and FENCE.I traps; SLLI accepts funct7 0x00 or 0x01.

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
    output reg         trap
);

    localparam ST_EXEC  = 2'd0;
    localparam ST_FETCH = 2'd1;
    localparam ST_HALT  = 2'd2;

    reg  [ 1:0] state;
    reg  [31:0] pc;      // address of the instr in EXEC / next fetch in FETCH
    reg  [31:0] instr;   // instruction under execution in ST_EXEC
    reg  [31:0] regs [0:31];

    // ------------------------------------------------------------------
    // decode
    // ------------------------------------------------------------------
    wire [6:0] op  = instr[6:0];
    wire [4:0] rd  = instr[11:7];
    wire [2:0] f3  = instr[14:12];
    wire [4:0] rs1 = instr[19:15];
    wire [4:0] rs2 = instr[24:20];
    wire [6:0] f7  = instr[31:25];

    wire [31:0] rs1v = (rs1 == 5'd0) ? 32'd0 : regs[rs1];
    wire [31:0] rs2v = (rs2 == 5'd0) ? 32'd0 : regs[rs2];

    wire [31:0] imm_i = {{20{instr[31]}}, instr[31:20]};
    wire [31:0] imm_s = {{20{instr[31]}}, instr[31:25], instr[11:7]};
    wire [31:0] imm_b = {{19{instr[31]}}, instr[31], instr[7],
                         instr[30:25], instr[11:8], 1'b0};
    wire [31:0] imm_u = {instr[31:12], 12'b0};
    wire [31:0] imm_j = {{11{instr[31]}}, instr[31], instr[19:12],
                         instr[20], instr[30:21], 1'b0};

    wire is_lui    = (op == 7'h37);
    wire is_auipc  = (op == 7'h17);
    wire is_jal    = (op == 7'h6F);
    wire is_jalr   = (op == 7'h67);
    wire is_branch = (op == 7'h63);
    wire is_load   = (op == 7'h03);
    wire is_store  = (op == 7'h23);
    wire is_opimm  = (op == 7'h13);
    wire is_op     = (op == 7'h33);

    // legality of the encoding (SYSTEM/ECALL/EBREAK/CSR and unknown
    // opcodes fall into the default -> illegal -> trap)
    reg dec_illegal;
    always @* begin
        case (op)
            7'h37, 7'h17, 7'h6F:
                dec_illegal = 1'b0;                          // LUI AUIPC JAL
            7'h67:
                dec_illegal = (f3 != 3'h0);                  // JALR
            7'h63:
                dec_illegal = (f3 == 3'h2 || f3 == 3'h3);    // branches
            7'h03:
                dec_illegal = !(f3 == 3'h0 || f3 == 3'h1 || f3 == 3'h2 ||
                                f3 == 3'h4 || f3 == 3'h5);   // loads
            7'h23:
                dec_illegal = (f3 > 3'h2);                   // stores
            7'h13:
                dec_illegal = (f3 == 3'h1 && !(f7 == 7'h00 || f7 == 7'h01)) ||
                              (f3 == 3'h5 && !(f7 == 7'h00 || f7 == 7'h20));
            7'h33:
                dec_illegal = !(f7 == 7'h00 ||
                                (f7 == 7'h20 && (f3 == 3'h0 || f3 == 3'h5)));
            7'h0F:
                dec_illegal = (f3 != 3'h0);                  // FENCE ok, FENCE.I traps
            default:
                dec_illegal = 1'b1;                          // SYSTEM et al.
        endcase
    end

    // ------------------------------------------------------------------
    // execute datapath (all combinational on instr + regs + pc)
    // ------------------------------------------------------------------
    wire [31:0] pc_plus4 = pc + 32'd4;

    // branch condition
    reg br_taken;
    always @* begin
        case (f3)
            3'h0:    br_taken = (rs1v == rs2v);
            3'h1:    br_taken = (rs1v != rs2v);
            3'h4:    br_taken = ($signed(rs1v) <  $signed(rs2v));
            3'h5:    br_taken = ($signed(rs1v) >= $signed(rs2v));
            3'h6:    br_taken = (rs1v <  rs2v);
            3'h7:    br_taken = (rs1v >= rs2v);
            default: br_taken = 1'b0;
        endcase
    end

    // targets
    wire [31:0] br_t   = pc + imm_b;
    wire [31:0] jal_t  = pc + imm_j;
    wire [31:0] jalr_t = (rs1v + imm_i) & 32'hFFFF_FFFE;
    wire [31:0] jump_t = is_jalr ? jalr_t : (is_jal ? jal_t : br_t);
    wire        jump_req = is_jal || is_jalr || (is_branch && br_taken);
    wire        jump_mis = jump_req && jump_t[1];

    wire [31:0] next_pc = jump_req ? jump_t : pc_plus4;

    // load/store address and byte strobes
    wire [31:0] ls_addr  = rs1v + (is_store ? imm_s : imm_i);
    wire        load_mis = is_load && (((f3 == 3'h2) && (ls_addr[1:0] != 2'b00)) ||
                                      ((f3 == 3'h1 || f3 == 3'h5) && ls_addr[0]));
    wire        store_mis = is_store && (((f3 == 3'h2) && (ls_addr[1:0] != 2'b00)) ||
                                        ((f3 == 3'h1) && ls_addr[0]));

    wire [3:0]  st_wstrb = (f3 == 3'h0) ? (4'b0001 << ls_addr[1:0]) :
                           (f3 == 3'h1) ? (4'b0011 << ls_addr[1:0]) :
                                          4'b1111;
    wire [31:0] st_wdata = (f3 == 3'h0) ? {4{rs2v[7:0]}}  :
                           (f3 == 3'h1) ? {2{rs2v[15:0]}} : rs2v;

    // trap this instruction (in EXEC): illegal encoding or misalignment
    wire exec_trap = dec_illegal || jump_mis || load_mis || store_mis;

    // shared ALU for OP / OP-IMM
    wire [31:0] alu_b = is_opimm ? imm_i : rs2v;
    wire [4:0]  shamt = is_opimm ? rs2 : rs2v[4:0];
    reg  [31:0] alu_r;
    always @* begin
        case (f3)
            3'h0:    alu_r = (is_op && f7[5]) ? rs1v - alu_b : rs1v + alu_b;
            3'h1:    alu_r = rs1v << shamt;
            3'h2:    alu_r = {31'b0, $signed(rs1v) < $signed(alu_b)};
            3'h3:    alu_r = {31'b0, rs1v < alu_b};
            3'h4:    alu_r = rs1v ^ alu_b;
            3'h5:    alu_r = f7[5] ? $signed(rs1v) >>> shamt : rs1v >> shamt;
            3'h6:    alu_r = rs1v | alu_b;
            default: alu_r = rs1v & alu_b;
        endcase
    end

    // register writeback for non-load instructions
    wire        wb_en = (rd != 5'd0) &&
                        (is_lui || is_auipc || is_jal || is_jalr ||
                         is_opimm || is_op);
    wire [31:0] wb_data = is_lui            ? imm_u     :
                          is_auipc          ? pc + imm_u :
                          (is_jal | is_jalr) ? pc_plus4  : alu_r;

    // load data extraction (valid in the mem_ready cycle)
    wire [31:0] ld_sh   = mem_rdata >> {ls_addr[1:0], 3'b000};
    wire [31:0] ld_data = (f3 == 3'h0) ? {{24{ld_sh[7]}},  ld_sh[7:0]}  :
                          (f3 == 3'h4) ? { 24'b0,          ld_sh[7:0]}  :
                          (f3 == 3'h1) ? {{16{ld_sh[15]}}, ld_sh[15:0]} :
                          (f3 == 3'h5) ? { 16'b0,          ld_sh[15:0]} :
                                         mem_rdata;

    // ------------------------------------------------------------------
    // bus interface (combinational; a request holds stable until ready)
    // ------------------------------------------------------------------
    assign mem_valid = (state == ST_FETCH) ||
                       (state == ST_EXEC && !exec_trap);
    assign mem_instr = (state == ST_FETCH) ||
                       (state == ST_EXEC && !is_load && !is_store);
    assign mem_addr  = (state == ST_FETCH)              ? pc      :
                       (is_load || is_store)            ? ls_addr : next_pc;
    assign mem_wstrb = (state == ST_EXEC && is_store && !exec_trap) ? st_wstrb
                                                                  : 4'b0000;
    assign mem_wdata = st_wdata;

    // ------------------------------------------------------------------
    // sequential
    // ------------------------------------------------------------------
    always @(posedge clk) begin
        if (!resetn) begin
            state <= ST_FETCH;
            pc    <= 32'd0;
            instr <= 32'd0;
            trap  <= 1'b0;
        end else begin
            case (state)
                ST_FETCH: begin
                    if (mem_valid && mem_ready) begin
                        instr <= mem_rdata;
                        state <= ST_EXEC;
                    end
                end

                ST_EXEC: begin
                    if (exec_trap) begin
                        trap  <= 1'b1;
                        state <= ST_HALT;
                    end else if (mem_ready) begin
                        if (is_load) begin
                            if (rd != 5'd0) regs[rd] <= ld_data;
                            pc    <= pc_plus4;
                            state <= ST_FETCH;
                        end else if (is_store) begin
                            pc    <= pc_plus4;
                            state <= ST_FETCH;
                        end else begin
                            // fetch of next_pc completed with this instr
                            instr <= mem_rdata;
                            pc    <= next_pc;
                            if (wb_en) regs[rd] <= wb_data;
                        end
                    end
                end

                ST_HALT: begin
                    state <= ST_HALT;   // halt forever
                end

                default: state <= ST_FETCH;
            endcase
        end
    end

endmodule

`default_nettype wire
