#!/bin/bash
set -euo pipefail

# Judge toolchain setup for fpga-agent-loop.
# Installs, idempotently, into $HOME/riscv-toolchain:
#   - OSS CAD Suite 2026-09-27 (sha256 per SPEC.md)
#   - xPack riscv-none-elf-gcc 15.2.0-1 (sha256 checked)
#   - riscv-tests @ pinned SHA (+ riscv-test-env submodule @ pinned SHA)
#   - picorv32 @ pinned SHA (reference control for selftest)
#
# Everything comes from pinned release tarballs / pinned git commits —
# no apt packages are required (apt lists may be empty in the sandbox).
#
# Usage:
#   setup.sh                 install/verify toolchain, rebuild tests if missing
#   setup.sh --rebuild-tests regenerate judge/tests/*.hex from source

JUDGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLCHAIN_DIR="$HOME/riscv-toolchain"
OSS_DIR="$TOOLCHAIN_DIR/oss-cad-suite"
GCC_DIR="$TOOLCHAIN_DIR/riscv-none-elf"
TESTS_DIR="$TOOLCHAIN_DIR/riscv-tests"
PICO_DIR="$TOOLCHAIN_DIR/picorv32"
DL="$TOOLCHAIN_DIR/dl"

OSS_VER="2026-09-27"
OSS_URL="https://github.com/YosysHQ/oss-cad-suite-build/releases/download/${OSS_VER}/oss-cad-suite-linux-x64-20260927.tgz"
OSS_SHA256="8af3500957e8a304a9bb67ecbcd1e9a7a8bc6ae0813075cc812bfac6143aed86"

GCC_VER="15.2.0-1"
GCC_URL="https://github.com/xpack-dev-tools/riscv-none-elf-gcc-xpack/releases/download/v${GCC_VER}/xpack-riscv-none-elf-gcc-${GCC_VER}-linux-x64.tar.gz"
GCC_SHA256="aaaa8060c914851a3e5ee1ba82cc3d6f80972f90638a05c6e823a37557a33758"

RT_REPO="https://github.com/riscv-software-src/riscv-tests.git"
RT_SHA="7b68f7b91f827f8d94cc1c57ff123752c5c8f704"
# riscv-test-env is a submodule of riscv-tests; this is the SHA recorded
# for env/ at RT_SHA (from the gitlink).
RTE_REPO="https://github.com/riscv/riscv-test-env.git"
RTE_SHA="6de71edb142be36319e380ce782c3d1830c65d68"

PICO_REPO="https://github.com/YosysHQ/picorv32.git"
PICO_SHA="ef203c2b0a3fb793280f5114941416c425c5b461"

mkdir -p "$TOOLCHAIN_DIR" "$DL"

fetch() {  # url out
    echo "  download: $1"
    curl -L --retry 3 -sS -o "$2" "$1"
}

check_sha() {  # file sha
    local got
    got=$(sha256sum "$1" | cut -d' ' -f1)
    if [ "$got" != "$2" ]; then
        echo "SHA256 MISMATCH for $1" >&2
        echo "  expected: $2" >&2
        echo "  got:      $got" >&2
        return 1
    fi
}

clone_at() {  # repo sha dest
    if [ ! -d "$3/.git" ]; then
        rm -rf "$3"
        git clone -q "$1" "$3"
    fi
    git -C "$3" fetch -q --depth 1 origin "$2" 2>/dev/null || git -C "$3" fetch -q origin
    git -C "$3" checkout -q "$2"
    [ "$(git -C "$3" rev-parse HEAD)" = "$2" ]
}

# ---- OSS CAD Suite ------------------------------------------------------
if [ -f "$OSS_DIR/.ok-$OSS_VER" ]; then
    echo "OSS CAD Suite $OSS_VER: already installed"
else
    echo "Installing OSS CAD Suite $OSS_VER ..."
    fetch "$OSS_URL" "$DL/oss-cad-suite.tgz"
    check_sha "$DL/oss-cad-suite.tgz" "$OSS_SHA256"
    rm -rf "$OSS_DIR.tmp" "$OSS_DIR"
    mkdir -p "$OSS_DIR.tmp"
    tar -xzf "$DL/oss-cad-suite.tgz" -C "$OSS_DIR.tmp" --strip-components=1
    mv "$OSS_DIR.tmp" "$OSS_DIR"
    rm -f "$DL/oss-cad-suite.tgz"
    touch "$OSS_DIR/.ok-$OSS_VER"
fi

# ---- RISC-V GCC ----------------------------------------------------------
if [ -f "$GCC_DIR/.ok-$GCC_VER" ]; then
    echo "riscv-none-elf-gcc $GCC_VER: already installed"
