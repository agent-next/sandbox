#!/bin/bash
set -euo pipefail

# selftest.sh - judge acceptance oracle 1 (SPEC.md T3).
#
# Verifies the judge itself by grading the known-good picorv32 and a
# suite of anchored single-edit mutants, and by cross-checking the ISS
# against the control design.
#
# Steps:
#   1.  control:   grade picorv32 via grade.sh -> must PASS (G0-G5; G6 reports CPI)
#   2.  ISS x-check: g2check.py --iss-check over N programs (1000, --quick: 100)
#                  must agree 100%
#   3.  mutants:   mutants.py regenerates mutants_out/*/ (dirs only: picorv32.v +
#                  wrapper + Makefile); each is graded with grade.sh --g2-count 24.
#                  Mutants are aimed per-gate so a small G2 count keeps the
#                  runtime sane; killed = verdict JSON pass == false.
#   4.  kill rate: must be >= 95%
#   5.  survivors: each must be proven input/output equivalent to gold by the
#                  SPEC LEC recipe (judge/lec.sh), else selftest fails
#   6.  LEC power: the same LEC recipe run on a KILLED mutant must report
#                  NOT EQUIVALENT - a LEC that says "equivalent" on a
#                  known-bad design is a false pass and invalidates step 5
#
# Usage: bash selftest.sh [--quick] [--keep]
#   --quick   ISS cross-check over 100 programs instead of 1000
#   --keep    do not delete mutants_out/* build dirs afterwards (debug)
#
# Exit 0 iff every acceptance criterion above holds.

JUDGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLCHAIN="$HOME/riscv-toolchain"
export PATH="$TOOLCHAIN/oss-cad-suite/bin:$PATH"
GOLD_DIR="$TOOLCHAIN/picorv32"
GOLD_V="$GOLD_DIR/picorv32.v"

QUICK=0
KEEP=0
for arg in "$@"; do
    case "$arg" in
        --quick) QUICK=1 ;;
        --keep) KEEP=1 ;;
        *) echo "usage: selftest.sh [--quick] [--keep]" >&2; exit 2 ;;
    esac
done
[[ $QUICK -eq 1 ]] && ISS_PROGS=100 || ISS_PROGS=1000

WORK="$(mktemp -d "${TMPDIR:-/tmp}/selftest.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
T0=$(date +%s)
failed() { echo "SELFTEST: FAIL - $*" >&2; exit 1; }
now() { date +%s; }

echo "=== judge selftest (acceptance oracle 1, T3) ==="
echo "toolchain: $TOOLCHAIN"
echo "iss cross-check programs: $ISS_PROGS"
echo

# ---- 0. sanity: toolchain present ------------------------------------------------
[[ -x "$TOOLCHAIN/oss-cad-suite/bin/yosys" ]] \
    || failed "yosys not installed - run bash judge/setup.sh first"
[[ -x "$TOOLCHAIN/oss-cad-suite/bin/verilator" ]] \
    || failed "verilator not installed - run bash judge/setup.sh first"
[[ -f "$GOLD_V" ]] \
    || failed "pinned picorv32.v missing - run bash judge/setup.sh first"
[[ -x "$(command -v nextpnr-ecp5 || true)" ]] \
    || failed "nextpnr-ecp5 not installed - run bash judge/setup.sh first"

# ---- 1. control: grade known-good picorv32 ---------------------------------------
echo "--- step 1: control grade (picorv32, G0-G5 + G6 report)"
STEP_T=$(now)
if bash "$JUDGE_DIR/grade.sh" "$JUDGE_DIR/ref/picorv32_cpu.v" \
        --json "$WORK/control.json"; then
    echo "control: PASS"
else
    echo "control verdict:"
    cat "$WORK/control.json" || true
    failed "control picorv32 did not pass the judge"
