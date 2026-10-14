#!/usr/bin/env bash
# judge/setup.sh — install pinned toolchain idempotently into $HOME
# OSS CAD Suite 2026-09-27, RISC-V GCC for rv32i/ilp32, riscv-tests pinned SHA

set -euo pipefail

# Pinned versions and checksums
OSS_CAD_SUITE_VERSION="2026-09-27"
OSS_CAD_SUITE_SHA256="8af3500957e8a304a9bb67ecbcd1e9a7a8bc6ae0813075cc812bfac6143aed86"
OSS_CAD_SUITE_URL="https://github.com/YosysHQ/oss-cad-suite-build/releases/download/${OSS_CAD_SUITE_VERSION}/oss-cad-suite-linux-x64-${OSS_CAD_SUITE_VERSION//-}.tgz"

# xPack RISC-V GCC - pinned to exact version (rv32i/ilp32 support)
RISCV_GCC_VERSION="14.2.0-2"
RISCV_GCC_SHA256="0ab93937aab882c3a69f63eff4fe8fc6e360e4a23776004fa116ad692e699d23"
RISCV_GCC_URL="https://github.com/xpack-dev-tools/riscv-none-elf-gcc-xpack/releases/download/v${RISCV_GCC_VERSION}/xpack-riscv-none-elf-gcc-${RISCV_GCC_VERSION}-linux-x64.tar.gz"

# riscv-tests pinned SHA (only rv32ui sources needed)
RISCV_TESTS_SHA="7b68f7b91f827f8d94cc1c57ff123752c5c8f704"  # 2026-10-09
RISCV_TESTS_SHA256="c6fa241a06b756f73df66c2a23dd3fb25d2177a6744fa9cc523cff26fd538aae"
RISCV_TESTS_URL="https://github.com/riscv-software-src/riscv-tests/archive/${RISCV_TESTS_SHA}.tar.gz"

# Installation paths
INSTALL_DIR="${HOME}/.local"
OSS_CAD_DIR="${INSTALL_DIR}/oss-cad-suite"
RISCV_GCC_DIR="${INSTALL_DIR}/riscv-gcc"
RISCV_TESTS_DIR="${INSTALL_DIR}/riscv-tests"

# Judge directories
JUDGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TESTS_DIR="${JUDGE_DIR}/tests"
REF_DIR="${JUDGE_DIR}/ref"

# Flags
REBUILD_TESTS=false
FORCE=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [--rebuild-tests] [--force]
  --rebuild-tests   Regenerate .hex test files from riscv-tests sources
  --force           Force re-download and re-install everything
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --rebuild-tests) REBUILD_TESTS=true ;;
        --force) FORCE=true ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1"; usage; exit 1 ;;
    esac
    shift
done

# Helper: verify sha256
verify_sha256() {
    local file="$1"
    local expected="$2"
    local actual
    actual=$(sha256sum "$file" | awk '{print $1}')
    if [[ "$actual" != "$expected" ]]; then
        echo "ERROR: sha256 mismatch for $file"
        echo "  expected: $expected"
        echo "  actual:   $actual"
        return 1
    fi
}

# Helper: download with retries
download() {
    local url="$1"
    local output="$2"
    curl -L --retry 3 --retry-delay 2 -o "$output" "$url"
}

# Install OSS CAD Suite
install_oss_cad_suite() {
    if [[ -d "$OSS_CAD_DIR" && "$FORCE" != "true" ]]; then
        echo "OSS CAD Suite already installed at $OSS_CAD_DIR"
        return 0
    fi

    echo "Installing OSS CAD Suite ${OSS_CAD_SUITE_VERSION}..."
    local tmpdir
    tmpdir=$(mktemp -d)
    local tarball="${tmpdir}/oss-cad-suite.tgz"

    download "$OSS_CAD_SUITE_URL" "$tarball"
    verify_sha256 "$tarball" "$OSS_CAD_SUITE_SHA256"

    rm -rf "$OSS_CAD_DIR"
    mkdir -p "$INSTALL_DIR"
    tar -xzf "$tarball" -C "$INSTALL_DIR"
    # The tarball extracts directly to 'oss-cad-suite' directory
    if [[ -d "${INSTALL_DIR}/oss-cad-suite" && "${INSTALL_DIR}/oss-cad-suite" != "$OSS_CAD_DIR" ]]; then
        mv "${INSTALL_DIR}/oss-cad-suite" "$OSS_CAD_DIR"
    fi

    rm -rf "$tmpdir"
    echo "OSS CAD Suite installed to $OSS_CAD_DIR"
}

