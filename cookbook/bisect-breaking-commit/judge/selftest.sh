#!/usr/bin/env bash
# judge/selftest.sh — prove the judge can fail.
# The known-good artifact must pass; every scripted single-edit mutant must
# fail at least one gate.  Prints the kill rate; exits non-zero unless the
# good artifact passes, the verdict is deterministic at a fixed seed, and the
# kill rate is >= 90 %.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
GOOD="$BASE_DIR/examples/good/report.json"
BAD_DIR="$BASE_DIR/examples/bad"
GRADE_SH="$SCRIPT_DIR/grade.sh"
OUT="$(mktemp -d /tmp/bisect-selftest.XXXXXX)"
trap 'rm -rf "$OUT"' EXIT

echo "[selftest] Regenerating mutants..."
python3 -I "$SCRIPT_DIR/mutants.py"

echo ""
echo "[selftest] Known-good artifact (must PASS):"
t0=$(date +%s)
if "$GRADE_SH" "$GOOD" --json "$OUT/good.json" >"$OUT/good.log" 2>&1; then
    echo "[selftest]   good/report.json  PASS  ($(($(date +%s)-t0))s)"
else
    echo "[selftest]   good/report.json  FAIL (unexpected!) — see $OUT/good.log"
    tail -20 "$OUT/good.log" || true
    exit 1
fi

# ---------------------------------------------------------------------------
# Determinism: the same seed twice must give an identical verdict JSON after
# removing the 'timing' key (DEMO-STANDARD.md, "Deterministic").
# ---------------------------------------------------------------------------
echo ""
echo "[selftest] Determinism check (same seed twice, verdict JSON except 'timing'):"
if "$GRADE_SH" "$GOOD" --json "$OUT/good_run2.json" >"$OUT/det.log" 2>&1 \
        && python3 -I - "$OUT/good.json" "$OUT/good_run2.json" <<'PY'
import json, sys
a, b = sys.argv[1], sys.argv[2]
va, vb = json.load(open(a)), json.load(open(b))
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
then
    echo "[selftest]   deterministic (verdicts identical apart from timing)"
else
    echo "[selftest]   NON-DETERMINISTIC — see $OUT/det.log"
    exit 1
fi

echo ""
echo "[selftest] Known-bad mutants (must FAIL):"
KILLED=0
TOTAL=0
SURVIVED=()
for m in "$BAD_DIR"/*.json; do
    name="$(basename "$m" .json)"
    TOTAL=$((TOTAL + 1))
    if "$GRADE_SH" "$m" --json "$OUT/$name.json" >"$OUT/$name.log" 2>&1; then
        echo "[selftest]   $name  PASSED (missed kill!)"
        SURVIVED+=("$name")
    else
        KILLED=$((KILLED + 1))
        failed=$(python3 -I - "$OUT/$name.json" <<'EOF' 2>/dev/null || echo "?"
import json, sys
v = json.load(open(sys.argv[1]))
print(v.get("failed_gate", "?"))
EOF
)
        echo "[selftest]   $name  killed (failed gate: $failed)"
    fi
done

RATE=0
[[ $TOTAL -gt 0 ]] && RATE=$((KILLED * 100 / TOTAL))

echo ""
echo "[selftest] ============================================"
echo "[selftest] good artifact    : PASS"
echo "[selftest] determinism      : identical"
echo "[selftest] mutants killed   : $KILLED/$TOTAL ($RATE%)"
if [[ ${#SURVIVED[@]} -gt 0 ]]; then
    echo "[selftest] survived        : ${SURVIVED[*]}"
fi
echo "[selftest] ============================================"

[[ $RATE -ge 90 ]] || { echo "[selftest] FAIL: kill rate $RATE% < 90%"; exit 1; }
echo "[selftest] SUCCESS"
exit 0
