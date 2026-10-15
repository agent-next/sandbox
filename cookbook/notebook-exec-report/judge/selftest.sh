#!/usr/bin/env bash
# notebook-exec-report self-test: prove the judge can fail.
#   1. the known-good artifact passes every gate
#   2. every known-bad single-edit mutant fails at least one gate
#   3. kill rate >= 90 %, else exit non-zero
#   4. same seed twice -> byte-identical verdict JSON except `timing`
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$JDIR/.." && pwd)"
GOOD="$DEMO/examples/good/analysis.ipynb"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

echo "selftest: grading known-good $GOOD"
if bash "$JDIR/grade.sh" "$GOOD" --json "$work/good.json" > /dev/null 2>&1; then
    echo "selftest: known-good PASSED all gates"
else
    echo "selftest: known-good FAILED -- the judge or the example is broken" >&2
    cat "$work/good.json" >&2
    exit 1
fi

python3 -I "$JDIR/mutants.py" "$GOOD" "$work/mutants" > "$work/mutants.log"
cat "$work/mutants.log"

total=0
killed=0
for m in "$work"/mutants/*.ipynb; do
    name="$(basename "$m" .ipynb)"
    total=$((total + 1))
    # grade.sh requires dataset.csv beside the artifact
    cp "$DEMO/examples/good/dataset.csv" "$work/mutants/dataset.csv"
    if bash "$JDIR/grade.sh" "$m" --json "$work/$name.json" > /dev/null 2>&1; then
        echo "selftest: SURVIVED  $name (judge let it pass!)"
    else
        gate="$(python3 -I -c "import json,sys;print(json.load(open(sys.argv[1])).get('failed_gate','?'))" "$work/$name.json" 2>/dev/null || echo '?')"
        reason="$(python3 -I -c "import json,sys;print(json.load(open(sys.argv[1])).get('reason','?')[:90])" "$work/$name.json" 2>/dev/null || echo '?')"
        echo "selftest: killed    $name (gate: $gate; $reason)"
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
# (excluding the wall-time fields, which live under the `timing` key)
strip_timing() {
    python3 -I -c 'import json,sys; d=json.load(open(sys.argv[1])); d.pop("timing",None); json.dump(d,sys.stdout,indent=2,sort_keys=True)' "$1"
}
bash "$JDIR/grade.sh" "$GOOD" --seed 1 --json "$work/det1.json" > /dev/null 2>&1
bash "$JDIR/grade.sh" "$GOOD" --seed 1 --json "$work/det2.json" > /dev/null 2>&1
if [ "$(strip_timing "$work/det1.json")" = "$(strip_timing "$work/det2.json")" ]; then
    echo "selftest: determinism OK (two --seed 1 runs identical except timing)"
else
    echo "selftest: DETERMINISM FAILED: grade.sh --seed 1 differs between runs" >&2
    diff <(strip_timing "$work/det1.json") <(strip_timing "$work/det2.json") >&2 || true
    exit 1
fi
echo "selftest: OK"