# Install RISC-V GCC
install_riscv_gcc() {
    if [[ -d "$RISCV_GCC_DIR" && "$FORCE" != "true" ]]; then
        echo "RISC-V GCC already installed at $RISCV_GCC_DIR"
        return 0
    fi

    echo "Installing RISC-V GCC ${RISCV_GCC_VERSION}..."
    local tmpdir
    tmpdir=$(mktemp -d)
    local tarball="${tmpdir}/riscv-gcc.tar.gz"

    download "$RISCV_GCC_URL" "$tarball"
    verify_sha256 "$tarball" "$RISCV_GCC_SHA256"

    rm -rf "$RISCV_GCC_DIR"
    mkdir -p "$INSTALL_DIR"
    tar -xzf "$tarball" -C "$INSTALL_DIR"
    # xPack extracts to a versioned directory, rename it
    local extracted
    extracted=$(find "$INSTALL_DIR" -maxdepth 1 -type d -name 'xpack-riscv-none-elf-gcc-*')
    if [[ -n "$extracted" && -d "$extracted" ]]; then
        mv "$extracted" "$RISCV_GCC_DIR"
    fi

    rm -rf "$tmpdir"
    echo "RISC-V GCC installed to $RISCV_GCC_DIR"
}

# Install riscv-tests (sources only)
install_riscv_tests() {
    if [[ -d "$RISCV_TESTS_DIR" && "$FORCE" != "true" ]]; then
        echo "riscv-tests already installed at $RISCV_TESTS_DIR"
        return 0
    fi

    echo "Installing riscv-tests @ ${RISCV_TESTS_SHA}..."
    local tmpdir
    tmpdir=$(mktemp -d)
    local tarball="${tmpdir}/riscv-tests.tar.gz"

    download "$RISCV_TESTS_URL" "$tarball"
    verify_sha256 "$tarball" "$RISCV_TESTS_SHA256"

    rm -rf "$RISCV_TESTS_DIR"
    mkdir -p "$INSTALL_DIR"
    tar -xzf "$tarball" -C "$INSTALL_DIR"
    local extracted
    extracted=$(find "$INSTALL_DIR" -maxdepth 1 -type d -name 'riscv-tests-*')
    if [[ -n "$extracted" && -d "$extracted" ]]; then
        mv "$extracted" "$RISCV_TESTS_DIR"
    fi

    rm -rf "$tmpdir"
    echo "riscv-tests installed to $RISCV_TESTS_DIR"
}

