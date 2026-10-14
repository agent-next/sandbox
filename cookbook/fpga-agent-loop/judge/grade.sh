#!/bin/bash
set -euo pipefail

# fpga-agent-loop judge — grading entry point (SPEC.md, judge/grade.sh).
#
#   grade.sh <cpu.v> [--seed N] [--json out.json]
#
# Gates run end-to-end in T1:
#   G0  lint    : verilator --lint-only -Wall (errors fatal, warnings allowed)
#                 + yosys read_verilog; proc; check -assert
#   G1  isa     : every judge/tests/*.hex (riscv-tests rv32ui, no-CSR build)
#                 passes (tohost == 1) in the Verilator testbench, with the
#                 seeded random mem_ready latency enabled (G4 model)
#   G3  trap    : every judge/tests/trap/*.hex asserts trap and goes quiet
#   G4  bus     : G1 re-run under 3 different latency seeds derived from --seed
#   G2/G5/G6    : SKIP (T2/T3), recorded as skipped in the JSON verdict
#
# Exit 0 only if every non-skipped gate passes.

JUDGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLCHAIN="$HOME/riscv-toolchain"
OSS_BIN="$TOOLCHAIN/oss-cad-suite/bin"
# Include path for picorv32.v (reference wrapper; self-contained designer
# CPUs are unaffected). Override to point grade.sh at a mutant copy:
#   PICORV32_DIR=$PWD/mutants_out/ignore-mem-ready ./grade.sh ref/picorv32_cpu.v
PICORV32_DIR="${PICORV32_DIR:-$TOOLCHAIN/picorv32}"
export PATH="$OSS_BIN:$PATH"

if [ ! -x "$OSS_BIN/verilator" ]; then
    echo "error: toolchain missing - run $JUDGE_DIR/setup.sh first" >&2
    exit 2
fi

SEED=7
JSON_OUT=""
CPU_V=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --seed) SEED="$2"; shift 2 ;;
        --json) JSON_OUT="$2"; shift 2 ;;
        -*) echo "unknown option: $1" >&2; exit 2 ;;
        *)  if [[ -n "$CPU_V" ]]; then echo "usage: $0 <cpu.v> [--seed N] [--json out.json]" >&2; exit 2; fi
            CPU_V="$1"; shift ;;
    esac
done
if [[ -z "$CPU_V" || ! -f "$CPU_V" ]]; then
    echo "usage: $0 <cpu.v> [--seed N] [--json out.json]" >&2
    [[ -n "$CPU_V" ]] && echo "  cpu file not found: $CPU_V" >&2
    exit 2
fi
CPU_V="$(cd "$(dirname "$CPU_V")" && pwd)/$(basename "$CPU_V")"

if [[ ! -d "$JUDGE_DIR/tests" || -z "$(ls "$JUDGE_DIR"/tests/*.hex 2>/dev/null)" ]]; then
    echo "error: $JUDGE_DIR/tests/*.hex missing - run $JUDGE_DIR/setup.sh first" >&2
    exit 2
fi
if [[ ! -d "$JUDGE_DIR/tests/trap" ]]; then
    echo "error: $JUDGE_DIR/tests/trap/ missing - run: python3 $JUDGE_DIR/gen_traps.py" >&2
    exit 2
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/fpga-judge.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

T_START=$(date +%s)

# ---- gate result collection -------------------------------------------------
# GATE_<name>_pass / GATE_<name>_detail; detail is a JSON-safe string.
declare -A GATE_PASS GATE_DETAIL
GATE_ORDER=(G0 G1 G2 G3 G4 G5 G6)
for g in "${GATE_ORDER[@]}"; do GATE_PASS[$g]="skipped"; GATE_DETAIL[$g]=""; done

json_escape() {  # read stdin -> JSON-safe string on stdout
    python3 -c 'import json,sys; sys.stdout.write(json.dumps(sys.stdin.read().rstrip("\n")))'
}

# ---- G0: lint ----------------------------------------------------------------
# -I"$PICORV32_DIR" lets the reference wrapper resolve its `include
# "picorv32.v"`; self-contained designer CPUs are unaffected.
echo "== G0: lint (verilator -Wall; yosys proc; check -assert)"
G0_LOG="$WORK/g0.log"
g0_rc=0
verilator --lint-only -Wall -Wno-fatal -I"$PICORV32_DIR" "$CPU_V" \
    >"$G0_LOG" 2>&1 || g0_rc=$?
