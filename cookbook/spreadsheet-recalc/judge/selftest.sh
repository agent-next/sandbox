#!/bin/sh
# Self-test for the spreadsheet-recalc judge.
# Proves the judge can fail: known-good passes, every mutant fails.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
GOOD="$HERE/../examples/good/dcf_model.xlsx"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# Use the interpreter that has openpyxl: the venv setup.sh created, else
# $PYTHON, else python3. mutants.py and the gate-name helper both import it.
PY="${PYTHON:-python3}"
if [ -x "$HOME/.venvs/spreadsheet-recalc/bin/python" ]; then
    PY="$HOME/.venvs/spreadsheet-recalc/bin/python"
fi

echo "selftest: generating mutants..."
MUT="$WORK/mutants"
"$PY" "$HERE/mutants.py" "$MUT" > "$WORK/names.txt"

# 1. Known-good must pass
echo "selftest: grading known-good..."
if bash "$HERE/grade.sh" "$GOOD" --json "$WORK/good.json" >/dev/null 2>&1; then
    echo "selftest: known-good: PASS"
else
    echo "selftest: known-good FAILED" >&2
    exit 1
fi

# 2. Every mutant must fail
total=0
killed=0
while read -r name; do
    total=$((total + 1))
    if bash "$HERE/grade.sh" "$MUT/$name.xlsx" --json "$WORK/$name.json" >/dev/null 2>&1; then
        echo "selftest: mutant $name: SURVIVED" >&2
    else
        killed=$((killed + 1))
        gate=$(python3 -c "
import json, sys
v = json.load(open(sys.argv[1]))
failed = [k for k, val in v.get('gates', {}).items() if val is False]
print(','.join(failed) or '?')
" "$WORK/$name.json")
        echo "selftest: mutant $name: killed (gate: $gate)"
    fi
done < "$WORK/names.txt"

rate=$(python3 -c "print(f'{$killed / $total * 100:.0f}')")
echo "selftest: kill rate: $killed/$total = ${rate}%"

# 3. Determinism check
bash "$HERE/grade.sh" "$GOOD" --json "$WORK/det1.json" >/dev/null
bash "$HERE/grade.sh" "$GOOD" --json "$WORK/det2.json" >/dev/null
if python3 -c "
import json, sys
a = json.load(open(sys.argv[1]))
b = json.load(open(sys.argv[2]))
a.pop('timing', None)
b.pop('timing', None)
sys.exit(0 if a == b else 1)
" "$WORK/det1.json" "$WORK/det2.json"; then
    echo "selftest: determinism: OK"
else
    echo "selftest: determinism FAILED" >&2
    exit 1
fi

# 4. Kill rate threshold
if [ "$rate" -lt 90 ]; then
    echo "selftest: kill rate below 90%" >&2
    exit 1
fi

echo "selftest: ok"