# Build rv32ui tests and generate .hex files
build_tests() {
    echo "Building rv32ui tests..."

    # Ensure toolchain is in PATH
    export PATH="${OSS_CAD_DIR}/bin:${RISCV_GCC_DIR}/bin:${PATH}"

    # Verify tools exist
    command -v riscv-none-elf-gcc >/dev/null 2>&1 || { echo "riscv-none-elf-gcc not found in PATH"; exit 1; }
    command -v riscv-none-elf-objcopy >/dev/null 2>&1 || { echo "riscv-none-elf-objcopy not found in PATH"; exit 1; }

    # Create no-CSR riscv_test.h in env/p (used by tests)
    mkdir -p "${RISCV_TESTS_DIR}/env/p"
    cat > "${RISCV_TESTS_DIR}/env/p/riscv_test.h" <<'EOF'
/*
 * No-CSR riscv_test.h for rv32ui tests
 * PASS stores 1 to tohost (0x10000000)
 * FAIL stores (testnum<<1)|1 to tohost
 */
#ifndef RISCV_TEST_H
#define RISCV_TEST_H

#define RVMODEL_HALT() \
    .pushsection .tohost, "aw", @progbits; \
    .word 0; \
    .popsection; \
    .pushsection .text; \
    la x11, tohost; \
    li x10, 1; \
    sw x10, 0(x11); \
    .popsection

#define RVMODEL_PASS() \
    .pushsection .tohost, "aw", @progbits; \
    .word 0; \
    .popsection; \
    .pushsection .text; \
    la x11, tohost; \
    li x10, 1; \
    sw x10, 0(x11); \
    .popsection

#define RVMODEL_FAIL(testnum) \
    .pushsection .tohost, "aw", @progbits; \
    .word 0; \
    .popsection; \
    .pushsection .text; \
    la x11, tohost; \
    slli x10, testnum, 1; \
    ori x10, x10, 1; \
    sw x10, 0(x11); \
    .popsection

#define RVMODEL_BOOT \
    .pushsection .tohost, "aw", @progbits; \
    .word 0; \
    .popsection; \
    .pushsection .text; \
    la x11, tohost; \
    .popsection

#define RVMODEL_DATA_SECTION .data

#define RVMODEL_IO_WRITE(_addr, _val) \
    .pushsection .text; \
    sw _val, 0(_addr); \
    .popsection

#define RVMODEL_IO_READ(_addr) \
    ({ unsigned long _v; .pushsection .text; lw _v, 0(_addr); .popsection; _v; })

#define RVMODEL_SET_MSW_INT() do {} while(0)
#define RVMODEL_CLEAR_MSW_INT() do {} while(0)

#define RVTEST_RV32U
#define RVTEST_CODE_BEGIN \
    .text; \
    .global _start; \
    _start: \
    RVMODEL_BOOT

#define RVTEST_CODE_END \
    RVMODEL_HALT()

#define RVTEST_DATA_BEGIN \
    .data

#define RVTEST_DATA_END

#define RVTEST_PASS RVMODEL_PASS()
#define RVTEST_FAIL RVMODEL_FAIL(TESTNUM)

#define TESTNUM x5

#define TEST_CASE(testnum, testreg, correctval, code...) \
test_ ## testnum: \
    li TESTNUM, testnum; \
    code; \
    li x7, correctval; \
    bne testreg, x7, fail;

#define TEST_PASSFAIL \
        bne x0, TESTNUM, pass; \
fail: \
        RVTEST_FAIL; \
pass: \
        RVTEST_PASS

#define TEST_DATA

#define LOAD_PTR lw
#define STORE_PTR sw
#define MASK_XLEN(x) ((x) & 0xFFFFFFFF)

#define TEST_INSERT_NOPS_0
#define TEST_INSERT_NOPS_1  nop; TEST_INSERT_NOPS_0
#define TEST_INSERT_NOPS_2  nop; TEST_INSERT_NOPS_1
#define TEST_INSERT_NOPS_3  nop; TEST_INSERT_NOPS_2
#define TEST_INSERT_NOPS_4  nop; TEST_INSERT_NOPS_3
#define TEST_INSERT_NOPS_5  nop; TEST_INSERT_NOPS_4
#define TEST_INSERT_NOPS_6  nop; TEST_INSERT_NOPS_5
#define TEST_INSERT_NOPS_7  nop; TEST_INSERT_NOPS_6
#define TEST_INSERT_NOPS_8  nop; TEST_INSERT_NOPS_7
#define TEST_INSERT_NOPS_9  nop; TEST_INSERT_NOPS_8
#define TEST_INSERT_NOPS_10 nop; TEST_INSERT_NOPS_9

#define SEXT_IMM(x) ((x) | (-(((x) >> 11) & 1) << 11))

#define TEST_IMM_OP( testnum, inst, result, val1, imm ) \
    TEST_CASE( testnum, x14, result, \
      li  x13, MASK_XLEN(val1); \
      inst x14, x13, SEXT_IMM(imm); \
    )

#define TEST_IMM_SRC1_EQ_DEST( testnum, inst, result, val1, imm ) \
    TEST_CASE( testnum, x11, result, \
      li  x11, MASK_XLEN(val1); \
      inst x11, x11, SEXT_IMM(imm); \
    )

#define TEST_IMM_DEST_BYPASS( testnum, nop_cycles, inst, result, val1, imm ) \
    TEST_CASE( testnum, x6, result, \
      li  x4, 0; \
1:    li  x1, MASK_XLEN(val1); \
      inst x14, x1, SEXT_IMM(imm); \
      TEST_INSERT_NOPS_ ## nop_cycles \
      addi  x6, x14, 0; \
      addi  x4, x4, 1; \
      li  x5, 2; \
      bne x4, x5, 1b \
    )

#define TEST_IMM_SRC1_BYPASS( testnum, nop_cycles, inst, result, val1, imm ) \
    TEST_CASE( testnum, x14, result, \
      li  x4, 0; \
1:    li  x1, MASK_XLEN(val1); \
      TEST_INSERT_NOPS_ ## nop_cycles \
      inst x14, x1, SEXT_IMM(imm); \
      addi  x4, x4, 1; \
      li  x5, 2; \
      bne x4, x5, 1b \
    )

#define TEST_IMM_ZEROSRC1( testnum, inst, result, imm ) \
    TEST_CASE( testnum, x1, result, \
      inst x1, x0, SEXT_IMM(imm); \
    )

#define TEST_IMM_ZERODEST( testnum, inst, val1, imm ) \
    TEST_CASE( testnum, x0, 0, \
      li  x1, MASK_XLEN(val1); \
      inst x0, x1, SEXT_IMM(imm); \
    )

#define TEST_R_OP( testnum, inst, result, val1 ) \
    TEST_CASE( testnum, x14, result, \
      li  x1, val1; \
      inst x14, x1; \
    )

#define TEST_R_SRC1_EQ_DEST( testnum, inst, result, val1 ) \
    TEST_CASE( testnum, x1, result, \
      li  x1, val1; \
      inst x1, x1; \
    )

#define TEST_R_DEST_BYPASS( testnum, nop_cycles, inst, result, val1 ) \
    TEST_CASE( testnum, x6, result, \
      li  x4, 0; \
1:    li  x1, val1; \
      inst x14, x1; \
      TEST_INSERT_NOPS_ ## nop_cycles \
      addi  x6, x14, 0; \
      addi  x4, x4, 1; \
      li  x5, 2; \
      bne x4, x5, 1b \
    )

#define TEST_RR_OP( testnum, inst, result, val1, val2 ) \
    TEST_CASE( testnum, x14, result, \
      li  x11, MASK_XLEN(val1); \
      li  x12, MASK_XLEN(val2); \
      inst x14, x11, x12; \
    )

#define TEST_RR_SRC1_EQ_DEST( testnum, inst, result, val1, val2 ) \
    TEST_CASE( testnum, x11, result, \
      li  x11, MASK_XLEN(val1); \
      li  x12, MASK_XLEN(val2); \
      inst x11, x11, x12; \
    )

#define TEST_RR_SRC2_EQ_DEST( testnum, inst, result, val1, val2 ) \
    TEST_CASE( testnum, x12, result, \
      li  x11, MASK_XLEN(val1); \
      li  x12, MASK_XLEN(val2); \
      inst x12, x11, x12; \
    )

#define TEST_RR_SRC12_EQ_DEST( testnum, inst, result, val1 ) \
    TEST_CASE( testnum, x11, result, \
      li  x11, MASK_XLEN(val1); \
      inst x11, x11, x11; \
    )

#define TEST_RR_DEST_BYPASS( testnum, nop_cycles, inst, result, val1, val2 ) \
    TEST_CASE( testnum, x6, result, \
      li  x4, 0; \
1:    li  x1, MASK_XLEN(val1); \
      li  x2, MASK_XLEN(val2); \
      inst x14, x1, x2; \
      TEST_INSERT_NOPS_ ## nop_cycles \
      addi  x6, x14, 0; \
      addi  x4, x4, 1; \
      li  x5, 2; \
      bne x4, x5, 1b \
    )

#define TEST_RR_SRC12_BYPASS( testnum, src1_nops, src2_nops, inst, result, val1, val2 ) \
    TEST_CASE( testnum, x14, result, \
      li  x4, 0; \
1:    li  x1, MASK_XLEN(val1); \
      TEST_INSERT_NOPS_ ## src1_nops \
      li  x2, MASK_XLEN(val2); \
      TEST_INSERT_NOPS_ ## src2_nops \
      inst x14, x1, x2; \
      addi  x4, x4, 1; \
      li  x5, 2; \
      bne x4, x5, 1b \
    )

#define TEST_RR_SRC21_BYPASS( testnum, src1_nops, src2_nops, inst, result, val1, val2 ) \
    TEST_CASE( testnum, x14, result, \
      li  x4, 0; \
1:    li  x2, MASK_XLEN(val2); \
      TEST_INSERT_NOPS_ ## src1_nops \
      li  x1, MASK_XLEN(val1); \
      TEST_INSERT_NOPS_ ## src2_nops \
      inst x14, x1, x2; \
      addi  x4, x4, 1; \
      li  x5, 2; \
      bne x4, x5, 1b \
    )

#define TEST_RR_ZEROSRC1( testnum, inst, result, val ) \
    TEST_CASE( testnum, x2, result, \
      li x1, MASK_XLEN(val); \
      inst x2, x0, x1; \
    )

#define TEST_RR_ZEROSRC2( testnum, inst, result, val ) \
    TEST_CASE( testnum, x2, result, \
      li x1, MASK_XLEN(val); \
      inst x2, x1, x0; \
    )

#define TEST_RR_ZEROSRC12( testnum, inst, result ) \
    TEST_CASE( testnum, x1, result, \
      inst x1, x0, x0; \
    )

#define TEST_RR_ZERODEST( testnum, inst, val1, val2 ) \
    TEST_CASE( testnum, x0, 0, \
      li x1, MASK_XLEN(val1); \
      li x2, MASK_XLEN(val2); \
      inst x0, x1, x2; \
    )

#define TEST_LD_OP( testnum, inst, result, offset, base ) \
    TEST_CASE( testnum, x14, result, \
      li  x15, result; \
      la  x2, base; \
      inst x14, offset(x2); \
    )

#define TEST_ST_OP( testnum, load_inst, store_inst, result, offset, base ) \
    TEST_CASE( testnum, x14, result, \
      la  x2, base; \
      li  x1, result; \
      la  x15, 7f; \
      store_inst x1, offset(x2); \
      load_inst x14, offset(x2); \
      j 8f; \
7:    \
      mv x14, x1; \
8:    \
    )

#define TEST_BR2_OP_TAKEN(testnum, inst, val1, val2 ) \
test_ ## testnum: \
    li  TESTNUM, testnum; \
    li  x1, val1; \
    li  x2, val2; \
    inst x1, x2, 2f; \
    bne x0, TESTNUM, fail; \
1:  bne x0, TESTNUM, 3f; \
2:  inst x1, x2, 1b; \
    bne x0, TESTNUM, fail; \
3:

#define TEST_BR2_OP_NOTTAKEN( testnum, inst, val1, val2 ) \
test_ ## testnum: \
    li  TESTNUM, testnum; \
    li  x1, val1; \
    li  x2, val2; \
    inst x1, x2, 1f; \
    bne x0, TESTNUM, 2f; \
1:  bne x0, TESTNUM, fail; \
2:  inst x1, x2, 1b; \
3:

#define TEST_JR_SRC1_BYPASS( testnum, nop_cycles, inst ) \
test_ ## testnum: \
    li  TESTNUM, testnum; \
    li  x4, 0; \
1:  la  x6, 2f; \
    TEST_INSERT_NOPS_ ## nop_cycles \
    inst x6; \
    bne x0, TESTNUM, fail; \
2:  addi  x4, x4, 1; \
    li  x5, 2; \
    bne x4, x5, 1b

#define TEST_JALR_SRC1_BYPASS( testnum, nop_cycles, inst ) \
test_ ## testnum: \
    li  TESTNUM, testnum; \
    li  x4, 0; \
1:  la  x6, 2f; \
    TEST_INSERT_NOPS_ ## nop_cycles \
    inst x13, x6, 0; \
    bne x0, TESTNUM, fail; \
2:  addi  x4, x4, 1; \
    li  x5, 2; \
    bne x4, x5, 1b

#endif /* RISCV_TEST_H */
EOF

    # Create link.ld
    cat > "${RISCV_TESTS_DIR}/env/p/link.ld" <<'EOF'
OUTPUT_FORMAT("elf32-littleriscv")
OUTPUT_ARCH(riscv)
ENTRY(_start)

SECTIONS
{
    . = 0x80000000;
    .text.init : { *(.text.init) }
    .text : { *(.text) }
    .data : { *(.data*) }
    .bss : { *(.bss*) }
    .tohost : { *(.tohost) }
    tohost = .;
}
EOF

    # Ensure macros/scalar exists
    mkdir -p "${RISCV_TESTS_DIR}/macros/scalar"
    cp "${RISCV_TESTS_DIR}/isa/macros/scalar/test_macros.h" "${RISCV_TESTS_DIR}/macros/scalar/" 2>/dev/null || true

    # Also copy to judge/ref for reference
    mkdir -p "$REF_DIR"
    cp "${RISCV_TESTS_DIR}/env/p/riscv_test.h" "${REF_DIR}/riscv_test.h"

    # Build rv32ui tests - compile each test individually with rv32i
    cd "${RISCV_TESTS_DIR}/isa"
    make clean 2>/dev/null || true

    # Build rv32ui tests with rv32i only (not rv32g)
    for test in simple add andi and auipc beq bge bgeu blt bltu bne jal jalr lb lbu lh lhu lw lui or ori sb sh sll slli slt slti sltiu sltu sra srai srl srli sub sw xor xori; do
        echo "Building rv32ui-p-${test}..."
        riscv-none-elf-gcc -march=rv32i -mabi=ilp32 -static -mcmodel=medany -fvisibility=hidden -nostdlib -nostartfiles \
            -I./../env/p -I./macros/scalar -T./../env/p/link.ld \
            rv32ui/${test}.S -o rv32ui-p-${test} 2>/dev/null || echo "Failed to build ${test}"
    done

    # Convert to .hex files
    mkdir -p "$TESTS_DIR"
    for elf in rv32ui-p-*; do
        if [[ -f "$elf" && ! "$elf" =~ \. ]]; then
            local testname="${elf#rv32ui-p-}"
            # Generate raw verilog hex (with @address directives)
            riscv-none-elf-objcopy -O verilog "$elf" "${TESTS_DIR}/${testname}.hex" 2>/dev/null || true
            # Generate sim-friendly hex without @address directives
            # Text section at 0x80000000 -> array index 0
            # ToHost at 0x10000000 -> array index 65536
            # We'll create a pre-processed version for simulation
            # Using objcopy binary then converting
            riscv-none-elf-objcopy -O binary "$elf" "${TESTS_DIR}/${testname}.bin" 2>/dev/null || true
            if [[ -f "${TESTS_DIR}/${testname}.bin" ]]; then
                # Convert binary to hex words, 64KB text + 4 bytes tohost
                xxd -p -c 4 "${TESTS_DIR}/${testname}.bin" 2>/dev/null | head -16385 > "${TESTS_DIR}/${testname}_sim.hex" || true
            fi
        fi
    done

    echo "Generated .hex files in $TESTS_DIR:"
    ls -1 "$TESTS_DIR"/*.hex 2>/dev/null | head -20
}

# Verify tool versions
verify_tools() {
    export PATH="${OSS_CAD_DIR}/bin:${RISCV_GCC_DIR}/bin:${PATH}"

    echo "=== Tool versions ==="
    echo "yosys: $(yosys -V 2>&1 | head -1)"
    echo "nextpnr-ecp5: $(nextpnr-ecp5 --version 2>&1 | head -1)"
    echo "verilator: $(verilator --version 2>&1 | head -1)"
    echo "iverilog: $(iverilog -V 2>&1 | head -1)"
    echo "riscv-none-elf-gcc: $(riscv-none-elf-gcc --version 2>&1 | head -1)"
}

# Main
main() {
    echo "=== Judge setup started ==="
    local start_time
    start_time=$(date +%s)

    install_oss_cad_suite
    install_riscv_gcc
    install_riscv_tests

    if [[ "$REBUILD_TESTS" == "true" ]]; then
        build_tests
    fi

    verify_tools

    local end_time
    end_time=$(date +%s)
    echo "=== Judge setup completed in $((end_time - start_time)) seconds ==="
}

main "$@"