yosys -qq -p "read_verilog -I$PICORV32_DIR $CPU_V; proc; check -assert" \
    >>"$G0_LOG" 2>&1 || g0_rc=$?
if [[ $g0_rc -eq 0 ]]; then
    GATE_PASS[G0]=true
    echo "   G0: PASS"
else
    GATE_PASS[G0]=false
    GATE_DETAIL[G0]="$(tail -5 "$G0_LOG" | json_escape)"
    echo "   G0: FAIL"
    tail -15 "$G0_LOG"
fi

# ---- simulation build --------------------------------------------------------
# One Verilator build shared by G1/G3/G4. -Wno-fatal: warnings allowed
# (SPEC G0 pass rule), errors still abort the build. Lint-only pass above
# distinguishes real errors from style warnings.
echo "== building Verilator model (tb.cpp + $(basename "$CPU_V"))"
SIM="$WORK/sim_cpu"
BUILD_LOG="$WORK/build.log"
build_rc=0
verilator --cc --exe --build -j "$(nproc)" --top-module cpu \
    -Wno-fatal -I"$PICORV32_DIR" --Mdir "$WORK/obj_dir" -CFLAGS "-O2" \
    -o sim_cpu "$CPU_V" "$JUDGE_DIR/tb.cpp" >"$BUILD_LOG" 2>&1 || build_rc=$?
if [[ $build_rc -ne 0 || ! -x "$WORK/obj_dir/sim_cpu" ]]; then
    echo "   build FAILED:"
    tail -20 "$BUILD_LOG"
    for g in G1 G3 G4; do GATE_PASS[$g]=false; GATE_DETAIL[$g]="verilator build failed"; done
else
    SIM="$WORK/obj_dir/sim_cpu"
    echo "   build OK"
fi

MAX_CYCLES=400000

run_hex() {  # hex seed latency(0|1) expect_trap(0|1) -> RESULT line
    local args=(--hex "$1" --max-cycles "$MAX_CYCLES")
    [[ $2 != - ]] && args+=(--seed "$2")
    [[ $3 == 1 ]] && args+=(--latency)
    [[ $4 == 1 ]] && args+=(--expect-trap)
    "$SIM" "${args[@]}" 2>/dev/null
}

