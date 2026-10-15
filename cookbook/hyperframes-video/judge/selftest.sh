#!/usr/bin/env bash
# judge/selftest.sh — prove the judge can fail.
# The known-good example must pass; every scripted mutant must fail at
# least one gate.  Prints the kill rate; exits non-zero unless it is
# >= 90 % (8 mutants -> all 8 must die).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
GOOD_DIR="$BASE_DIR/examples/good"
BAD_DIR="$BASE_DIR/examples/bad"
GRADE_SH="$SCRIPT_DIR/grade.sh"
OUT="$(mktemp -d /tmp/hf-selftest.XXXXXX)"
trap 'rm -rf "$OUT"' EXIT
SEED="${SEED:-42}"

echo "[selftest] Regenerating mutant artifacts..."
python3 "$SCRIPT_DIR/mutants.py"

echo ""
echo "[selftest] Known-good example (must PASS):"
GOOD_PASS=0
t0=$(date +%s)
if "$GRADE_SH" "$GOOD_DIR" --json "$OUT/good.json" --seed "$SEED" \
        >"$OUT/good.log" 2>&1; then
    GOOD_PASS=1
    echo "[selftest]   good  PASS  ($(($(date +%s)-t0))s)"
else
    echo "[selftest]   good  FAIL (unexpected!) — see $OUT/good.log"
    tail -30 "$OUT/good.log" || true
fi

# ---------------------------------------------------------------------------
# Determinism: the same seed twice must give a byte-identical verdict JSON,
# excluding the 'timing' key (DEMO-STANDARD.md, "Deterministic").
# ---------------------------------------------------------------------------
echo ""
echo "[selftest] Determinism check (same seed twice, verdict JSON except 'timing'):"
DET_OK=0
DET_FAIL=0
if [[ $GOOD_PASS -eq 1 ]]; then
    cp "$OUT/good.json" "$OUT/good_run1.json"
    if "$GRADE_SH" "$GOOD_DIR" --json "$OUT/good_run2.json" \
            --seed "$SEED" >"$OUT/det.log" 2>&1; then
        if python3 - "$OUT/good_run1.json" "$OUT/good_run2.json" \
                <<'PY' >"$OUT/det.txt" 2>&1
import json, sys
va = json.load(open(sys.argv[1])); vb = json.load(open(sys.argv[2]))
ta, tb = va.pop('timing', None), vb.pop('timing', None)
if ta is None or tb is None:
    print('FAIL: no timing key in one of the verdicts'); sys.exit(1)
if va == vb:
    print('identical')
else:
    print('DIFFER')
    for ga, gb in zip(va['gates'], vb['gates']):
        if ga != gb:
            print(' gate %s:\n   run1 %s\n   run2 %s'
                  % (ga.get('gate'), json.dumps(ga)[:300],
                     json.dumps(gb)[:300]))
sys.exit(0 if va == vb else 1)
PY
        then
            DET_OK=1
            echo "[selftest]   good  deterministic ($(cat "$OUT/det.txt"))"
        else
            DET_FAIL=1
            echo "[selftest]   good  NON-DETERMINISTIC"
            cat "$OUT/det.txt" || true
        fi
    else
        DET_FAIL=1
        echo "[selftest]   good  re-run failed — see $OUT/det.log"
        tail -15 "$OUT/det.log" || true
    fi
else
    DET_FAIL=1
    echo "[selftest]   skipped (good did not pass)"
fi

echo ""
echo "[selftest] Known-bad mutants (must FAIL):"

MUTANTS=(wrong-duration missing-beat black-gap wrong-resolution
         off-brand-colors broken-js frozen-video nondeterministic)

KILLED=0
TOTAL=0
declare -a SURVIVED=()
for m in "${MUTANTS[@]}"; do
    dir="$BAD_DIR/$m"
    [[ -d "$dir" ]] || { echo "[selftest]   $m missing — skipped"; continue; }
    TOTAL=$((TOTAL + 1))
    t0=$(date +%s)
    if "$GRADE_SH" "$dir" --json "$OUT/$m.json" >"$OUT/$m.log" 2>&1; then
        echo "[selftest]   $m  PASSED (missed kill!)"
        SURVIVED+=("$m")
    else
        KILLED=$((KILLED + 1))
        failed=$(python3 - "$OUT/$m.json" <<'EOF' 2>/dev/null || echo "?"
import json,sys
v=json.load(open(sys.argv[1]))
print(",".join(str(g["gate"]) for g in v["gates"] if not g["passed"]))
EOF
)
        echo "[selftest]   $m  killed (failed gates: $failed, $(($(date +%s)-t0))s)"
    fi
done

RATE=0
[[ $TOTAL -gt 0 ]] && RATE=$((KILLED * 100 / TOTAL))

echo ""
echo "[selftest] ============================================"
echo "[selftest] good example passed : $GOOD_PASS/1"
echo "[selftest] determinism         : $((DET_OK))/$((DET_OK + DET_FAIL)) identical"
echo "[selftest] mutants killed      : $KILLED/$TOTAL ($RATE%)"
if [[ ${#SURVIVED[@]} -gt 0 ]]; then
    echo "[selftest] survived          : ${SURVIVED[*]}"
fi
echo "[selftest] ============================================"

fail=0
[[ $GOOD_PASS -ne 1 ]] && { echo "[selftest] FAIL: good example did not pass"; fail=1; }
[[ $DET_FAIL -ne 0 ]] && { echo "[selftest] FAIL: verdict JSON not deterministic at seed $SEED"; fail=1; }
[[ $RATE -lt 90 ]] && { echo "[selftest] FAIL: kill rate $RATE% < 90%"; fail=1; }
[[ $fail -eq 0 ]] && { echo "[selftest] SUCCESS"; exit 0; }
echo "[selftest] FAILURE"
exit 1
