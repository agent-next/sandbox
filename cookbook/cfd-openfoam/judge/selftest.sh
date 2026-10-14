#!/usr/bin/env bash
# judge/selftest.sh — prove the judge can fail.
# known-good examples must pass; every scripted mutant must fail at least
# one gate.  Prints the kill rate; exits non-zero unless it is >= 90 %.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
GOOD_DIR="$BASE_DIR/examples/good"
BAD_DIR="$BASE_DIR/examples/bad"
GRADE_SH="$SCRIPT_DIR/grade.sh"
OUT="$(mktemp -d /tmp/of-selftest.XXXXXX)"
trap 'rm -rf "$OUT"' EXIT

export FOAM_ETC=/usr/share/openfoam/etc
export WM_PROJECT_DIR=/usr/share/openfoam

echo "[selftest] Regenerating mutant cases..."
python3 "$SCRIPT_DIR/mutants.py"

echo ""
echo "[selftest] Known-good cases (must PASS):"
GOOD_PASS=0
GOOD_TOTAL=0
SEED="${SEED:-42}"
for case in poiseuille cavity; do
    GOOD_TOTAL=$((GOOD_TOTAL + 1))
    t0=$(date +%s)
    if "$GRADE_SH" "$GOOD_DIR/$case" --json "$OUT/good_$case.json" \
            --seed "$SEED" >"$OUT/good_$case.log" 2>&1; then
        GOOD_PASS=$((GOOD_PASS + 1))
        echo "[selftest]   good/$case  PASS  ($(($(date +%s)-t0))s)"
    else
        echo "[selftest]   good/$case  FAIL (unexpected!) — see $OUT/good_$case.log"
        tail -20 "$OUT/good_$case.log" || true
    fi
done

# ---------------------------------------------------------------------------
# Determinism: the same seed twice must give a byte-identical verdict JSON,
# excluding the `timing` key (DEMO-STANDARD.md, "Deterministic").
# ---------------------------------------------------------------------------
echo ""
echo "[selftest] Determinism check (same seed twice, verdict JSON except 'timing'):"
DET_OK=0
DET_FAIL=0
for case in poiseuille cavity; do
    # keep the first run's JSON, then re-run into a second file and compare
    cp "$OUT/good_$case.json" "$OUT/good_${case}_run1.json" 2>/dev/null || true
    if "$GRADE_SH" "$GOOD_DIR/$case" --json "$OUT/good_${case}_run2.json" \
            --seed "$SEED" >"$OUT/det_$case.log" 2>&1; then
        if python3 - "$OUT/good_${case}_run1.json" "$OUT/good_${case}_run2.json" \
                <<'PY' >"$OUT/det_$case.txt" 2>&1
import json, sys
a, b = sys.argv[1], sys.argv[2]
va = json.load(open(a)); vb = json.load(open(b))
ta, tb = va.pop('timing', None), vb.pop('timing', None)
if ta is None or tb is None:
    print('FAIL: no timing key in one of the verdicts'); sys.exit(1)
if va == vb:
    print('identical')
else:
    print('DIFFER')
    print('run1:', json.dumps(va, sort_keys=True)[:400])
    print('run2:', json.dumps(vb, sort_keys=True)[:400])
sys.exit(0 if va == vb else 1)
PY
        then
            DET_OK=$((DET_OK + 1))
            echo "[selftest]   good/$case  deterministic ($(cat "$OUT/det_$case.txt"))"
        else
            DET_FAIL=$((DET_FAIL + 1))
            echo "[selftest]   good/$case  NON-DETERMINISTIC"
            cat "$OUT/det_$case.txt" || true
        fi
    else
        DET_FAIL=$((DET_FAIL + 1))
        echo "[selftest]   good/$case  re-run failed — see $OUT/det_$case.log"
    fi
done

echo ""
echo "[selftest] Known-bad mutants (must FAIL):"

MUTANTS=(
    poiseuille_wrong_bc poiseuille_wrong_viscosity poiseuille_coarse_mesh
    poiseuille_unconverged poiseuille_wrong_outlet
    cavity_wrong_lid cavity_wrong_viscosity cavity_coarse_mesh
    cavity_unconverged cavity_slip_wall
)

KILLED=0
TOTAL=0
declare -a SURVIVED=()
for m in "${MUTANTS[@]}"; do
    dir="$BAD_DIR/$m"
    [[ -d "$dir" ]] || { echo "[selftest]   $m missing — skipped"; continue; }
    TOTAL=$((TOTAL + 1))
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
        echo "[selftest]   $m  killed (failed gates: $failed)"
    fi
done

RATE=0
[[ $TOTAL -gt 0 ]] && RATE=$((KILLED * 100 / TOTAL))

echo ""
echo "[selftest] ============================================"
echo "[selftest] good cases passed : $GOOD_PASS/$GOOD_TOTAL"
echo "[selftest] determinism       : $((DET_OK + DET_FAIL - DET_FAIL))/$((DET_OK + DET_FAIL)) identical"
echo "[selftest] mutants killed    : $KILLED/$TOTAL ($RATE%)"
if [[ ${#SURVIVED[@]} -gt 0 ]]; then
    echo "[selftest] survived        : ${SURVIVED[*]}"
fi
echo "[selftest] ============================================"

fail=0
[[ $GOOD_PASS -ne $GOOD_TOTAL ]] && { echo "[selftest] FAIL: a good case did not pass"; fail=1; }
[[ $DET_FAIL -ne 0 ]] && { echo "[selftest] FAIL: verdict JSON not deterministic at seed $SEED"; fail=1; }
[[ $RATE -lt 90 ]] && { echo "[selftest] FAIL: kill rate $RATE% < 90%"; fail=1; }
[[ $fail -eq 0 ]] && { echo "[selftest] SUCCESS"; exit 0; }
echo "[selftest] FAILURE"
exit 1
