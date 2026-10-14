#!/usr/bin/env bash
# judge/selftest.sh — prove the judge can fail.
# good example must pass twice with byte-identical JSON (outside `timing`);
# every known-bad mutant must fail at least one gate; kill rate >= 90%.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
GOOD_DIR="$BASE_DIR/examples/good/httpx-map"
BAD_DIR="$BASE_DIR/examples/bad"
GRADE_SH="$SCRIPT_DIR/grade.sh"
OUT="$(mktemp -d /tmp/archify-selftest.XXXXXX)"
trap 'rm -rf "$OUT"' EXIT
SEED="${SEED:-42}"

if [[ ! -f "$GOOD_DIR/diagram.html" ]]; then
    echo "[selftest] rendering shipped diagram.html for good example..."
    NODE_BIN="$(cat "$HOME/.archify_demo_node" 2>/dev/null || echo node)"
    "$NODE_BIN" "$HOME/archify-skill/archify/bin/archify.mjs" render architecture \
        "$GOOD_DIR/diagram.json" "$GOOD_DIR/diagram.html" \
        --repo-root "$HOME/ground-truth/httpx-0.28.1" >/dev/null
fi

echo "[selftest] Regenerating mutant cases..."
python3 -I "$SCRIPT_DIR/mutants.py"

echo ""
echo "[selftest] Known-good (must PASS):"
t0=$(date +%s)
GOOD_OK=0
if "$GRADE_SH" "$GOOD_DIR" --json "$OUT/good_run1.json" --seed "$SEED" \
        >"$OUT/good_run1.log" 2>&1; then
    GOOD_OK=1
    echo "[selftest]   good/httpx-map  PASS  ($(($(date +%s)-t0))s)"
else
    echo "[selftest]   good/httpx-map  FAIL (unexpected!) — see $OUT/good_run1.log"
    tail -20 "$OUT/good_run1.log" || true
fi

echo ""
echo "[selftest] Determinism (same seed twice, verdict JSON except 'timing'):"
DET_OK=0
if [[ $GOOD_OK == 1 ]] && "$GRADE_SH" "$GOOD_DIR" \
        --json "$OUT/good_run2.json" --seed "$SEED" >"$OUT/det.log" 2>&1; then
    if python3 -I - "$OUT/good_run1.json" "$OUT/good_run2.json" <<'PY' >"$OUT/det.txt" 2>&1
import json, sys
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
ta, tb = a.pop('timing', None), b.pop('timing', None)
if ta is None or tb is None:
    print('FAIL: no timing key'); sys.exit(1)
if a == b:
    print('identical')
else:
    print('DIFFER')
    print('run1:', json.dumps(a, sort_keys=True)[:400])
    print('run2:', json.dumps(b, sort_keys=True)[:400])
sys.exit(0 if a == b else 1)
PY
    then
        DET_OK=1
        echo "[selftest]   good/httpx-map  deterministic ($(cat "$OUT/det.txt"))"
    else
        echo "[selftest]   good/httpx-map  NON-DETERMINISTIC"
        cat "$OUT/det.txt" || true
    fi
else
    echo "[selftest]   determinism re-run failed — see $OUT/det.log"
fi

echo ""
echo "[selftest] Known-bad mutants (must FAIL):"
KILLED=0
TOTAL=0
SURVIVED=()
for dir in "$BAD_DIR"/*/; do
    m="$(basename "$dir")"
    TOTAL=$((TOTAL + 1))
    if "$GRADE_SH" "$dir" --json "$OUT/$m.json" >"$OUT/$m.log" 2>&1; then
        echo "[selftest]   $m  PASSED (missed kill!)"
        SURVIVED+=("$m")
    else
        KILLED=$((KILLED + 1))
        failed=$(python3 -I - "$OUT/$m.json" <<'PY' 2>/dev/null || echo "grade-error"
import json, sys
try:
    v = json.load(open(sys.argv[1]))
    print(",".join(str(g["gate"]) for g in v["gates"] if not g["passed"]))
except Exception:
    print("grade-error")
PY
)
        echo "[selftest]   $m  killed (failed gates: $failed)"
    fi
done

RATE=0
[[ $TOTAL -gt 0 ]] && RATE=$((KILLED * 100 / TOTAL))

echo ""
echo "[selftest] ============================================"
echo "[selftest] good passed       : $GOOD_OK/1"
echo "[selftest] determinism       : $DET_OK/1"
echo "[selftest] mutants killed    : $KILLED/$TOTAL ($RATE%)"
[[ ${#SURVIVED[@]} -gt 0 ]] && echo "[selftest] survived         : ${SURVIVED[*]}"
true
echo "[selftest] ============================================"

fail=0
[[ $GOOD_OK -ne 1 ]] && { echo "[selftest] FAIL: good example did not pass"; fail=1; }
[[ $DET_OK -ne 1 ]] && { echo "[selftest] FAIL: verdict not deterministic at seed $SEED"; fail=1; }
[[ $RATE -lt 90 ]] && { echo "[selftest] FAIL: kill rate $RATE% < 90%"; fail=1; }
[[ $fail -eq 0 ]] && { echo "[selftest] SUCCESS"; exit 0; }
echo "[selftest] FAILURE"
exit 1
