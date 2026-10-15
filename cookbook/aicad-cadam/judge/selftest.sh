#!/usr/bin/env bash
# judge/selftest.sh — prove the judge can fail.
# The known-good cases must pass, every scripted mutant must fail at
# least one gate, and a repeated grade must be byte-identical modulo
# the timing key.  Prints the kill rate; exits non-zero below 90 %.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
GOOD_DIR="$BASE_DIR/examples/good"
BAD_DIR="$BASE_DIR/examples/bad"
GRADE_SH="$SCRIPT_DIR/grade.sh"
VENV="${AICAD_VENV:-$HOME/.venvs/aicad}"
OUT="$(mktemp -d /tmp/aicad-selftest.XXXXXX)"
trap 'rm -rf "$OUT"' EXIT

echo "[selftest] Regenerating mutants..."
"$VENV/bin/python" "$SCRIPT_DIR/mutants.py"

echo ""
echo "[selftest] Known-good cases (must PASS):"
GOOD_PASS=0
GOOD_TOTAL=0
for case in bushing plate bracket; do
    GOOD_TOTAL=$((GOOD_TOTAL + 1))
    t0=$(date +%s)
    if "$GRADE_SH" "$GOOD_DIR/$case" --json "$OUT/good_$case.json" \
            >"$OUT/good_$case.log" 2>&1; then
        GOOD_PASS=$((GOOD_PASS + 1))
        echo "[selftest]   good/$case  PASS  ($(($(date +%s) - t0))s)"
    else
        echo "[selftest]   good/$case  FAIL (unexpected!) — see $OUT/good_$case.log"
        tail -n 5 "$OUT/good_$case.log" || true
    fi
done

echo ""
echo "[selftest] Determinism (same case twice, verdict JSON minus 'timing'):"
DET_FAIL=0
if "$GRADE_SH" "$GOOD_DIR/bushing" --json "$OUT/det1.json" >/dev/null 2>&1 &&
   "$GRADE_SH" "$GOOD_DIR/bushing" --json "$OUT/det2.json" >/dev/null 2>&1; then
    if python3 - "$OUT/det1.json" "$OUT/det2.json" <<'PY'
import json, sys
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
a.pop("timing", None); b.pop("timing", None)
sys.exit(0 if a == b else 1)
PY
    then
        echo "[selftest]   bushing  deterministic"
    else
        echo "[selftest]   bushing  NON-DETERMINISTIC"
        DET_FAIL=1
    fi
else
    echo "[selftest]   determinism re-run failed"
    DET_FAIL=1
fi

echo ""
echo "[selftest] Known-bad mutants (must FAIL):"
KILLED=0
TOTAL=0
for dir_ in "$BAD_DIR"/*/; do
    m="$(basename "$dir_")"
    TOTAL=$((TOTAL + 1))
    if "$GRADE_SH" "$dir_" --json "$OUT/$m.json" >"$OUT/$m.log" 2>&1; then
        echo "[selftest]   $m  PASSED (missed kill!)"
    else
        KILLED=$((KILLED + 1))
        failed="$(python3 - "$OUT/$m.json" <<'EOF' 2>/dev/null || echo "?"
import json, sys
v = json.load(open(sys.argv[1]))
print(",".join(g["gate"] for g in v["gates"] if not g["passed"]))
EOF
)"
        echo "[selftest]   $m  killed (failed: $failed)"
    fi
done

RATE=0
[[ $TOTAL -gt 0 ]] && RATE=$((KILLED * 100 / TOTAL))

echo ""
echo "[selftest] ============================================"
echo "[selftest] good cases passed : $GOOD_PASS/$GOOD_TOTAL"
echo "[selftest] kill rate         : $KILLED/$TOTAL ($RATE %)"
echo "[selftest] ============================================"

[[ $GOOD_PASS -eq $GOOD_TOTAL ]] || exit 1
[[ $RATE -ge 90 ]] || exit 1
[[ $DET_FAIL -eq 0 ]] || exit 1
exit 0
