#!/usr/bin/env bash
# judge/selftest.sh — prove the judge can fail.
#
# The known-good artifact must pass every gate; every known-bad mutant
# derived by mutants.py must fail at least one. Prints the kill rate and a
# determinism check (two grades of the good artifact at the same seed give
# byte-identical verdict JSON except the timing key). Exits non-zero unless
# the good passes, the verdict is deterministic and the kill rate is >= 90 %.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(dirname "$SCRIPT_DIR")"
GOOD="$DEMO_DIR/examples/good/artifact"
BAD="$DEMO_DIR/examples/bad"
GRADE="$SCRIPT_DIR/grade.sh"
OUT="$(mktemp -d /tmp/gpu-lora-selftest.XXXXXX)"
trap 'rm -rf "$OUT"' EXIT

SEED="${SEED:-0}"

echo "[selftest] generating mutants from the known-good artifact..."
MUTANTS="$(python3 "$SCRIPT_DIR/mutants.py" --out "$BAD")"

echo
echo "[selftest] known-good artifact (must PASS all gates):"
GOOD_OK=0
if "$GRADE" "$GOOD" --seed "$SEED" --json "$OUT/good1.json" >"$OUT/good1.log" 2>&1; then
    GOOD_OK=1
    echo "[selftest]   good/artifact  PASS  ($(grep -o '"total_s": [0-9.]*' "$OUT/good1.json" | head -1 | cut -d' ' -f2) s)"
else
    echo "[selftest]   good/artifact  FAIL (unexpected) — verdict:"
    tail -40 "$OUT/good1.log" || true
fi

echo
echo "[selftest] determinism: same seed twice, verdict except 'timing':"
DET_OK=0
if [[ $GOOD_OK -eq 1 ]]; then
    if "$GRADE" "$GOOD" --seed "$SEED" --json "$OUT/good2.json" >"$OUT/good2.log" 2>&1 \
        && python3 - "$OUT/good1.json" "$OUT/good2.json" <<'PY'
import json, sys
a = json.load(open(sys.argv[1]))
b = json.load(open(sys.argv[2]))
a.pop("timing", None); b.pop("timing", None)
sys.exit(0 if a == b else 1)
PY
    then
        DET_OK=1
        echo "[selftest]   identical"
    else
        echo "[selftest]   DIFFER — verdict JSON is not deterministic"
    fi
else
    echo "[selftest]   skipped (good artifact did not pass)"
fi

echo
echo "[selftest] known-bad mutants (each must FAIL >= 1 gate):"
KILLED=0
TOTAL=0
for m in $MUTANTS; do
    TOTAL=$((TOTAL + 1))
    if "$GRADE" "$BAD/$m" --seed "$SEED" --json "$OUT/$m.json" >"$OUT/$m.log" 2>&1; then
        echo "[selftest]   $m  SURVIVED (missed kill!)"
    else
        KILLED=$((KILLED + 1))
        failed="$(python3 - "$OUT/$m.json" <<'PY' 2>/dev/null || echo "?"
import json, sys
v = json.load(open(sys.argv[1]))
print(",".join(g for g, x in sorted((v.get("gates") or {}).items())
              if isinstance(x, dict) and x.get("pass") is not True))
PY
)"
        echo "[selftest]   $m  killed (failing: $failed)"
    fi
done
RATE=$((TOTAL ? KILLED * 100 / TOTAL : 0))

echo
echo "[selftest] =========================================="
echo "[selftest] good artifact   : $((GOOD_OK ? 1 : 0))/1 passed"
echo "[selftest] deterministic   : $DET_OK/1 identical"
echo "[selftest] mutants killed  : $KILLED/$TOTAL ($RATE %)"
echo "[selftest] =========================================="

FAIL=0
[[ $GOOD_OK -eq 1 ]] || { echo "[selftest] FAIL: the known-good artifact did not pass"; FAIL=1; }
[[ $DET_OK -eq 1 ]] || { echo "[selftest] FAIL: verdict not deterministic at seed $SEED"; FAIL=1; }
[[ $RATE -ge 90 ]] || { echo "[selftest] FAIL: kill rate $RATE % < 90 %"; FAIL=1; }
[[ $FAIL -eq 0 ]] && { echo "[selftest] SUCCESS"; exit 0; }
echo "[selftest] FAILURE"
exit 1
