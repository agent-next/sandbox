#!/bin/bash
set -euo pipefail

# lec.sh - yosys LEC for the judge self-test (SPEC.md "Known-bad controls").
#
# Usage: lec.sh <gate_picorv32_dir> [gold_picorv32_dir]
#
# Compares the wrapped SPEC-interface CPU (ref/picorv32_cpu.v) when its
# `include "picorv32.v"` resolves to the gold copy vs the mutant copy.
#
# Verdicts (stdout):
#   "LEC: EQUIVALENT"     exit 0 - proven input/output equivalent
#   "LEC: NOT EQUIVALENT" exit 1 - a distinguishing model was found
#   "LEC: UNPROVEN"       exit 2 - no verdict (error or timeout); a timeout
#                                  is never recorded as equivalent
#
# Two sound stages, each bounded by `timeout` ($LEC_TIMEOUT, default 900s):
#
#   Stage 1 - unbounded equivalence proof (fast path):
#       equiv_make gold gate equiv; opt; equiv_simple; equiv_induct;
#       equiv_status -assert
#     k-induction over the full state space - strictly stronger than the
#     bounded SPEC recipe. Proves the ebreak-uncaught survivor (dead
#     instr_ecall_ebreak flag swept by opt) in ~35 s where the bounded
#     miter+sat recipe needs > 6 min of UNSAT solving on ~2 M variables.
#     equiv_status -assert requires EVERY $equiv cell proven, so this can
#     only declare EQUIVALENT soundly; unproven cells fall through to
#     stage 2 (a failed induction is inconclusive, never a disproof).
#
#   Stage 2 - SPEC recipe, bounded model checking on the outputs:
#       miter -equiv -make_outputs -flatten gold gate miter
#       techmap -autoproc -map +/ecp5/cells_sim.v
#       sat -verify -seq 24 -set-init-zero -set-at {1..3} in_resetn 0
#           -prove trigger 0
#     Sequential-legal additions needed for that recipe to run at all on a
#     sequential design (verified live: identical netlists prove, a
#     known-bad mutant reports "proof did fail"):
#       prep -flatten + memory_map + async2sync   (no $mem_v2/$adff for sat)
#       miter -flatten                          (sat needs leaf cells)
#       -seq 24 -set-init-zero -set-at {1..3} in_resetn 0
#         (unroll 24 cycles; both sides start at all-zero state and take
#          the same 3-cycle reset, after which the DUT executes free
#          inputs. Without this, miter leaves the two sides' FF init
#          states free and even identical circuits report NOT equivalent;
#          with all-zero init and no reset pulse cpu_state=0 is a dead
#          state and everything vacuously proves.)
#     sat succeeding on -verify => EQUIVALENT; "proof did fail" (a real
#     counter-model) => NOT EQUIVALENT - this is what the power check on a
#     killed mutant relies on. A timeout or solver error => UNPROVEN.

JUDGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLCHAIN="$HOME/riscv-toolchain"
export PATH="$TOOLCHAIN/oss-cad-suite/bin:$PATH"
GOLD_DIR="${2:-$TOOLCHAIN/picorv32}"
GATE_DIR="$1"
LEC_TIMEOUT="${LEC_TIMEOUT:-900}"

if [[ ! -f "$GOLD_DIR/picorv32.v" || ! -f "$GATE_DIR/picorv32.v" ]]; then
    echo "LEC: UNPROVEN - picorv32.v not found in gold/gate dir" >&2
    exit 2
fi
if [[ ! -x "$(command -v yosys || true)" ]]; then
    echo "LEC: UNPROVEN - yosys not on PATH (run setup.sh)" >&2
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
    echo "LEC: UNPROVEN - failed to elaborate a side" >&2
    exit 2
fi

# ---- stage 1: unbounded k-induction equivalence proof (fast path) --------
S1_LOG="$WORK/lec_stage1.log"
s1_rc=0
timeout "$LEC_TIMEOUT" yosys -p \
    "read_rtlil $WORK/gold.il; read_rtlil $WORK/gate.il;
     equiv_make gold gate equiv; opt; equiv_simple; equiv_induct;
     equiv_status -assert" >"$S1_LOG" 2>&1 || s1_rc=$?
if [[ $s1_rc -eq 0 ]]; then
    echo "LEC: EQUIVALENT (equiv_simple + equiv_induct proved every \$equiv cell)"
    exit 0
fi
if grep -q "Equivalence successfully proven" "$S1_LOG"; then
    echo "LEC: EQUIVALENT (equiv_simple + equiv_induct proved every \$equiv cell)"
    exit 0
fi
# stage 1 inconclusive (unproven cells or timeout) -> stage 2

# ---- stage 2: SPEC miter+sat recipe, bounded -----------------------------
S2_LOG="$WORK/lec_stage2.log"
s2_rc=0
timeout "$LEC_TIMEOUT" yosys -p \
    "read_rtlil $WORK/gold.il; read_rtlil $WORK/gate.il;
     miter -equiv -make_outputs -flatten gold gate miter;
     techmap -autoproc -map +/ecp5/cells_sim.v;
     sat -verify -seq 24 -set-init-zero \
         -set-at 1 in_resetn 0 -set-at 2 in_resetn 0 \
         -set-at 3 in_resetn 0 -prove trigger 0 -show-inputs miter" \
    >"$S2_LOG" 2>&1 || s2_rc=$?

if [[ $s2_rc -eq 0 ]]; then
    echo "LEC: EQUIVALENT (sat -verify -prove trigger 0 held over 24 cycles)"
    exit 0
fi
if grep -q "proof did fail" "$S2_LOG"; then
    echo "LEC: NOT EQUIVALENT (sat found trigger=1 model)"
    exit 1
fi
echo "LEC: UNPROVEN - sat gave no verdict (rc=$s2_rc; see below)" >&2
tail -5 "$S2_LOG" >&2
exit 2
