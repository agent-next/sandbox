#!/usr/bin/env bash
# judge/selftest.sh — prove the judge can fail.
# The known-good artifact must pass; every known-bad single-edit mutant must
# fail at least one gate.  Prints the kill rate; exits non-zero unless it is
# >= 90 %.  Also proves determinism: two grade.sh runs at the same seed give
# a byte-identical verdict JSON excluding the `timing` key.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
GOOD_DIR="$BASE_DIR/examples/good"
BAD_DIR="$BASE_DIR/examples/bad"
GRADE_SH="$SCRIPT_DIR/grade.sh"
OUT="$(mktemp -d /tmp/harness-selftest.XXXXXX)"
trap 'rm -rf "$OUT"' EXIT

SEED="${SEED:-42}"

echo "[selftest] Regenerating known-bad single-edit mutants of the good eval.py..."
python3 "$SCRIPT_DIR/mutants.py"

echo ""
echo "[selftest] Known-good artifact (must PASS):"
GOOD_PASS=0
GOOD_TOTAL=0
GOOD_TOTAL=$((GOOD_TOTAL + 1))
t0=$(date +%s)
if "$GRADE_SH" "$GOOD_DIR/samples.jsonl" "$GOOD_DIR/eval.py" \
        --json "$OUT/good.json" --seed "$SEED" >"$OUT/good.log" 2>&1; then
    GOOD_PASS=$((GOOD_PASS + 1))
    echo "[selftest]   good  PASS  ($(($(date +%s)-t0))s)"
else
    echo "[selftest]   good  FAIL (unexpected!) — see the log tail below"
    tail -20 "$OUT/good.log" || true
fi

# ---------------------------------------------------------------------------
# Determinism: same seed twice -> byte-identical verdict JSON except `timing`
# ---------------------------------------------------------------------------
echo ""
echo "[selftest] Determinism check (same seed twice, verdict JSON except 'timing'):"
DET_OK=0
DET_FAIL=0
if "$GRADE_SH" "$GOOD_DIR/samples.jsonl" "$GOOD_DIR/eval.py" \
        --json "$OUT/good_run2.json" --seed "$SEED" >"$OUT/det.log" 2>&1; then
    if python3 - "$OUT/good.json" "$OUT/good_run2.json" >"$OUT/det.txt" 2>&1 <<'PY'
import json, sys
va = json.load(open(sys.argv[1])); vb = json.load(open(sys.argv[2]))
ta, tb = va.pop('timing', None), vb.pop('timing', None)
if ta is None or tb is None:
    print('FAIL: no timing key in one of the verdicts'); sys.exit(1)
if va == vb:
    print('identical')
else:
    print('DIFFER')
    print('run1:', json.dumps(va, sort_keys=True)[:400])
    print('run2:', json.dumps(vb, sort_keys=True)[:400])
sys.exit(0 if va == vb else 1)
PY
    then
        DET_OK=$((DET_OK + 1))
        echo "[selftest]   good  deterministic ($(cat "$OUT/det.txt"))"
    else
        DET_FAIL=$((DET_FAIL + 1))
        echo "[selftest]   good  NON-DETERMINISTIC"
        cat "$OUT/det.txt" || true
    fi
else
    DET_FAIL=$((DET_FAIL + 1))
    echo "[selftest]   good  re-run failed — see $OUT/det.log"
fi

# ---------------------------------------------------------------------------
# Known-bad mutants (must FAIL)
# ---------------------------------------------------------------------------
echo ""
echo "[selftest] Known-bad mutants (must FAIL):"
MUTANTS=(
    m1_wrong_pass1_formula
    m2_timeout_counts_as_pass
    m3_metrics_on_stderr
    m4_tests_ignored
    m5_off_by_one_index
)

KILLED=0
TOTAL=0
declare -a SURVIVED=()
for m in "${MUTANTS[@]}"; do
    dir="$BAD_DIR/$m"
    [[ -d "$dir" ]] || { echo "[selftest]   $m missing — skipped"; continue; }
    TOTAL=$((TOTAL + 1))
    if "$GRADE_SH" "$dir/samples.jsonl" "$dir/eval.py" \
            --json "$OUT/$m.json" >"$OUT/$m.log" 2>&1; then
        echo "[selftest]   $m  PASSED (missed kill!)"
        SURVIVED+=("$m")
    else
        KILLED=$((KILLED + 1))
        failed=$(python3 - "$OUT/$m.json" <<'EOF' 2>/dev/null || echo "?"
import json, sys
v = json.load(open(sys.argv[1]))
print(",".join(str(g["gate"]) for g in v.get("gates", []) if not g["passed"]))
EOF
)
        echo "[selftest]   $m  killed (failed gates: $failed)"
    fi
done

RATE=0
[[ $TOTAL -gt 0 ]] && RATE=$((KILLED * 100 / TOTAL))

echo ""
echo "[selftest] ============================================"
echo "[selftest] good cases passed : $GOOD_PASS/$GOOD_TOTAL"
echo "[selftest] determinism       : $((DET_OK + DET_FAIL - DET_FAIL))/$((DET_OK + DET_FAIL)) identical"
echo "[selftest] mutants killed    : $KILLED/$TOTAL ($RATE%)"
if [[ ${#SURVIVED[@]} -gt 0 ]]; then
    echo "[selftest] survived        : ${SURVIVED[*]}"
fi
echo "[selftest] ============================================"

fail=0
[[ $GOOD_PASS -ne $GOOD_TOTAL ]] && { echo "[selftest] FAIL: the known-good artifact did not pass"; fail=1; }
[[ $DET_FAIL -ne 0 ]] && { echo "[selftest] FAIL: verdict JSON not deterministic at seed $SEED"; fail=1; }
[[ $RATE -lt 90 ]] && { echo "[selftest] FAIL: kill rate $RATE% < 90%"; fail=1; }
[[ $fail -eq 0 ]] && { echo "[selftest] SUCCESS"; exit 0; }
echo "[selftest] FAILURE"
exit 1
