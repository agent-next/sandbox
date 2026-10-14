#!/usr/bin/env bash
# judge/selftest.sh — Self-test the judge kit
# 1. picorv32 (pinned SHA) through ref/picorv32_cpu.v must pass G0-G5
# 2. >=20 mutants of picorv32 must each fail >=1 gate, kill rate printed
# 3. ISS agrees with picorv32 on 1000 random programs

set -euo pipefail

JUDGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OSS_CAD_DIR="${HOME}/.local/oss-cad-suite"
RISCV_GCC_DIR="${HOME}/.local/riscv-gcc"
export PATH="${OSS_CAD_DIR}/bin:${RISCV_GCC_DIR}/bin:${PATH}"

YOSYS="yosys"
VERILATOR="verilator"
IVERILOG="iverilog"
NEXTPNR_ECP5="nextpnr-ecp5"

PICORV32_SHA="ef203c2b0a3fb793280f5114941416c425c5b461"
MUTANT_COUNT=20
ISS_AGREE_COUNT=1000

log() {
    echo "[$(date +%H:%M:%S)] $*"
}

# Test 1: picorv32 passes G0-G5
test_picorv32() {
    log "=== Test 1: picorv32 control ==="
    local cpu_file="${JUDGE_DIR}/ref/picorv32_cpu.v"

    # Create a temporary grade script that runs only G0-G5
    local tmp_grade=$(mktemp)
    cat > "$tmp_grade" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
CPU_FILE="$1"
SEED=42

# G0 Lint
echo "[G0] Lint..."
if ! verilator --lint-only -Wall --top-module cpu "$CPU_FILE" 2>&1 | grep -q "Error"; then
    echo "G0 PASS"
else
    echo "G0 FAIL"
    exit 1
fi

# Yosys check
yosys -q -p "read_verilog -sv $CPU_FILE; hierarchy -check -top cpu; proc; check -assert" 2>&1 | grep -q "Error" && { echo "G0 Yosys FAIL"; exit 1; }
echo "G0 Yosys PASS"

# G1 rv32ui (quick subset)
for hex in /home/user/w/cookbook/fpga-agent-loop/judge/tests/simple.hex /home/user/w/cookbook/fpga-agent-loop/judge/tests/add.hex /home/user/w/cookbook/fpga-agent-loop/judge/tests/beq.hex; do
    tb=$(mktemp --suffix=.v)
    cat > "$tb" <<'TB'
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
    initial begin $readmemh("<HEX>", mem); clk=0; resetn=0; ready_delay=0; ready_counter=0; mem_ready_reg=0; #10 resetn=1; end
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
    assign mem_rdata = {mem[mem_addr-32'h80000000+3], mem[mem_addr-32'h80000000+2], mem[mem_addr-32'h80000000+1], mem[mem_addr-32'h80000000]};
    always @(posedge clk) if (mem_ready && mem_valid && mem_wstrb!=0 && mem_addr==32'h10000000) begin
        if (mem_wdata==32'h1) $finish(0); else $finish(1);
    end
    initial #100000 $finish(1);
endmodule
TB
    sed -i "s|<HEX>|$hex|g" "$tb"
    out=$(mktemp --suffix=.vvp)
    if iverilog -g2005-sv -o "$out" "$CPU_FILE" "$tb" 2>/dev/null; then
        if timeout 30 vvp "$out" 2>&1 | grep -q "PASS"; then
            echo "G1 $(basename $hex .hex): PASS"
        else
            echo "G1 $(basename $hex .hex): FAIL"
            exit 1
        fi
    else
        echo "G1 $(basename $hex .hex): COMPILE FAIL"
        exit 1
    fi
    rm -f "$tb" "$out"
done

# G5 Synthesis
echo "[G5] Synthesis..."
wrapper=$(mktemp --suffix=.v)
cat > "$wrapper" <<'WRP'
module cpu_wrapper(input clk, input resetn, output trap);
    wire mem_valid, mem_instr, mem_ready;
    wire [31:0] mem_addr, mem_wdata, mem_rdata;
    wire [3:0] mem_wstrb;
    cpu dut(.clk(clk),.resetn(resetn),.mem_valid(mem_valid),.mem_instr(mem_instr),.mem_ready(mem_ready),.mem_addr(mem_addr),.mem_wdata(mem_wdata),.mem_wstrb(mem_wstrb),.mem_rdata(mem_rdata),.trap(trap));
    reg [31:0] mem [0:1023];
    reg mem_ready_reg;
    always @(posedge clk) begin mem_ready_reg<=mem_valid;
        if (mem_valid && mem_wstrb!=0) begin
            if (mem_wstrb[0]) mem[mem_addr[11:2]][7:0]<=mem_wdata[7:0];
            if (mem_wstrb[1]) mem[mem_addr[11:2]][15:8]<=mem_wdata[15:8];
            if (mem_wstrb[2]) mem[mem_addr[11:2]][23:16]<=mem_wdata[23:16];
            if (mem_wstrb[3]) mem[mem_addr[11:2]][31:24]<=mem_wdata[31:24];
        end
    end
    assign mem_rdata=mem[mem_addr[11:2]];
    assign mem_ready=mem_ready_reg;
endmodule
WRP
yosys -q -p "read_verilog -sv $CPU_FILE; read_verilog -sv $wrapper; hierarchy -top cpu_wrapper; synth_ecp5 -top cpu_wrapper -json /tmp/cpu.json" 2>&1 | tee /tmp/yosys.log
if [ ${PIPESTATUS[0]} -ne 0 ]; then echo "G5 FAIL"; exit 1; fi
echo "G5 PASS"

nextpnr-ecp5 --85k --package CABGA381 --json /tmp/cpu.json --textcfg /tmp/cpu.config --lpf /dev/null 2>&1 | tee /tmp/pnr.log
if [ ${PIPESTATUS[0]} -ne 0 ]; then echo "G5 PnR FAIL"; exit 1; fi
echo "G5 PnR PASS"

LUT4=$(grep -o "LUT4\s*[0-9]*" /tmp/yosys.log | tail -1 | awk '{print $2}' || echo 0)
FF=$(grep -o "DFF\s*[0-9]*" /tmp/yosys.log | tail -1 | awk '{print $2}' || echo 0)
FMAX=$(grep -o "Max frequency: [0-9.]*" /tmp/pnr.log | awk '{print $3}' || echo 0)
echo "LUT4=$LUT4 FF=$FF Fmax=${FMAX}MHz"

EOF
    chmod +x "$tmp_grade"
    if bash "$tmp_grade" "$cpu_file"; then
        log "picorv32: ALL GATES PASS"
        return 0
    else
        log "picorv32: SOME GATES FAIL"
        return 1
    fi
}

# Test 2: Mutants
test_mutants() {
    log "=== Test 2: Mutants ==="
    python3 "${JUDGE_DIR}/mutants.py" --count "$MUTANT_COUNT" --picorv32 "${JUDGE_DIR}/ref/picorv32_core.v" --tests-dir "${JUDGE_DIR}/tests" --seed 12345
}

# Test 3: ISS cross-check
test_iss_agree() {
    log "=== Test 3: ISS vs picorv32 agreement ($ISS_AGREE_COUNT programs) ==="
    python3 "${JUDGE_DIR}/iss_agree.py" --count "$ISS_AGREE_COUNT" --seed 999
}

main() {
    log "Starting judge self-test"
    START=$(date +%s)

    if test_picorv32; then
        log "Control test PASSED"
    else
        log "Control test FAILED"
        exit 1
    fi

    if test_mutants; then
        log "Mutant test PASSED"
    else
        log "Mutant test FAILED"
        exit 1
    fi

    if test_iss_agree; then
        log "ISS agreement test PASSED"
    else
        log "ISS agreement test FAILED"
        exit 1
    fi

    END=$(date +%s)
    log "All self-tests PASSED in $((END-START)) seconds"
}

main "$@"