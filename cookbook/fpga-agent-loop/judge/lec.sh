#!/bin/bash
set -euo pipefail

# lec.sh - yosys LEC for the judge self-test (SPEC.md "Known-bad controls").
#
# Usage: lec.sh <gate_picorv32_dir> [gold_picorv32_dir]
#
# Compares the wrapped SPEC-interface CPU (ref/picorv32_cpu.v) when its
# `include "picorv32.v"` resolves to the gold copy vs the mutant copy.
# Prints "LEC: EQUIVALENT" / "LEC: NOT EQUIVALENT" and exits 0/1 (2 = error).
#
# Recipe (SPEC.md): miter -equiv -make_outputs gold gate miter +
# sat -verify -prove trigger 0 after techmap -autoproc -map +/ecp5/cells_sim.v.
#
# Sequential-legal additions needed for that recipe to run at all on a
# sequential design (verified live: identical netlists prove, a known-bad
# mutant fails):
#   prep -flatten + memory_map + async2sync   (no $mem_v2/$adff for sat)
#   miter -flatten                          (sat needs leaf cells)
#   -seq 24 -set-init-zero -set-at {1..3} in_resetn 0
#     (unroll 24 cycles; both sides start at all-zero state and take the
#      same 3-cycle reset, after which the DUT executes free inputs.
#      Without this, miter leaves the two sides' FF init states free and
#      even identical circuits report NOT equivalent; with all-zero init
#      and no reset pulse cpu_state=0 is a dead state and everything
#      vacuously proves.)

JUDGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLCHAIN="$HOME/riscv-toolchain"
export PATH="$TOOLCHAIN/oss-cad-suite/bin:$PATH"
GOLD_DIR="${2:-$TOOLCHAIN/picorv32}"
GATE_DIR="$1"

if [[ ! -f "$GOLD_DIR/picorv32.v" || ! -f "$GATE_DIR/picorv32.v" ]]; then
    echo "LEC: ERROR - picorv32.v not found in gold/gate dir" >&2
    exit 2
fi
if [[ ! -x "$(command -v yosys || true)" ]]; then
    echo "LEC: ERROR - yosys not on PATH (run setup.sh)" >&2
    exit 2
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/lec.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

emit_side() {  # picorv32_dir rtlil_name -> writes <name>.il in $WORK
    yosys -qq -p "read_verilog -I$1 $JUDGE_DIR/ref/picorv32_cpu.v;
                  prep -top cpu -flatten; memory_map; async2sync; opt;
                  rename cpu $2; write_rtlil $WORK/$2.il"
}

if ! emit_side "$GOLD_DIR" gold || ! emit_side "$GATE_DIR" gate; then
    echo "LEC: ERROR - failed to elaborate a side" >&2
    exit 2
fi

LEC_LOG="$WORK/lec.log"
if yosys -p "read_rtlil $WORK/gold.il; read_rtlil $WORK/gate.il;
             miter -equiv -make_outputs -flatten gold gate miter;
             techmap -autoproc -map +/ecp5/cells_sim.v;
             sat -verify -seq 24 -set-init-zero \
                 -set-at 1 in_resetn 0 -set-at 2 in_resetn 0 \
                 -set-at 3 in_resetn 0 -prove trigger 0 -show-inputs miter" \
        >"$LEC_LOG" 2>&1; then
    echo "LEC: EQUIVALENT (sat -verify -prove trigger 0 held over 24 cycles)"
    exit 0
else
    if grep -q "proof did fail" "$LEC_LOG"; then
        echo "LEC: NOT EQUIVALENT (sat found trigger=1 model)"
        exit 1
    fi
    echo "LEC: ERROR - sat did not run to a verdict:" >&2
    tail -5 "$LEC_LOG" >&2
    exit 2
fi
