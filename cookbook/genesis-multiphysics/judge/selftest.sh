#!/usr/bin/env bash
# judge/selftest.sh — prove the judge can fail.
# The known-good scenario must pass; every scripted mutant must fail at
# least one gate; two good-case grades at the same seed must produce
# byte-identical verdict JSON outside the `timing` key. Prints the kill
# rate; exits non-zero unless it is >= 90 %.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
GRADE_SH="$SCRIPT_DIR/grade.sh"
OUT="$(mktemp -d /tmp/gen-selftest.XXXXXX)"
echo "[selftest] scratch: $OUT"

echo "[selftest] Regenerating mutant scenarios..."
python3 "$SCRIPT_DIR/mutants.py" >/dev/null

SEED="${SEED:-42}"

echo ""
echo "[selftest] Known-good scenario (must PASS):"
GOOD_PASS=0; GOOD_TOTAL=0
GOOD_TOTAL=$((GOOD_TOTAL + 1))
t0=$(date +%s)
if "$GRADE_SH" "$BASE_DIR/examples/good/scenario.py" \
        --json "$OUT/good.json" --seed "$SEED" >"$OUT/good.log" 2>&1; then
    GOOD_PASS=$((GOOD_PASS + 1))
    echo "[selftest]   good  PASS  ($(($(date +%s)-t0))s)"
else
    echo "[selftest]   good  FAIL (unexpected!) — tail of log:"
    tail -30 "$OUT/good.log" || true
fi

echo ""
echo "[selftest] Determinism check (same seed twice, verdict JSON except 'timing'):"
DET_OK=0; DET_FAIL=0
cp "$OUT/good.json" "$OUT/good_run1.json" 2>/dev/null || true
if "$GRADE_SH" "$BASE_DIR/examples/good/scenario.py" \
        --json "$OUT/good_run2.json" --seed "$SEED" >"$OUT/det.log" 2>&1; then
    if python3 - "$OUT/good_run1.json" "$OUT/good_run2.json" <<'PY'
import json, sys
a, b = sys.argv[1], sys.argv[2]
va = json.load(open(a)); vb = json.load(open(b))
ta, tb = va.pop('timing', None), vb.pop('timing', None)
if ta is None or tb is None:
    print('FAIL: no timing key in one of the verdicts'); sys.exit(1)
if va != vb:
    print('DIFFER')
    print('run1:', json.dumps(va, sort_keys=True)[:400])
    print('run2:', json.dumps(vb, sort_keys=True)[:400])
    sys.exit(1)
print('identical')
PY
    then DET_OK=$((DET_OK + 1)); echo "[selftest]   good  deterministic"
    else DET_FAIL=$((DET_FAIL + 1)); echo "[selftest]   good  NON-DETERMINISTIC"; fi
else
    DET_FAIL=$((DET_FAIL + 1))
    echo "[selftest]   good  re-run failed — see $OUT/det.log"
fi

echo ""
echo "[selftest] Known-bad mutants (must FAIL):"
KILLED=0; TOTAL=0
declare -a SURVIVED=()
for dir in "$BASE_DIR"/examples/bad/*/; do
    m="$(basename "$dir")"
    [[ -f "$dir/scenario.py" ]] || continue
    TOTAL=$((TOTAL + 1))
    if "$GRADE_SH" "$dir/scenario.py" --json "$OUT/$m.json" >"$OUT/$m.log" 2>&1; then
        echo "[selftest]   $m  PASSED (missed kill!)"
        SURVIVED+=("$m")
    else
        KILLED=$((KILLED + 1))
        failed=$(python3 - "$OUT/$m.json" <<'EOF' 2>/dev/null || echo "runner-error"
import json, sys
v = json.load(open(sys.argv[1]))
print(",".join(str(g["gate"]) for g in v["gates"] if not g["passed"]))
EOF
)
        echo "[selftest]   $m  killed (failed gates: $failed)"
    fi
done

RATE=0
[[ $TOTAL -gt 0 ]] && RATE=$((KILLED * 100 / TOTAL))

echo ""
echo "[selftest] ============================================"
echo "[selftest] good case passed : $GOOD_PASS/$GOOD_TOTAL"
echo "[selftest] determinism      : $DET_OK/$((DET_OK + DET_FAIL)) identical"
echo "[selftest] mutants killed   : $KILLED/$TOTAL ($RATE%)"
if [[ ${#SURVIVED[@]} -gt 0 ]]; then
    echo "[selftest] survived       : ${SURVIVED[*]}"
fi
echo "[selftest] ============================================"

fail=0
[[ $GOOD_PASS -ne $GOOD_TOTAL ]] && { echo "[selftest] FAIL: the good case did not pass"; fail=1; }
[[ $DET_FAIL -ne 0 ]] && { echo "[selftest] FAIL: verdict JSON not deterministic at seed $SEED"; fail=1; }
[[ $RATE -lt 90 ]] && { echo "[selftest] FAIL: kill rate $RATE% < 90%"; fail=1; }
[[ $fail -eq 0 ]] && { echo "[selftest] SUCCESS"; exit 0; }
echo "[selftest] FAILURE"
exit 1