# ---- G1: rv32ui (seeded random latency per G4 model) -------------------------
if [[ "${GATE_PASS[G1]}" != false ]]; then
    echo "== G1: riscv-tests rv32ui (latency seed $SEED)"
    fails=0; total=0; fail_names=""
    for hex in "$JUDGE_DIR"/tests/*.hex; do
        name="$(basename "$hex" .hex)"
        total=$((total+1))
        out="$(run_hex "$hex" "$SEED" 1 0)"
        case "$out" in
            "RESULT PASS"*) ;;
            *) fails=$((fails+1)); fail_names+="$name "; echo "   FAIL $name: $out" ;;
        esac
    done
    if [[ $fails -eq 0 ]]; then
        GATE_PASS[G1]=true
        GATE_DETAIL[G1]="\"$total/$total tests pass\""
        echo "   G1: PASS ($total/$total)"
    else
        GATE_PASS[G1]=false
        GATE_DETAIL[G1]="$(printf '"%d/%d tests pass; failing: %s"' "$((total-fails))" "$total" "$fail_names")"
        echo "   G1: FAIL ($((total-fails))/$total)"
    fi
fi

# ---- G3: directed trap tests --------------------------------------------------
if [[ "${GATE_PASS[G3]}" != false ]]; then
    echo "== G3: directed trap tests"
    fails=0; total=0; fail_names=""
    for hex in "$JUDGE_DIR"/tests/trap/*.hex; do
        name="$(basename "$hex" .hex)"
        total=$((total+1))
        out="$(run_hex "$hex" "$SEED" 1 1)"
        case "$out" in
            "RESULT PASS"*) ;;
            *) fails=$((fails+1)); fail_names+="$name "; echo "   FAIL $name: $out" ;;
        esac
    done
    if [[ $fails -eq 0 ]]; then
        GATE_PASS[G3]=true
        GATE_DETAIL[G3]="\"$total/$total trap tests pass\""
        echo "   G3: PASS ($total/$total)"
    else
        GATE_PASS[G3]=false
        GATE_DETAIL[G3]="$(printf '"%d/%d trap tests pass; failing: %s"' "$((total-fails))" "$total" "$fail_names")"
        echo "   G3: FAIL ($((total-fails))/$total)"
    fi
fi

# ---- G4: bus - G1 re-run under 3 other latency seeds --------------------------
if [[ "${GATE_PASS[G4]}" != false ]]; then
    echo "== G4: bus (random mem_ready latency 0-7, seeds $((SEED+1)) $((SEED+101)) $((SEED+1009)))"
    fails=0; runs=0
    for s in $((SEED+1)) $((SEED+101)) $((SEED+1009)); do
        run_fails=0; run_total=0
        for hex in "$JUDGE_DIR"/tests/*.hex; do
            run_total=$((run_total+1))
            out="$(run_hex "$hex" "$s" 1 0)"
            case "$out" in
                "RESULT PASS"*) ;;
                *) run_fails=$((run_fails+1)); echo "   FAIL seed=$s $(basename "$hex" .hex): $out" ;;
            esac
        done
        runs=$((runs+1))
        fails=$((fails+run_fails))
        echo "   seed $s: $((run_total-run_fails))/$run_total"
    done
    if [[ $fails -eq 0 ]]; then
        GATE_PASS[G4]=true
        GATE_DETAIL[G4]="\"all G1 tests pass under latency seeds $((SEED+1)),$((SEED+101)),$((SEED+1009))\""
        echo "   G4: PASS"
    else
        GATE_PASS[G4]=false
        GATE_DETAIL[G4]="$(printf '"%d failing runs over 3 latency seeds"' "$fails")"
        echo "   G4: FAIL"
    fi
fi

# ---- G2/G5/G6: not in T1 ------------------------------------------------------
for g in G2 G5 G6; do
    if [[ "$g" == G6 ]]; then
        echo "== G6: perf benchmark: SKIP (T3) - not a gate"
    else
        echo "== $g: SKIP (T2/T3)"
    fi
done
GATE_DETAIL[G2]="differential test lands in T2"
GATE_DETAIL[G5]="synth gate lands in T3"
GATE_DETAIL[G6]="perf report lands in T3 (not a gate)"

# ---- verdict -------------------------------------------------------------------
T_END=$(date +%s)
WALL=$((T_END - T_START))
VERDICT=true
for g in G0 G1 G3 G4; do
    [[ "${GATE_PASS[$g]}" == true ]] || VERDICT=false
done

emit_json() {
    python3 - "$VERDICT" "$SEED" "$WALL" "$JSON_OUT" "${GATE_ORDER[@]}" <<'PY'
import json, sys, os
verdict = sys.argv[1] == "true"
seed = int(sys.argv[2])
wall = int(sys.argv[3])
json_out = sys.argv[4]
gates = {}
for g in sys.argv[5:]:
    st = os.environ.get("GATE_PASS_%s" % g, "skipped")
    detail = os.environ.get("GATE_DETAIL_%s" % g, "")
    if st in ("true", "false"):
        entry = {"pass": st == "true"}
        if detail:
            try:
                entry["detail"] = json.loads(detail)
            except ValueError:
                entry["detail"] = detail
    else:
        entry = {"skipped": True, "reason": detail}
    gates[g] = entry
v = {
    "pass": verdict,
    "gates": gates,
    "seed": seed,
    "wall_seconds": wall,
    "tool_versions": {
        "verilator": os.environ.get("TOOL_VERILATOR", ""),
        "yosys": os.environ.get("TOOL_VER_YOSYS", ""),
    },
}
s = json.dumps(v, indent=2)
print(s)
if json_out:
    with open(json_out, "w") as f:
        f.write(s + "\n")
PY
}

for g in "${GATE_ORDER[@]}"; do
    export "GATE_PASS_$g=${GATE_PASS[$g]}"
    export "GATE_DETAIL_$g=${GATE_DETAIL[$g]}"
done
export TOOL_VERILATOR="$(verilator --version 2>/dev/null | head -1)"
export TOOL_VER_YOSYS="$(yosys -V 2>/dev/null | head -1)"

emit_json

if [[ "$VERDICT" == true ]]; then
    exit 0
else
    exit 1
fi
