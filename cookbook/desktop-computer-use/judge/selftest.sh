#!/usr/bin/env bash
# desktop-computer-use self-test: prove the judge can fail.
#   1. the known-good artifact passes every gate
#   2. every known-bad single-edit mutant fails at least one gate
#   3. kill rate >= 90 %, else exit non-zero
#   4. same seed twice -> byte-identical verdict JSON except `timing`
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$JDIR/.." && pwd)"
GOOD="$DEMO/examples/good/actions.py"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

echo "selftest: grading known-good $GOOD"
if bash "$JDIR/grade.sh" "$GOOD" --json "$work/good.json" > /dev/null; then
    echo "selftest: known-good PASSED all gates"
else
    echo "selftest: known-good FAILED -- the judge or the example is broken" >&2
    cat "$work/good.json" >&2
    exit 1
fi
# the good artifact must not die inside the judge itself: a "judge" failure
# here means the environment is broken, not that the artifact is bad
python3 -I -c "
import json, sys
v = json.load(open(sys.argv[1]))
if v.get('failed_gate') == 'judge':
    print('selftest: known-good died inside the judge:', v.get('reason'), file=sys.stderr)
    sys.exit(1)
" "$work/good.json"

python3 -I "$JDIR/mutants.py" "$GOOD" "$work/mutants" > "$work/mutants.log"
cat "$work/mutants.log"

total=0
killed=0
for m in "$work"/mutants/*.py; do
    name="$(basename "$m" .py)"
    total=$((total + 1))
    if bash "$JDIR/grade.sh" "$m" --json "$work/$name.json" > /dev/null 2>&1; then
        echo "selftest: SURVIVED  $name (judge let it pass!)"
    else
        gate="$(python3 -I -c "import json,sys;print(json.load(open(sys.argv[1])).get('failed_gate','?'))" "$work/$name.json" 2>/dev/null || echo '?')"
        echo "selftest: killed    $name (gate: $gate)"
        if [ "$gate" = "judge" ]; then
            echo "selftest: $name died inside the judge, not at a gate -- the" \
                 "verdict explains:" >&2
            sed 's/^/selftest: /' "$work/$name.json" >&2
        fi
        killed=$((killed + 1))
    fi
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

# --- determinism: same seed twice -> identical verdict JSON ------------
# Everything allowed to differ (wall clock, elapsed time) lives under the
# `timing` key; strip it before comparing (DEMO-STANDARD.md, "Deterministic").
bash "$JDIR/grade.sh" "$GOOD" --seed 1 --json "$work/det1.json" > /dev/null
bash "$JDIR/grade.sh" "$GOOD" --seed 1 --json "$work/det2.json" > /dev/null
if DET_SAME="$(python3 -I - "$work/det1.json" "$work/det2.json" <<'PYDET'
import json, sys
a = json.load(open(sys.argv[1]))
b = json.load(open(sys.argv[2]))
a.pop("timing", None)
b.pop("timing", None)
if not a or not b:
    raise SystemExit(1)
print("yes" if a == b else "no")
PYDET
)" && test "$DET_SAME" = "yes"; then
    echo "selftest: determinism OK (two --seed 1 runs identical modulo timing)"
else
    echo "selftest: DETERMINISM FAILED: grade.sh --seed 1 differs between runs" >&2
    diff "$work/det1.json" "$work/det2.json" >&2 || true
    exit 1
fi
echo "selftest: OK"
