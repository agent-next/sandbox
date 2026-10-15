#!/usr/bin/env bash
# judge/selftest.sh — prove the judge can fail.
#   - the known-good site passes every gate
#   - the same seed twice gives a byte-identical verdict (except 'timing')
#   - the no-skill baseline exits non-zero AND yields a verdict JSON
#     (the exit-code contract: any failed gate => grade.sh rc != 0)
#   - every scripted mutant fails at least one gate  -> kill rate >= 90 %
# Exit non-zero unless good passes, determinism holds, the baseline fails
# the right way, and kill rate >= 90 %.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
GOOD="$BASE_DIR/examples/good/site"
BASELINE="$BASE_DIR/examples/baseline/site"
BAD="$BASE_DIR/examples/bad"

export PLAYWRIGHT_BROWSERS_PATH="$HOME/.cache/ms-playwright"
SEED="${SEED:-42}"
OUT="$(mktemp -d /tmp/taste-selftest.XXXXXX)"
trap 'rm -rf "$OUT"' EXIT

failed_gates() {  # $1 = verdict json
    python3 - "$1" <<'EOF'
import json, sys
try:
    v = json.load(open(sys.argv[1]))
except Exception:
    print("?"); sys.exit(0)
names = []
for g in v.get("gates", []):
    if not g["passed"]:
        if g["gate"] == "taste_rules":
            names += [s["rule"] for s in g["detail"] if not s["passed"]]
        else:
            names.append(g["gate"])
print(",".join(names) or "?")
EOF
}

echo "[selftest] Regenerating mutants..."
python3 "$SCRIPT_DIR/mutants.py"

echo ""
echo "[selftest] Known-good site (must PASS):"
if "$SCRIPT_DIR/grade.sh" "$GOOD" --seed "$SEED" --json "$OUT/good.json" \
        >"$OUT/good.log" 2>&1; then
    echo "[selftest]   good/site  PASS"
else
    echo "[selftest]   good/site  FAIL (unexpected!) — see $OUT/good.log"
    tail -5 "$OUT/good.log" || true
fi

echo ""
echo "[selftest] Determinism (same seed twice, verdict minus 'timing'):"
DET_OK=1
if "$SCRIPT_DIR/grade.sh" "$GOOD" --seed "$SEED" --json "$OUT/good2.json" \
        >"$OUT/det.log" 2>&1; then
    if python3 - "$OUT/good.json" "$OUT/good2.json" <<'EOF'
import json, sys
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
a.pop("timing", None); b.pop("timing", None)
sys.exit(0 if a == b else 1)
EOF
    then
        echo "[selftest]   identical"
    else
        echo "[selftest]   NON-DETERMINISTIC"
        DET_OK=0
    fi
else
    echo "[selftest]   re-run failed — see $OUT/det.log"
    DET_OK=0
fi

echo ""
echo "[selftest] No-skill baseline (MUST exit non-zero — the grader's"
echo "[selftest] exit-code contract: any failed gate => grade.sh rc != 0):"
BASE_OK=0
if [[ -d "$BASELINE" ]]; then
    if "$SCRIPT_DIR/grade.sh" "$BASELINE" --seed "$SEED" --json "$OUT/baseline.json" \
            >"$OUT/baseline.log" 2>&1; then
        echo "[selftest]   baseline/site  exit 0 (CONTRACT BROKEN: a failing site must exit non-zero)"
    else
        FAILS="$(failed_gates "$OUT/baseline.json")"
        if [[ "$FAILS" == "?" ]]; then
            echo "[selftest]   baseline/site  exit non-zero but no verdict JSON"
        else
            echo "[selftest]   baseline/site  exit != 0, fails: $FAILS"
            BASE_OK=1
        fi
    fi
else
    echo "[selftest]   baseline/site  missing — skipped (not asserted)"
    BASE_OK=1
fi

echo ""
echo "[selftest] Known-bad mutants (must FAIL):"
MUTANTS=(low_contrast fixed_container missing_section console_error
         default_font tiny_taps img_no_alt wind_sign_bug gradient_button)
KILLED=0; TOTAL=0; SURVIVED=()
for m in "${MUTANTS[@]}"; do
    d="$BAD/$m"
    [[ -d "$d" ]] || { echo "[selftest]   $m missing — skipped"; continue; }
    TOTAL=$((TOTAL + 1))
    if "$SCRIPT_DIR/grade.sh" "$d" --seed "$SEED" --json "$OUT/$m.json" \
            >"$OUT/$m.log" 2>&1; then
        echo "[selftest]   $m  PASSED (missed kill!)"
        SURVIVED+=("$m")
    else
        KILLED=$((KILLED + 1))
        echo "[selftest]   $m  killed (failed: $(failed_gates "$OUT/$m.json"))"
    fi
done

RATE=0
[[ $TOTAL -gt 0 ]] && RATE=$((KILLED * 100 / TOTAL))

GOOD_OK=0
python3 - "$OUT/good.json" <<'EOF' && GOOD_OK=1
import json, sys
sys.exit(0 if json.load(open(sys.argv[1])).get("all_gates_passed") else 1)
EOF

echo ""
echo "[selftest] ============================================"
echo "[selftest] good passed     : $GOOD_OK"
echo "[selftest] determinism     : $DET_OK"
echo "[selftest] baseline fails  : $BASE_OK (contract: rc != 0 + verdict JSON)"
echo "[selftest] mutants killed  : $KILLED/$TOTAL ($RATE%)"
[[ ${#SURVIVED[@]} -gt 0 ]] && echo "[selftest] survived       : ${SURVIVED[*]}"
echo "[selftest] ============================================"

[[ $GOOD_OK -eq 1 && $DET_OK -eq 1 && $BASE_OK -eq 1 && $RATE -ge 90 ]] && {
    echo "[selftest] SUCCESS"; exit 0; }
echo "[selftest] FAILURE"
exit 1