fi
CONTROL_JSON="$WORK/control.json"
cp "$CONTROL_JSON" "$JUDGE_DIR/verdict.control.json" 2>/dev/null || true
LUT4=$(python3 -c 'import json;print(json.load(open("'"$CONTROL_JSON"'"))["lut4"])')
FF=$(python3 -c 'import json;print(json.load(open("'"$CONTROL_JSON"'"))["ff"])')
FMAX=$(python3 -c 'import json;print(json.load(open("'"$CONTROL_JSON"'"))["fmax_mhz"])')
CPI=$(python3 -c 'import json;print(json.load(open("'"$CONTROL_JSON"'"))["cpi"])')
echo "control metrics: LUT4=$LUT4 FF=$FF Fmax=$FMAX MHz CPI=$CPI  ($(($(now)-STEP_T))s)"
echo

# ---- 2. ISS cross-check ------------------------------------------------------------
# Build the gold sim once, then run g2check.py over $ISS_PROGS programs:
# every generated program's x1..x31 signature must agree between the ISS
# oracle and the known-good RTL. 1000 programs (100 with --quick).
echo "--- step 2: ISS x-check (g2check.py on gold, $ISS_PROGS programs)"
STEP_T=$(now)
GOLD_SIM="$WORK/obj_dir/sim_cpu"
verilator --cc --exe --build -j "$(nproc)" --top-module cpu \
    -Wno-fatal -I"$GOLD_DIR" --Mdir "$WORK/obj_dir" -CFLAGS "-O2" \
    -o sim_cpu "$JUDGE_DIR/ref/picorv32_cpu.v" "$JUDGE_DIR/tb.cpp" \
    >"$WORK/gold_build.log" 2>&1 \
    || failed "gold verilator build failed (see $WORK/gold_build.log)"
[[ -x "$GOLD_SIM" ]] || failed "gold sim binary missing"
if python3 "$JUDGE_DIR/g2check.py" --sim "$GOLD_SIM" \
        --count "$ISS_PROGS" --seed 7; then
    echo "iss cross-check: PASS"
else
    failed "ISS disagreed with control picorv32"
fi
echo "($(($(now)-STEP_T))s)"
echo

# ---- 3-4. mutants: generate, grade, kill rate --------------------------------------
echo "--- step 3: mutants (generate + grade, kill rate >= 95%)"
STEP_T=$(now)
rm -rf "$JUDGE_DIR/mutants_out"
MUT_NAMES=$(python3 "$JUDGE_DIR/mutants.py" --list)
N_MUT=$(echo "$MUT_NAMES" | grep -c .)
echo "$N_MUT mutants"
python3 "$JUDGE_DIR/mutants.py" --outdir "$JUDGE_DIR/mutants_out" >/dev/null \
    || failed "mutants.py failed to generate"

KILLED=0; SURVIVORS=""
kill_table="$WORK/kill_table.txt"
: > "$kill_table"
for m in $MUT_NAMES; do
    md="$JUDGE_DIR/mutants_out/$m"
    t=$(now)
    if PICORV32_DIR="$md" bash "$JUDGE_DIR/grade.sh" \
            "$JUDGE_DIR/ref/picorv32_cpu.v" --g2-count 24 \
            --json "$WORK/verdict.$m.json" >"$WORK/grade.$m.log" 2>&1; then
        SURVIVORS="${SURVIVORS:+$SURVIVORS }$m"
        printf "%-24s SURVIVOR  (%ds)\n" "$m" "$(($(now)-t))" >>"$kill_table"
        echo "  $m ... SURVIVOR"
    else
        KILLED=$((KILLED+1))
        failed_gates=$(python3 - <<PY
import json
v = json.load(open("$WORK/verdict.$m.json"))
print(",".join(g for g, e in v["gates"].items() if e.get("pass") is False))
PY
)
        printf "%-24s KILLED    (%s)  (%ds)\n" "$m" "$failed_gates" "$(($(now)-t))" >>"$kill_table"
        echo "  $m ... KILLED ($failed_gates)"
    fi
done
RATE=$(python3 -c "print('%.1f' % (100.0 * $KILLED / $N_MUT))")
echo
echo "mutant kill table:"
cat "$kill_table"
echo "kill rate: $KILLED/$N_MUT = $RATE%  ($(($(now)-STEP_T))s)"
echo

