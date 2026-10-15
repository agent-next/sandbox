#!/usr/bin/env bash
# background-coding-agent self-test: prove the judge can fail.
#   1. the known-good delivery passes every gate
#   2. every known-bad single-edit mutant fails at least one gate
#   3. kill rate >= 90 %, else exit non-zero
#   4. same seed twice -> byte-identical verdict JSON
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$JDIR/.." && pwd)"
GOOD="$DEMO/examples/good/delivery.patch"
GOOD_PR="$DEMO/examples/good/PR.md"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

echo "selftest: grading known-good $GOOD"
if bash "$JDIR/grade.sh" "$GOOD" --pr "$GOOD_PR" --json "$work/good.json" \
        > /dev/null; then
    echo "selftest: known-good PASSED all gates"
else
    echo "selftest: known-good FAILED -- the judge or the example is broken" >&2
    cat "$work/good.json" >&2
    exit 1
fi

python3 -I "$JDIR/mutants.py" "$GOOD" "$GOOD_PR" "$work/mutants" \
    > "$work/mutants.log"
cat "$work/mutants.log"

total=0
killed=0
for m in "$work"/mutants/*/; do
    name="$(basename "$m")"
    total=$((total + 1))
    if bash "$JDIR/grade.sh" "$m/delivery.patch" --pr "$m/PR.md" \
            --json "$work/$name.json" > /dev/null 2>&1; then
        echo "selftest: SURVIVED  $name (judge let it pass!)"
    else
        gate="$(python3 -I -c "import json,sys;print(json.load(open(sys.argv[1])).get('failed_gate','?'))" "$work/$name.json" 2>/dev/null || echo '?')"
        echo "selftest: killed    $name (gate: $gate)"
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
bash "$JDIR/grade.sh" "$GOOD" --pr "$GOOD_PR" --seed 1 --json "$work/det1.json" > /dev/null
bash "$JDIR/grade.sh" "$GOOD" --pr "$GOOD_PR" --seed 1 --json "$work/det2.json" > /dev/null
if cmp -s "$work/det1.json" "$work/det2.json"; then
    echo "selftest: determinism OK (two --seed 1 runs byte-identical)"
else
    echo "selftest: DETERMINISM FAILED: grade.sh --seed 1 differs between runs" >&2
    diff "$work/det1.json" "$work/det2.json" >&2 || true
    exit 1
fi
echo "selftest: OK"
