#!/usr/bin/env bash
# judge/selftest.sh — prove the judge can fail.
# known-good examples must pass; every scripted mutant must fail at
# least one gate.  Prints the kill rate; exits non-zero unless it is
# >= 90 %.
#
# The host this demo targets has 2 vCPUs and the artifact is pinned to
# one Taichi thread, so grades run two at a time without disturbing
# determinism.  Mutants are graded with --steps $MUT_STEPS: every
# killing gate trips well inside that window (verified in RECEIPT.md),
# and all physics gates are evaluated on the finite metrics prefix, so
# a mutant that blows up early is still killed by its physics gate.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
GOOD_DIR="$BASE_DIR/examples/good"
BAD_DIR="$BASE_DIR/examples/bad"
GRADE_SH="$SCRIPT_DIR/grade.sh"
OUT="$(mktemp -d /tmp/mpm-selftest.XXXXXX)"
VERDICT_DIR="${VERDICT_DIR:-$BASE_DIR/media/data/verdicts}"
trap 'rm -rf "$OUT"' EXIT

SEED="${SEED:-0}"
MUT_STEPS="${MUT_STEPS:-1000}"
PAR="${PAR:-2}"

echo "[selftest] Regenerating mutant artifacts..."
python3 "$SCRIPT_DIR/mutants.py"

mkdir -p "$VERDICT_DIR"

echo ""
echo "[selftest] Known-good example (must PASS, seed $SEED):"
GOOD_PASS=0
GOOD_TOTAL=1
t0=$(date +%s)
if "$GRADE_SH" "$GOOD_DIR" --json "$OUT/good.json" --seed "$SEED" \
        >"$OUT/good.log" 2>&1; then
    GOOD_PASS=$((GOOD_PASS + 1))
    echo "[selftest]   good  PASS  ($(($(date +%s)-t0))s)"
else
    echo "[selftest]   good  FAIL (unexpected!) — see $OUT/good.log"
    tail -20 "$OUT/good.log" || true
fi
cp "$OUT/good.json" "$VERDICT_DIR/good.json" 2>/dev/null || true

echo ""
echo "[selftest] Determinism check (same seed twice, verdict JSON except 'timing'):"
DET_OK=0
DET_FAIL=0
cp "$OUT/good.json" "$OUT/good_run1.json" 2>/dev/null || true
if "$GRADE_SH" "$GOOD_DIR" --json "$OUT/good_run2.json" --seed "$SEED" \
        >"$OUT/det.log" 2>&1; then
    if python3 - "$OUT/good_run1.json" "$OUT/good_run2.json" <<'PY' \
            >"$OUT/det.txt" 2>&1
import json, sys
va = json.load(open(sys.argv[1])); vb = json.load(open(sys.argv[2]))
ta, tb = va.pop('timing', None), vb.pop('timing', None)
if ta is None or tb is None:
    print('FAIL: no timing key'); sys.exit(1)
if va == vb:
    print('identical'); sys.exit(0)
print('DIFFER')
print('run1:', json.dumps(va, sort_keys=True)[:400])
print('run2:', json.dumps(vb, sort_keys=True)[:400])
sys.exit(1)
PY
    then
        DET_OK=$((DET_OK + 1))
        echo "[selftest]   good  deterministic ($(cat "$OUT/det.txt"))"
    else
        DET_FAIL=$((DET_FAIL + 1))
        echo "[selftest]   good  NON-DETERMINISTIC"
        cat "$OUT/det.txt" || true
    fi
else
    DET_FAIL=$((DET_FAIL + 1))
    echo "[selftest]   good  re-run failed — see $OUT/det.log"
fi

echo ""
echo "[selftest] Known-bad mutants (must FAIL; --steps $MUT_STEPS, $PAR at a time):"

MUTANTS=(
    gravity_flipped dt_too_large no_boundary
    p2g_weight_bug no_plasticity v0_mismatch
)

grade_mutant() {
    local m="$1"
    local dir="$BAD_DIR/$m"
    if [[ ! -d "$dir" ]]; then
        echo "MISSING" > "$OUT/$m.status"
        return
    fi
    if "$GRADE_SH" "$dir" --json "$OUT/$m.json" --seed "$SEED" \
            --steps "$MUT_STEPS" >"$OUT/$m.log" 2>&1; then
        echo "PASSED" > "$OUT/$m.status"
    else
        echo "KILLED" > "$OUT/$m.status"
    fi
    cp "$OUT/$m.json" "$VERDICT_DIR/$m.json" 2>/dev/null || true
}

for m in "${MUTANTS[@]}"; do
    while (( $(jobs -rp | wc -l) >= PAR )); do sleep 1; done
    grade_mutant "$m" &
done
wait

KILLED=0
TOTAL=0
declare -a SURVIVED=()
for m in "${MUTANTS[@]}"; do
    status="$(cat "$OUT/$m.status" 2>/dev/null || echo MISSING)"
    case "$status" in
        MISSING)
            echo "[selftest]   $m missing — skipped" ;;
        PASSED)
            TOTAL=$((TOTAL + 1))
            echo "[selftest]   $m  PASSED (missed kill!)"
            SURVIVED+=("$m") ;;
        KILLED)
            TOTAL=$((TOTAL + 1))
            KILLED=$((KILLED + 1))
            failed=$(python3 - "$OUT/$m.json" <<'EOF' 2>/dev/null || echo "?"
import json,sys
v=json.load(open(sys.argv[1]))
print(",".join(str(g["gate"]) for g in v.get("gates",[]) if not g["passed"]))
EOF
)
            echo "[selftest]   $m  killed (failed gates: $failed)" ;;
    esac
done

RATE=0
[[ $TOTAL -gt 0 ]] && RATE=$((KILLED * 100 / TOTAL))

echo ""
echo "[selftest] ============================================"
echo "[selftest] good passed       : $GOOD_PASS/$GOOD_TOTAL"
echo "[selftest] determinism       : $DET_OK/1 identical"
echo "[selftest] mutants killed    : $KILLED/$TOTAL ($RATE%)"
if [[ ${#SURVIVED[@]} -gt 0 ]]; then
    echo "[selftest] survived        : ${SURVIVED[*]}"
fi
echo "[selftest] verdicts -> $VERDICT_DIR"
echo "[selftest] ============================================"

fail=0
[[ $GOOD_PASS -ne $GOOD_TOTAL ]] && { echo "[selftest] FAIL: good did not pass"; fail=1; }
[[ $DET_FAIL -ne 0 ]] && { echo "[selftest] FAIL: verdict not deterministic at seed $SEED"; fail=1; }
[[ $RATE -lt 90 ]] && { echo "[selftest] FAIL: kill rate $RATE% < 90%"; fail=1; }
[[ $fail -eq 0 ]] && { echo "[selftest] SUCCESS"; exit 0; }
echo "[selftest] FAILURE"
exit 1