else
    echo "Installing riscv-none-elf-gcc $GCC_VER ..."
    fetch "$GCC_URL" "$DL/xpack-riscv.tgz"
    check_sha "$DL/xpack-riscv.tgz" "$GCC_SHA256"
    rm -rf "$GCC_DIR.tmp" "$GCC_DIR"
    mkdir -p "$GCC_DIR.tmp"
    tar -xzf "$DL/xpack-riscv.tgz" -C "$GCC_DIR.tmp" --strip-components=1
    mv "$GCC_DIR.tmp" "$GCC_DIR"
    rm -f "$DL/xpack-riscv.tgz"
    touch "$GCC_DIR/.ok-$GCC_VER"
fi

# ---- riscv-tests (+ env submodule) ---------------------------------------
if [ -f "$TESTS_DIR/.ok-$RT_SHA" ]; then
    echo "riscv-tests @ $RT_SHA: already installed"
else
    echo "Installing riscv-tests @ $RT_SHA ..."
    clone_at "$RT_REPO" "$RT_SHA" "$TESTS_DIR"
    clone_at "$RTE_REPO" "$RTE_SHA" "$TESTS_DIR/env"
    touch "$TESTS_DIR/.ok-$RT_SHA"
fi

# ---- picorv32 -------------------------------------------------------------
if [ -f "$PICO_DIR/.ok-$PICO_SHA" ]; then
    echo "picorv32 @ $PICO_SHA: already installed"
else
    echo "Installing picorv32 @ $PICO_SHA ..."
    clone_at "$PICO_REPO" "$PICO_SHA" "$PICO_DIR"
    touch "$PICO_DIR/.ok-$PICO_SHA"
fi

# ---- test image rebuild ---------------------------------------------------
# All rv32ui tests except:
#   fence_i.S  - excluded by SPEC.md
#   ma_data.S  - requires a trap-based misaligned-access emulator in the env;
#                cannot run on a bare trapping CPU (deviation, see README)
RV32UI_TESTS=$(ls "$TESTS_DIR/isa/rv32ui"/*.S | xargs -n1 basename | sed 's/\.S$//' \
               | grep -vx -e fence_i -e ma_data | sort)

rebuild_tests() {
    local outdir="$1"
    mkdir -p "$outdir"
    local cc="$GCC_DIR/bin/riscv-none-elf-gcc"
    local objcopy="$GCC_DIR/bin/riscv-none-elf-objcopy"
    local t elf bin hex
    for t in $RV32UI_TESTS; do
        elf="$outdir/$t.elf"; bin="$outdir/$t.bin"; hex="$outdir/$t.hex"
        "$cc" -march=rv32i -mabi=ilp32 -static -mcmodel=medany \
              -nostdlib -nostartfiles -fno-pic \
              -I"$JUDGE_DIR" \
              -I"$TESTS_DIR/isa/macros/scalar" \
              -T"$JUDGE_DIR/link.ld" \
              "$TESTS_DIR/isa/rv32ui/$t.S" -o "$elf"
        "$objcopy" -O binary "$elf" "$bin"
        HEX_OUT="$hex" python3 - "$bin" <<'PY'
import os, sys
sys.path.insert(0, os.environ["JUDGE_DIR_FOR_MEMH"])
from memh import bytes_to_words, words_to_memh
data = open(sys.argv[1], "rb").read()
open(os.environ["HEX_OUT"], "w").write(words_to_memh(bytes_to_words(data)))
PY
        rm -f "$elf" "$bin"
    done
}

if [ "${1:-}" = "--rebuild-tests" ]; then
    echo "Rebuilding test images into $JUDGE_DIR/tests ..."
    JUDGE_DIR_FOR_MEMH="$JUDGE_DIR" rebuild_tests "$JUDGE_DIR/tests"
    echo "  $(ls "$JUDGE_DIR/tests"/*.hex | wc -l) .hex files written"
elif [ ! -f "$JUDGE_DIR/tests/rv32ui-simple.hex" ] && [ ! -f "$JUDGE_DIR/tests/simple.hex" ]; then
    echo "Test images missing; rebuilding into $JUDGE_DIR/tests ..."
    JUDGE_DIR_FOR_MEMH="$JUDGE_DIR" rebuild_tests "$JUDGE_DIR/tests"
    echo "  $(ls "$JUDGE_DIR/tests"/*.hex | wc -l) .hex files written"
else
    echo "Test images present (use --rebuild-tests to regenerate)"
fi

cat <<EOF

Toolchain ready at $TOOLCHAIN_DIR
  oss-cad-suite : $OSS_VER   ($OSS_DIR/bin)
  riscv gcc     : $GCC_VER   ($GCC_DIR/bin)
  riscv-tests   : $RT_SHA
  riscv-test-env: $RTE_SHA
  picorv32      : $PICO_SHA

Add to PATH:  export PATH=$OSS_DIR/bin:$GCC_DIR/bin:\$PATH
EOF