# ---- 5. survivors: LEC equivalence proof --------------------------------------------
LEC_T=$(now)
if [[ -n "$SURVIVORS" ]]; then
    echo "--- step 5: LEC survivor proofs (SPEC recipe via lec.sh)"
    # lec.sh verdicts: "LEC: EQUIVALENT" (rc 0), "LEC: NOT EQUIVALENT"
    # (rc 1: a real bug the gates missed), "LEC: UNPROVEN" (rc 2:
    # error/timeout - never counted as equivalent).
    for m in $SURVIVORS; do
        echo "  $m:"
        LEC_OUT=$(bash "$JUDGE_DIR/lec.sh" "$JUDGE_DIR/mutants_out/$m" 2>&1) && LEC_RC=0 || LEC_RC=$?
        echo "$LEC_OUT" | sed 's/^/    /'
        if [[ $LEC_RC -eq 0 ]] && echo "$LEC_OUT" | grep -q "^LEC: EQUIVALENT"; then
            echo "    -> proven equivalent (survivor accepted)"
        elif [[ $LEC_RC -eq 1 ]]; then
            failed "survivor $m is NOT equivalent to gold - a real bug slipped past every gate"
        else
            failed "survivor $m equivalence UNPROVEN (LEC rc=$LEC_RC; a timeout is unproven, never equivalent)"
        fi
    done
else
    echo "--- step 5: no survivors to prove"
fi
echo

# ---- 6. LEC power check: a KILLED mutant must report NOT EQUIVALENT -----------------
echo "--- step 6: LEC power check (same recipe on a known-killed mutant)"
# branch-flip is the most structurally subtle killer (decode-level, still
# finishes programs); it must be picked from the KILLED rows of the kill
# table - if it survived and was proven equivalent, using it here would
# be invalid. Fall back to the first killed mutant.
LEC_PWR=$(awk '$1=="branch-flip" && $2=="KILLED" {print $1}' "$kill_table")
[[ -n "$LEC_PWR" ]] || \
    LEC_PWR=$(awk '$2=="KILLED" {print $1; exit}' "$kill_table")
[[ -n "$LEC_PWR" ]] || failed "no killed mutant available for the LEC power check"
echo "  lec.sh on killed mutant: $LEC_PWR"
LEC_OUT=$(bash "$JUDGE_DIR/lec.sh" "$JUDGE_DIR/mutants_out/$LEC_PWR" 2>&1) && LEC_RC=0 || LEC_RC=$?
echo "$LEC_OUT" | sed 's/^/  /'
# rc 1 + "LEC: NOT EQUIVALENT" is the only acceptable answer: rc 0 would be
# a false pass invalidating every survivor proof; rc 2 (timeout/error)
# leaves the recipe's power unproven.
if [[ $LEC_RC -eq 1 ]] && echo "$LEC_OUT" | grep -q "^LEC: NOT EQUIVALENT"; then
    echo "  LEC power check: PASS (recipe detects a real difference)"
else
    failed "LEC on killed mutant $LEC_PWR gave rc=$LEC_RC ('$LEC_OUT') - cannot trust the survivor proofs"
fi
echo "($(($(now)-LEC_T))s for steps 5-6)"
echo

# ---- 7. kill-rate verdict ------------------------------------------------------------
python3 -c "exit(0 if $RATE >= 95.0 else 1)" \
    || failed "kill rate $RATE% < 95%"

# ---- 8. cleanup ----------------------------------------------------------------------
if [[ $KEEP -eq 0 ]]; then
    rm -rf "$JUDGE_DIR/mutants_out"   # created by mutants.py in step 3
fi
rm -f "$JUDGE_DIR/verdict.control.json"

echo "=== SELFTEST: PASS ==="
echo "  control picorv32: PASS (G0-G5)"
echo "  control metrics:  LUT4=$LUT4 FF=$FF Fmax=$FMAX MHz CPI=$CPI"
echo "  iss x-check:      $ISS_PROGS/$ISS_PROGS programs agree"
echo "  mutants:          $KILLED/$N_MUT killed ($RATE%)"
echo "  survivors proven: ${SURVIVORS:-none}"
echo "  LEC power check:  PASS ($LEC_PWR -> NOT EQUIVALENT)"
echo "  wall time:        $(($(now)-T0))s"
