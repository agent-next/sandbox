#!/usr/bin/env bash
# judge/selftest.sh — prove the judge can fail.
#
#   * every known-good part passes all gates
#   * every scripted mutant (single edit of the good artifact) fails >= 1
#   * kill rate >= 90 % (DEMO-STANDARD.md), else exit 1
#   * determinism: the same seed graded twice gives a byte-identical
#     verdict JSON, excluding the 'timing' key

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
GOOD_DIR="$BASE_DIR/examples/good"
GRADE_SH="$SCRIPT_DIR/grade.sh"
SEED="${SEED:-42}"
OUT="$(mktemp -d /tmp/aicad-selftest.XXXXXX)"
trap 'rm -rf "$OUT"' EXIT

VENV="${AICAD_JUDGE_VENV:-$HOME/.venvs/aicad-judge}"
GATE_PY="$VENV/bin/python"

echo "[selftest] regenerating mutants with the pinned tool..."
"$GATE_PY" "$SCRIPT_DIR/mutants.py" --out "$OUT/mutants"

echo ""
echo "[selftest] known-good parts (must PASS):"
GOOD_PASS=0; GOOD_TOTAL=0
for part in bushing adapter_plate bracket; do
    GOOD_TOTAL=$((GOOD_TOTAL + 1))
    t0=$(date +%s)
    if "$GRADE_SH" "$GOOD_DIR/$part" --seed "$SEED" --json "$OUT/good_$part.json" \
            >"$OUT/good_$part.log" 2>&1; then
        GOOD_PASS=$((GOOD_PASS + 1))
        echo "[selftest]   good/$part  PASS  ($(($(date +%s) - t0))s)"
    else
        echo "[selftest]   good/$part  FAIL (unexpected!) — see $OUT/good_$part.log"
        tail -5 "$OUT/good_$part.log" || true
    fi
done

echo ""
echo "[selftest] determinism (same seed twice, verdict JSON minus 'timing'):"
DET_OK=0
for part in bushing adapter_plate bracket; do
    "$GRADE_SH" "$GOOD_DIR/$part" --seed "$SEED" --json "$OUT/det_${part}_2.json" \
        >/dev/null 2>&1 || true
    if "$GATE_PY" - "$OUT/good_$part.json" "$OUT/det_${part}_2.json" <<'PY'
import json, sys
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
a.pop("timing", None); b.pop("timing", None)
sys.exit(0 if a == b else 1)
PY
    then
        DET_OK=$((DET_OK + 1))
        echo "[selftest]   $part: byte-identical (minus timing)  OK"
    else
        echo "[selftest]   $part: DIFFERS between same-seed runs!"
    fi
done

echo ""
echo "[selftest] mutants (each must FAIL >= 1 gate):"
KILLED=0; TOTAL=0
for mdir in "$OUT"/mutants/*/; do
    name="$(basename "$mdir")"
    TOTAL=$((TOTAL + 1))
    if "$GRADE_SH" "$mdir" --seed "$SEED" --json "$OUT/mut_$name.json" \
            >"$OUT/mut_$name.log" 2>&1; then
        echo "[selftest]   $name  PASSED (judge fooled!)"
    else
        KILLED=$((KILLED + 1))
        fails=$("$GATE_PY" -c "
import json,sys
d = json.load(open('$OUT/mut_$name.json'))
print(', '.join(k for k, v in sorted(d['gates'].items()) if not v['pass']))")
        echo "[selftest]   $name  killed by: $fails"
    fi
done

KILL_RATE=$(awk "BEGIN{printf \"%.0f\", 100 * $KILLED / $TOTAL}")
echo ""
echo "[selftest] summary: good $GOOD_PASS/$GOOD_TOTAL pass," \
     "determinism $DET_OK/3, mutants killed $KILLED/$TOTAL (kill rate ${KILL_RATE}%)"

[[ $GOOD_PASS -eq $GOOD_TOTAL && $DET_OK -eq 3 ]] || { echo "[selftest] FAIL" >&2; exit 1; }
[[ $KILLED -ge 1 ]] || { echo "[selftest] FAIL: no mutant killed" >&2; exit 1; }
[[ $(awk "BEGIN{print ($KILLED / $TOTAL >= 0.90) ? 1 : 0}") -eq 1 ]] \
    || { echo "[selftest] FAIL: kill rate below 90%" >&2; exit 1; }
echo "[selftest] OK"
