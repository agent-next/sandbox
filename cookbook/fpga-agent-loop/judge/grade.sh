#!/bin/bash
set -euo pipefail

# fpga-agent-loop judge — grading entry point (SPEC.md, judge/grade.sh).
#
#   grade.sh <cpu.v> [--seed N] [--json out.json] [--g2-count K]
#
# Gates:
#   G0  lint    : verilator --lint-only -Wall (errors fatal, warnings allowed)
#                 + yosys read_verilog; proc; check -assert
#   G1  isa     : every judge/tests/*.hex (riscv-tests rv32ui, no-CSR build)
#                 passes (tohost == 1) in the Verilator testbench, with the
#                 seeded random mem_ready latency enabled (G4 model)
#   G2  diff    : K seeded random programs (gen.py) on the DUT vs the Python
#                 ISS (iss.py via g2check.py); every program must end
#                 tohost==1 and its x1..x31 signature must match the ISS.
#                 K defaults to the SPEC's 200 (--g2-count for quick runs);
#                 each program is 500 instructions with per-program random
#                 mem_ready latency derived from the seed
#   G3  trap    : every judge/tests/trap/*.hex asserts trap and goes quiet
#   G4  bus     : G1 re-run under 3 different latency seeds derived from --seed
#   G5  synth   : yosys synth_ecp5 + nextpnr-ecp5 --85k --package CABGA381 on
#                 g5_top.v (IO-reducing wrapper: cpu + internal 16 KiB RAM,
#                 3 pins). P&R must succeed; reports LUT4/FF/Fmax.
#   G6  perf    : fixed benchmark (generated at grade time by gen_bench.py:
#                 bubble sort of 64 words + checksum) under 0-latency memory;
#                 checksum checked against the ISS; reports CPI.
#                 Informational: not a gate.
#
# Exit 0 only if every non-skipped gate passes (G6 never gates).

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
G2_COUNT=200
G2_INSTRS=500
CPU_V=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --seed) SEED="$2"; shift 2 ;;
        --json) JSON_OUT="$2"; shift 2 ;;
        --g2-count) G2_COUNT="$2"; shift 2 ;;
        -*) echo "unknown option: $1" >&2; exit 2 ;;
        *)  if [[ -n "$CPU_V" ]]; then echo "usage: $0 <cpu.v> [--seed N] [--json out.json] [--g2-count K]" >&2; exit 2; fi
            CPU_V="$1"; shift ;;
    esac
done
if [[ -z "$CPU_V" || ! -f "$CPU_V" ]]; then
    echo "usage: $0 <cpu.v> [--seed N] [--json out.json] [--g2-count K]" >&2
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
# GATE_META_<name> may hold a JSON object merged into the gate's verdict entry.
declare -A GATE_PASS GATE_DETAIL GATE_META
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
    for g in G1 G2 G3 G4; do GATE_PASS[$g]=false; GATE_DETAIL[$g]="verilator build failed"; done
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

# ---- G2: random differential vs the Python ISS ---------------------------------
# Program i uses gen.program_seed(SEED, i); each program runs on the DUT with
# per-program random mem_ready latency (tb --latency --seed <program seed>)
# and in-process on the ISS; the x1..x31 signature must match exactly.
if [[ "${GATE_PASS[G2]}" != false ]]; then
    echo "== G2: random differential vs ISS (${G2_COUNT} programs x ${G2_INSTRS} instrs, base seed $SEED)"
    G2_LOG="$WORK/g2.log"
    if python3 "$JUDGE_DIR/g2check.py" --sim "$SIM" --seed "$SEED" \
            --count "$G2_COUNT" --len "$G2_INSTRS" \
            --max-cycles "$MAX_CYCLES" >"$G2_LOG" 2>&1; then
        GATE_PASS[G2]=true
        GATE_DETAIL[G2]="\"$G2_COUNT/$G2_COUNT random programs match the ISS (x1..x31 signature)\""
        sed 's/^/   /' "$G2_LOG" | tail -1
    else
        GATE_PASS[G2]=false
        GATE_DETAIL[G2]="$(grep -m1 "G2:" "$G2_LOG" | json_escape)"
        echo "   G2: FAIL (first mismatch):"
        sed 's/^/   /' "$G2_LOG" | head -5
        echo "   G2: FAIL"
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

# ---- G5: synthesis + place & route (ECP5-85k CABGA381) -------------------------
# cpu's ~105-bit memory bus is bound inside judge/g5_top.v to an internal
# 16 KiB RAM: the synthesized top has 3 pins, so IO/pinout can never be the
# reason P&R fails. LUT4/FF come from the yosys stat; Fmax from the nextpnr
# --report JSON (worst clock). A synth or P&R failure fails the gate with
# the tool's own error line.
echo "== G5: synth (yosys synth_ecp5 + nextpnr-ecp5 --85k --package CABGA381)"
G5_LOG="$WORK/g5.log"
G5_NET="$WORK/g5_netlist.json"
G5_RPT="$WORK/g5_report.json"
REPORT_LUT4=""; REPORT_FF=""; REPORT_FMAX=""
g5_rc=0
yosys -p "read_verilog -I$PICORV32_DIR $CPU_V; read_verilog $JUDGE_DIR/g5_top.v; hierarchy -top top; synth_ecp5 -top top -json $G5_NET; stat" \
    >"$G5_LOG" 2>&1 || g5_rc=$?
