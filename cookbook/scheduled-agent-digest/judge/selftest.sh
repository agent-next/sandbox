#!/usr/bin/env bash
# cookbook/scheduled-agent-digest self-test: prove the judge can fail.
#
# 1. the known-good example must pass every gate
# 2. every single-edit mutant of it must fail at least one gate
# 3. determinism: same seed -> identical verdict JSON (except timing)
# 4. prints the kill rate; exits non-zero if kill rate < 90 %
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GOOD="${HERE}/../examples/good"
MUTDIR="$(mktemp -d)/mutants"
LOGDIR="$(mktemp -d)"

fail_banner() { echo "selftest: $*" >&2; }

# --- 1. known-good must pass -------------------------------------------
if ! bash "$HERE/grade.sh" "$GOOD" --json "$LOGDIR/good.json" >"$LOGDIR/good.log" 2>&1; then
    fail_banner "known-good example FAILED the judge:"
    cat "$LOGDIR/good.log" >&2
    exit 1
fi
echo "selftest: known-good PASS"

# --- 2. every mutant must fail -----------------------------------------
python3 "$HERE/mutants.py" --list >/dev/null
python3 "$HERE/mutants.py" "$GOOD" "$MUTDIR" >/dev/null

nmut=0
killed=0
for m in "$MUTDIR"/*/; do
    name="$(basename "$m")"
    nmut=$((nmut + 1))
    if bash "$HERE/grade.sh" "$m" --json "$LOGDIR/${name}.json" >"$LOGDIR/${name}.log" 2>&1; then
        fail_banner "mutant ESCAPED: $name (judge passed on a bad artifact)"
        echo "--- ${name}.log ---" >&2
        cat "$LOGDIR/${name}.log" >&2
    else
        gate="$(python3 -c "
import json,sys
try:
    v=json.load(open('$LOGDIR/${name}.json'))
    print(v.get('failed_gate') or '?')
except Exception:
    print('?')
")"
        echo "selftest: mutant KILLED: $name (failed gate: $gate)"
        killed=$((killed + 1))
    fi
done

rate=0
if [ "$nmut" -gt 0 ]; then
    rate=$(awk -v k="$killed" -v n="$nmut" 'BEGIN{printf "%.0f", 100*k/n}')
fi
echo "selftest: kill rate ${killed}/${nmut} (${rate}%)"

if [ "$nmut" -lt 5 ]; then
    fail_banner "need >= 5 known-bad examples; only $nmut present"
    exit 1
fi
if [ "$rate" -lt 90 ]; then
    fail_banner "kill rate ${rate}% < 90%"
    exit 1
fi

# --- 3. determinism: same seed -> identical verdict (except timing) ---
SEED=999999
bash "$HERE/grade.sh" "$GOOD" --seed "$SEED" --json "$LOGDIR/det1.json" >"$LOGDIR/det1.log" 2>&1
bash "$HERE/grade.sh" "$GOOD" --seed "$SEED" --json "$LOGDIR/det2.json" >"$LOGDIR/det2.log" 2>&1

python3 -c "
import json, sys
v1 = json.load(open('$LOGDIR/det1.json'))
v2 = json.load(open('$LOGDIR/det2.json'))
v1.pop('timing', None)
v2.pop('timing', None)
if v1 != v2:
    print('selftest: determinism FAILED: verdicts differ for same seed', file=sys.stderr)
    sys.exit(1)
print('selftest: determinism PASS (same seed -> identical verdict)')
" || exit 1

echo "selftest: PASS"
