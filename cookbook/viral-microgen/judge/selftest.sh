#!/usr/bin/env bash
# viral-microgen self-test: prove the judge can fail.
#   1. the known-good artifact passes every gate
#   2. every known-bad single-edit mutant fails at least one gate
#   3. kill rate >= 90 %, else exit non-zero
#   4. same seed twice -> byte-identical verdict JSON except `timing`
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$JDIR/.." && pwd)"
GOOD="$DEMO/examples/good"
SEED="${VIRAL_SEED:-42}"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

echo "selftest: grading known-good $GOOD"
if bash "$JDIR/grade.sh" "$GOOD" --seed "$SEED" --json "$work/good.json" >/dev/null; then
    echo "selftest: known-good PASSED all gates"
else
    echo "selftest: known-good FAILED -- the judge or the example is broken" >&2
    cat "$work/good.json" >&2 || true
    exit 1
fi

bash "$JDIR/grade.sh" "$GOOD" --seed "$SEED" --json "$work/good2.json" >/dev/null
python3 - "$work/good.json" "$work/good2.json" <<'PY'
import json, sys
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
a.pop("timing", None); b.pop("timing", None)
if a != b:
    print("selftest: DETERMINISM FAILED: two grades differ", file=sys.stderr)
    sys.exit(1)
print("selftest: determinism OK (two grades byte-identical except timing)")
PY

python3 "$JDIR/mutants.py" "$GOOD" "$work/mutants" --seed "$SEED" > "$work/mutants.log"
cat "$work/mutants.log"

total=0
killed=0
survived=0
for m in "$work"/mutants/*/; do
    name="$(basename "$m")"
    total=$((total + 1))
    if bash "$JDIR/grade.sh" "$m" --seed "$SEED" --json "$work/$name.json" \
            >/dev/null 2>&1; then
        echo "selftest: SURVIVED  $name (the judge let it pass!)"
        survived=$((survived + 1))
    else
        gate="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('failed_gate') or 'validation')" "$work/$name.json" 2>/dev/null || echo '?')"
        echo "selftest: killed    $name (gate: $gate)"
        killed=$((killed + 1))
    fi
done

rate="$(python3 -c "print(f'{$killed/$total:.0%}' if $total else 'n/a')")"
echo "selftest: kill rate $killed/$total = $rate"
if [ "$total" -lt 5 ]; then
    echo "selftest: fewer than 5 mutants" >&2
    exit 1
fi
if [ $((killed * 10)) -lt $((total * 9)) ]; then
    echo "selftest: kill rate below 90%" >&2
    exit 1
fi
echo "selftest: OK"
