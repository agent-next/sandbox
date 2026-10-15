#!/usr/bin/env bash
# usd-validate-fix self-test: prove the judge can fail.
#   1. the known-good artifact passes every gate
#   2. every known-bad single-edit mutant fails at least one gate
#   3. kill rate >= 90 %, else exit non-zero
#   4. two grade.sh runs of the same artifact are byte-identical
#      (excluding the `timing` key)
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$JDIR/.." && pwd)"
VENV="$HOME/.usd-validate-fix-venv"
GOOD="$DEMO/examples/good/traffic_cone_fixed.usda"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

echo "selftest: grading known-good $GOOD"
if bash "$JDIR/grade.sh" "$GOOD" --json "$work/good.json" > /dev/null; then
    echo "selftest: known-good PASSED all gates"
else
    echo "selftest: known-good FAILED -- the judge or the example is broken" >&2
    cat "$work/good.json" >&2 || true
    exit 1
fi

"$VENV/bin/python" -I "$JDIR/mutants.py" "$GOOD" "$work/mutants"

total=0
killed=0
# The gates grade_engine.py can name.  A verdict whose failed_gate is not in
# this set -- or whose JSON is missing -- means the mutant died by a crash,
# not by a judging gate, and that is NOT a kill (DEMO-STANDARD: "Every mutant
# must be killed BY A JUDGE GATE ... not by the artifact crashing").
GATES="validator,oracle,geometry,up_axis,recount"

# killed_by <verdict.json>: prints "<gate> <n-errors>" when the verdict
# exists, its failed_gate is a real judging gate and that gate reported
# errors; prints the reason it is not a kill and exits 1 otherwise.
killed_by() {
    python3 -I "$JDIR/kill_check.py" "$1" "$GATES"
}

for m in "$work"/mutants/*.usda; do
    name="$(basename "$m" .usda)"
    total=$((total + 1))
    rc=0
    bash "$JDIR/grade.sh" "$m" --json "$work/$name.json" > /dev/null 2>&1 || rc=$?
    if [ "$rc" -eq 0 ]; then
        echo "selftest: SURVIVED  $name (judge let it pass!)"
        continue
    fi
    out="$(killed_by "$work/$name.json" 2>/dev/null)" || {
        echo "selftest: CRASHED   $name (rc=$rc, ${out:-no verdict JSON}) -- not counted as a kill" >&2
        echo "selftest: CRASHED   $name (rc=$rc, ${out:-no verdict JSON})"
        continue
    }
    gate="${out%% *}"
    nerr="${out##* }"
    echo "selftest: killed    $name (gate: $gate, $nerr error(s))"
    killed=$((killed + 1))
done

rate="$(python3 -I -c "print(f'{$killed/$total:.0%}' if $total else 'n/a')")"
echo "selftest: kill rate $killed/$total = $rate"
if [ "$total" -lt 5 ]; then
    echo "selftest: fewer than 5 mutants" >&2
    exit 1
fi
if [ $((killed * 10)) -lt $((total * 9)) ]; then
    echo "selftest: kill rate below 90%" >&2
    exit 1
fi

# --- determinism: the verdict body must not change between runs -----------
bash "$JDIR/grade.sh" "$GOOD" --seed 1 --json "$work/det1.json" > /dev/null
bash "$JDIR/grade.sh" "$GOOD" --seed 1 --json "$work/det2.json" > /dev/null
if python3 -I -c "
import json, sys
a = json.load(open(sys.argv[1])); a.pop('timing', None)
b = json.load(open(sys.argv[2])); b.pop('timing', None)
sys.exit(0 if a == b else 1)" "$work/det1.json" "$work/det2.json"; then
    echo "selftest: determinism OK (two --seed 1 runs identical except timing)"
else
    echo "selftest: DETERMINISM FAILED: grade.sh --seed 1 differs between runs" >&2
    exit 1
fi
echo "selftest: OK"
