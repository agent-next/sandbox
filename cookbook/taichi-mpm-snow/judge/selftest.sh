#!/usr/bin/env bash
# judge/selftest.sh — prove the judge can fail.
# known-good examples must pass; every scripted mutant must fail at
# least one gate.  Prints the kill rate; exits non-zero unless it is
# >= 90 %.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
GOOD_DIR="$BASE_DIR/examples/good"
BAD_DIR="$BASE_DIR/examples/bad"
GRADE_SH="$SCRIPT_DIR/grade.sh"
OUT="$(mktemp -d /tmp/mpm-selftest.XXXXXX)"
trap 'rm -rf "$OUT"' EXIT

SEED="${SEED:-0}"

echo "[selftest] Regenerating mutant artifacts..."
python3 "$SCRIPT_DIR/mutants.py"

echo ""
echo "[selftest] Known-good example (must PASS):"
GOOD_PASS=0
GOOD_TOTAL=0
GOOD_TOTAL=$((GOOD_TOTAL + 1))
t0=$(date +%s)
if "$GRADE_SH" "$GOOD_DIR" --json "$OUT/good.json" --seed "$SEED" \
        >"$OUT/good.log" 2>&1; then
    GOOD_PASS=$((GOOD_PASS + 1))
    echo "[selftest]   good  PASS  ($(($(date +%s)-t0))s)"
else
    echo "[selftest]   good  FAIL (unexpected!) — see $OUT/good.log"
    tail -20 "$OUT/good.log" || true
fi

echo ""
echo "[selftest] Determinism check (same seed twice, verdict JSON except 'timing'):"
DET_OK=0
DET_FAIL=0
cp "$OUT/good.json" "$OUT/good_run1.json" 2>/dev/null || true
if "$GRADE_SH" "$GOOD_DIR" --json "$OUT/good_run2.json" --seed "$SEED" \
        >"$OUT/det.log" 2>&1; then
    if python3 - "$OUT/good_run1.json" "$OUT/good_run2.json" <<'PY' \
            >"$OUT/det.txt" 2>&1
import json, sys
va = json.load(open(sys.argv[1])); vb = json.load(open(sys.argv[2]))
ta, tb = va.pop('timing', None), vb.pop('timing', None)
if ta is None or tb is None:
    print('FAIL: no timing key'); sys.exit(1)
if va == vb:
    print('identical'); sys.exit(0)
print('DIFFER')
print('run1:', json.dumps(va, sort_keys=True)[:400])
print('run2:', json.dumps(vb, sort_keys=True)[:400])
sys.exit(1)
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

echo ""
echo "[selftest] Known-bad mutants (must FAIL):"

MUTANTS=(
    gravity_flipped dt_too_large no_boundary
    p2g_weight_bug no_plasticity v0_mismatch
)

KILLED=0
TOTAL=0
declare -a SURVIVED=()
for m in "${MUTANTS[@]}"; do
    dir="$BAD_DIR/$m"
    [[ -d "$dir" ]] || { echo "[selftest]   $m missing — skipped"; continue; }
    TOTAL=$((TOTAL + 1))
    if "$GRADE_SH" "$dir" --json "$OUT/$m.json" --seed "$SEED" \
            >"$OUT/$m.log" 2>&1; then
        echo "[selftest]   $m  PASSED (missed kill!)"
        SURVIVED+=("$m")
    else
        KILLED=$((KILLED + 1))
        failed=$(python3 - "$OUT/$m.json" <<'EOF' 2>/dev/null || echo "?"
import json,sys
v=json.load(open(sys.argv[1]))
print(",".join(str(g["gate"]) for g in v.get("gates",[]) if not g["passed"]))
EOF
)
        echo "[selftest]   $m  killed (failed gates: $failed)"
    fi
done

RATE=0
[[ $TOTAL -gt 0 ]] && RATE=$((KILLED * 100 / TOTAL))

echo ""
echo "[selftest] ============================================"
echo "[selftest] good passed       : $GOOD_PASS/$GOOD_TOTAL"
echo "[selftest] determinism       : $DET_OK/1 identical"
echo "[selftest] mutants killed    : $KILLED/$TOTAL ($RATE%)"
if [[ ${#SURVIVED[@]} -gt 0 ]]; then
    echo "[selftest] survived        : ${SURVIVED[*]}"
fi
echo "[selftest] ============================================"

fail=0
[[ $GOOD_PASS -ne $GOOD_TOTAL ]] && { echo "[selftest] FAIL: good did not pass"; fail=1; }
[[ $DET_FAIL -ne 0 ]] && { echo "[selftest] FAIL: verdict not deterministic at seed $SEED"; fail=1; }
[[ $RATE -lt 90 ]] && { echo "[selftest] FAIL: kill rate $RATE% < 90%"; fail=1; }
[[ $fail -eq 0 ]] && { echo "[selftest] SUCCESS"; exit 0; }
echo "[selftest] FAILURE"
exit 1
