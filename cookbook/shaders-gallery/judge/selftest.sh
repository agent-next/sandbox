#!/usr/bin/env bash
# judge/selftest.sh — prove the judge can fail.
# The known-good example must pass; every mutant must fail at least one
# gate.  Also checks determinism: two grades with the same seed must
# produce byte-identical verdict JSON outside "timing".
# Prints the kill rate; exits non-zero unless it is >= 90%.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
GRADE="$SCRIPT_DIR/grade.sh"
OUT="$(mktemp -d /tmp/sg-selftest.XXXXXX)"
trap 'rm -rf "$OUT"' EXIT
SEED="${SEED:-42}"

echo "[selftest] Regenerating mutants..."
python3 "$SCRIPT_DIR/mutants.py"

echo ""
echo "[selftest] Known-good example (must PASS):"
t0=$(date +%s)
if "$GRADE" "$BASE_DIR/examples/good" --seed "$SEED" \
        --json "$OUT/good.json" >"$OUT/good.log" 2>&1; then
    echo "[selftest]   good PASS ($(($(date +%s)-t0))s)"
else
    echo "[selftest]   good FAIL (unexpected) — see $OUT/good.log"
    tail -20 "$OUT/good.log" || true
    exit 1
fi

echo ""
echo "[selftest] Determinism (same seed twice -> identical outside timing):"
"$GRADE" "$BASE_DIR/examples/good" --seed "$SEED" \
    --json "$OUT/good2.json" >"$OUT/good2.log" 2>&1 || true
if python3 - "$OUT/good.json" "$OUT/good2.json" <<'PY'
import json, sys
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
a.pop("timing", None); b.pop("timing", None)
sys.exit(0 if a == b else 1)
PY
then
    echo "[selftest]   deterministic OK"
else
    echo "[selftest]   NONDETERMINISTIC verdict — timing-independent fields differ"
    diff <(python3 -c "import json,sys;v=json.load(open(sys.argv[1]));v.pop('timing',0);print(json.dumps(v,indent=1,sort_keys=True))" "$OUT/good.json") \
         <(python3 -c "import json,sys;v=json.load(open(sys.argv[1]));v.pop('timing',0);print(json.dumps(v,indent=1,sort_keys=True))" "$OUT/good2.json") | head -20 || true
    exit 1
fi

echo ""
echo "[selftest] Mutants (each must FAIL):"
TOTAL=0; KILLED=0
for d in "$BASE_DIR"/examples/bad/*/; do
    name="$(basename "$d")"
    TOTAL=$((TOTAL + 1))
    t0=$(date +%s)
    if "$GRADE" "$d" --seed "$SEED" --json "$OUT/$name.json" \
            >"$OUT/$name.log" 2>&1; then
        echo "[selftest]   $name  PASS (mutant survived!)"
    else
        KILLED=$((KILLED + 1))
        gates=$(python3 -c "
import json
v = json.load(open('$OUT/$name.json'))
print(','.join(k for k,g in v['gates'].items() if not g['pass']))" 2>/dev/null || echo "?")
        echo "[selftest]   $name  killed ($gates)  ($(($(date +%s)-t0))s)"
    fi
done

echo ""
RATE=$(python3 -c "print($KILLED/$TOTAL if $TOTAL else 0)")
echo "[selftest] kill rate: $KILLED/$TOTAL = $(python3 -c "print(f'{$RATE:.0%}')")"
python3 -c "import sys; sys.exit(0 if $KILLED/$TOTAL >= 0.9 else 1)"
