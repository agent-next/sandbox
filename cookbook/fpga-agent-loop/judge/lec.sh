#!/bin/bash
set -euo pipefail

# lec.sh - yosys LEC for the judge self-test (SPEC.md "Known-bad controls").
#
# Usage: lec.sh <mutant_picorv32_dir> [gold_picorv32_dir]
#
# Compares the wrapped SPEC-interface CPU (ref/picorv32_cpu.v) when its
# `include "picorv32.v"` resolves to the gold copy vs the mutant copy.
# Prints "LEC: EQUIVALENT" / "LEC: NOT EQUIVALENT" / "LEC: UNPROVEN (timeout)"
# and exits 0/1/3 (2 = tool error).
#
# Two soundness mechanisms, both time-bounded (a LEC run must never hang the
# self-test; a timeout is recorded as UNPROVEN, never as equivalent):
#
#   1. Netlist identity (fast path, exits in <1 min): elaborate both sides
#      with the same yosys transform pipeline (prep -flatten + memory_map +
#      async2sync + opt) and compare the resulting RTLIL netlists modulo
#      source-path attributes and yosys's auto-generated cell names. If the
#      optimized netlists are identical, the two designs are structurally
#      the same circuit - a strictly stronger claim than any bounded SAT
#      proof (it holds over all input sequences and unbounded time).
#      Sufficient by itself for mutants whose edit touches logic that the
#      wrapper's parameter set renders unobservable (e.g. ebreak-uncaught:
#      instr_ecall_ebreak has no remaining fanout with WITH_PCPI=0,
#      ENABLE_IRQ=0, CATCH_ILLINSN=1 - yosys optimizes the signal away on
#      BOTH sides, which is exactly what the identity check shows).
#
#   2. SPEC recipe (bounded sequential SAT): miter -equiv -make_outputs +
#      sat -verify -prove trigger 0 after techmap -autoproc
#      -map +/ecp5/cells_sim.v. Sequential-legal additions needed for the
#      recipe to run at all on a sequential design (verified live: identical
#      netlists prove, a known-bad mutant fails):
#        prep -flatten + memory_map + async2sync   (no $mem_v2/$adff for sat)
#        miter -flatten                          (sat needs leaf cells)
#        -seq 24 -set-init-zero -set-at {1..3} in_resetn 0
#          (unroll 24 cycles; both sides start at all-zero state and take
#           the same 3-cycle reset, after which the DUT executes free
#           inputs. Without this, miter leaves the two sides' FF init
#           states free and even identical circuits report NOT equivalent;
#           with all-zero init and no reset pulse cpu_state=0 is a dead
#           state and everything vacuously proves.)
#      Used for the power check (a KILLED mutant must fail it) and kept
#      available for any survivor that is NOT netlist-identical.
#
#      NOTE: -prove trigger 0 over -seq 24 is a BOUNDED proof (24 cycles
#      from reset); a pass is necessary-but-not-sufficient evidence of
#      equivalence, which is why the identity check is preferred whenever
#      it applies and the SAT recipe's verdict line is prefixed "bounded".

LEC_ELAB_TIMEOUT=900    # per-side elaboration  (yosys prep/opt)
LEC_SAT_TIMEOUT=1800     # bounded SAT unrolling (sat -seq 24)

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
    timeout "$LEC_ELAB_TIMEOUT" yosys -qq -p "read_verilog -I$1 $JUDGE_DIR/ref/picorv32_cpu.v;
                  prep -top cpu -flatten; memory_map; async2sync; opt;
                  rename cpu $2; write_rtlil $WORK/$2.il"
}

if ! emit_side "$GOLD_DIR" gold || ! emit_side "$GATE_DIR" gate; then
    echo "LEC: ERROR - failed to elaborate a side (or elaboration timed out)" >&2
    exit 2
fi

# ---- 1. netlist identity (sound; unbounded; <1 min) ----------------------
# Compare netlists modulo (a) the picorv32.v source path each side was read
# from (differs by construction) and (b) source line numbers embedded in
# \src attributes and yosys's auto-generated cell/wire names (a mutant edit
# can shift them without changing structure). Only the structural content
# (cells, connections, bit widths, constants, port order) matters.
norm_il() {  # file -> stdout: normalized netlist
    sed -E 's#[^" ]*/picorv32\.v#SRC#g; s#SRC:[0-9.]*-[0-9.]*#SRC#g; s#SRC:[0-9.]*#SRC#g;
            s#^module \\gold$#module MOD#; s#^module \\gate$#module MOD#' "$1"
}
if diff <(norm_il "$WORK/gold.il") <(norm_il "$WORK/gate.il") >"$WORK/ident.diff"; then
    echo "LEC: EQUIVALENT (netlist identity: gold and gate elaborate to the"
    echo "  same optimized netlist - sound over unbounded time, all inputs)"
    exit 0
fi
# netlists differ -> fall through to the SPEC bounded-SAT recipe

# ---- 2. SPEC recipe: miter + bounded sat -----------------------------------
LEC_LOG="$WORK/lec.log"
if timeout "$LEC_SAT_TIMEOUT" yosys -p "read_rtlil $WORK/gold.il; read_rtlil $WORK/gate.il;
             miter -equiv -make_outputs -flatten gold gate miter;
             techmap -autoproc -map +/ecp5/cells_sim.v;
             sat -verify -seq 24 -set-init-zero \
                 -set-at 1 in_resetn 0 -set-at 2 in_resetn 0 \
                 -set-at 3 in_resetn 0 -prove trigger 0 -show-inputs miter" \
        >"$LEC_LOG" 2>&1; then
    echo "LEC: EQUIVALENT (bounded: sat -verify -prove trigger 0 held over 24 cycles;"
    echo "  netlists differ, so equivalence is only proven within the window)"
    exit 0
else
    rc=$?
    if [[ $rc -eq 124 ]]; then
        echo "LEC: UNPROVEN (timeout after ${LEC_SAT_TIMEOUT}s - recorded as"
        echo "  unproven, never equivalent; strengthen the judge instead)" >&2
        exit 3
    fi
    if grep -q "proof did fail" "$LEC_LOG"; then
        echo "LEC: NOT EQUIVALENT (sat found trigger=1 model)"
        exit 1
    fi
    echo "LEC: ERROR - sat did not run to a verdict:" >&2
    tail -5 "$LEC_LOG" >&2
    exit 2
fi