if [[ $g5_rc -eq 0 ]]; then
    REPORT_LUT4=$(grep -oE '^ *[0-9]+ +LUT4$' "$G5_LOG" | tail -1 | awk '{print $1}')
    REPORT_FF=$(grep -oE '^ *[0-9]+ +TRELLIS_FF$' "$G5_LOG" | tail -1 | awk '{print $1}')
    nextpnr-ecp5 --85k --package CABGA381 --json "$G5_NET" \
        --textcfg "$WORK/g5.config" --lpf-allow-unconstrained \
        --report "$G5_RPT" >>"$G5_LOG" 2>&1 || g5_rc=$?
    if [[ $g5_rc -eq 0 ]]; then
        REPORT_FMAX=$(G5_RPT="$G5_RPT" python3 - <<'PY'
import json, os
f = json.load(open(os.environ["G5_RPT"]))["fmax"]
print("%.2f" % min(v["achieved"] for v in f.values()) if f else "")
PY
)
    fi
fi
if [[ $g5_rc -eq 0 && -n "${REPORT_LUT4:-}" && -n "${REPORT_FMAX:-}" ]]; then
    GATE_PASS[G5]=true
    GATE_DETAIL[G5]="$(printf '"synth+P&R ok: lut4=%s ff=%s fmax=%s MHz"' "$REPORT_LUT4" "$REPORT_FF" "$REPORT_FMAX")"
    GATE_META[G5]="$(printf '{"lut4": %s, "ff": %s, "fmax_mhz": %s}' \
        "${REPORT_LUT4:-0}" "${REPORT_FF:-0}" "${REPORT_FMAX:-0}")"
    echo "   G5: PASS (LUT4=$REPORT_LUT4 FF=$REPORT_FF Fmax=${REPORT_FMAX} MHz)"
else
    GATE_PASS[G5]=false
    G5_ERR=$(grep -iE "ERROR:|fatal" "$G5_LOG" | head -1)
    [[ -z "$G5_ERR" ]] && G5_ERR="g5 failed: $(tail -1 "$G5_LOG")"
    GATE_DETAIL[G5]="$(printf '%s' "$G5_ERR" | json_escape)"
    echo "   G5: FAIL"
    echo "   $G5_ERR"
fi

# ---- G6: perf benchmark (reported; NOT a gate) --------------------------------
# bench.hex is generated at grade time: gen_bench.py is pure python
# (gen.py/memh.py only, no toolchain) and byte-identical every run, so the
# image is never committed.
REPORT_CPI=""
if [[ ! -x "${SIM:-/nonexistent}" ]]; then
    GATE_PASS[G6]=skipped
    GATE_DETAIL[G6]="\"verilator build failed - benchmark not run\""
    echo "== G6: perf benchmark: SKIP (no sim)"
elif ! python3 "$JUDGE_DIR/gen_bench.py" --out "$WORK/bench.hex" >/dev/null 2>&1; then
    GATE_PASS[G6]=skipped
    GATE_DETAIL[G6]="\"gen_bench.py failed - benchmark not generated\""
    echo "== G6: perf benchmark: SKIP (generation failed)"
else
    echo "== G6: perf benchmark (bubble sort 64 words + checksum, 0-latency mem)"
    G6_OUT="$WORK/g6.json"
    if python3 "$JUDGE_DIR/g6check.py" --sim "$SIM" --bench "$WORK/bench.hex" \
            >"$G6_OUT" 2>/dev/null; then
        GATE_PASS[G6]=true
    else
        GATE_PASS[G6]=false
    fi
    GATE_META[G6]="$(cat "$G6_OUT")"
    REPORT_CPI=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("cpi") or "")' "$G6_OUT")
    GATE_DETAIL[G6]="$(python3 -c 'import json,sys; import json as j; print(j.dumps(json.load(open(sys.argv[1])).get("detail") or ""))' "$G6_OUT")"
    echo "   G6: $(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("detail") or "n/a")' "$G6_OUT")"
fi

# ---- verdict -------------------------------------------------------------------
T_END=$(date +%s)
WALL=$((T_END - T_START))
VERDICT=true
for g in G0 G1 G2 G3 G4 G5; do
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
    meta = os.environ.get("GATE_META_%s" % g, "")
    if st in ("true", "false"):
        entry = {"pass": st == "true"}
        if detail:
            try:
                entry["detail"] = json.loads(detail)
            except ValueError:
                entry["detail"] = detail
        if meta:
            try:
                entry.update(json.loads(meta))
            except ValueError:
                pass
    else:
        entry = {"skipped": True, "reason": detail}
    gates[g] = entry

def numenv(name):
    v = os.environ.get(name, "")
    if v == "":
        return None
    try:
        f = float(v)
    except ValueError:
        return None
    return int(f) if f == int(f) else f

v = {
    "pass": verdict,
    "gates": gates,
    "lut4": numenv("REPORT_LUT4"),
    "ff": numenv("REPORT_FF"),
    "fmax_mhz": numenv("REPORT_FMAX"),
    "cpi": numenv("REPORT_CPI"),
    "seed": seed,
    "wall_seconds": wall,
    "tool_versions": {
        "verilator": os.environ.get("TOOL_VERILATOR", ""),
        "yosys": os.environ.get("TOOL_VER_YOSYS", ""),
        "nextpnr": os.environ.get("TOOL_VER_NEXTPNR", ""),
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
    export "GATE_META_$g=${GATE_META[$g]:-}"
done
export REPORT_LUT4 REPORT_FF REPORT_FMAX REPORT_CPI
export TOOL_VERILATOR="$(verilator --version 2>/dev/null | head -1)"
export TOOL_VER_YOSYS="$(yosys -V 2>/dev/null | head -1)"
export TOOL_VER_NEXTPNR="$(nextpnr-ecp5 -V 2>/dev/null | head -1)"

emit_json

if [[ "$VERDICT" == true ]]; then
    exit 0
else
    exit 1
fi
