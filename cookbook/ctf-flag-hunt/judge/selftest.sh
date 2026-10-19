#!/usr/bin/env bash
# ctf-flag-hunt self-test: prove the judge can fail.
#   1. the known-good range passes every gate
#   2. every known-bad single-edit mutant fails at least one gate
#   3. kill rate >= 90 %, else exit non-zero
#   4. same seed twice -> byte-identical verdict JSON except the `timing` key
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$JDIR/.." && pwd)"
GOOD="$DEMO/examples/good"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

echo "selftest: grading known-good $GOOD"
if bash "$JDIR/grade.sh" "$GOOD" --json "$work/good.json" \
        > "$work/good.log" 2>&1; then
    echo "selftest: known-good PASSED all gates"
else
    echo "selftest: known-good FAILED -- the judge or the example is broken" >&2
    cat "$work/good.log" >&2
    cat "$work/good.json" >&2
    exit 1
fi

python3 -I "$JDIR/mutants.py" "$GOOD" "$work/mutants" > "$work/mutants.log"
cat "$work/mutants.log"

total=0
killed=0
gates_hit=""
for m in "$work"/mutants/*/; do
    name="$(basename "$m")"
    total=$((total + 1))
    if bash "$JDIR/grade.sh" "$m" --json "$work/$name.json" > /dev/null 2>&1; then
        echo "selftest: SURVIVED  $name (judge let it pass!)"
    else
        gate="$(python3 -I -c "import json,sys;print(json.load(open(sys.argv[1])).get('failed_gate','?'))" "$work/$name.json" 2>/dev/null || echo '?')"
        echo "selftest: killed    $name (gate: $gate)"
        gates_hit="$gates_hit $gate"
        killed=$((killed + 1))
    fi
done

# Every SPEC-claimed gate must be exercised by at least one killed mutant.
python3 -I - "$gates_hit" <<'PY' || exit 1
import sys

gates = set(sys.argv[1].split())
need = {"flags", "oracle", "negative_control", "blast_radius", "build"}
missing = need - gates
if missing:
    print(f"selftest: mutant gates missing coverage of: "
          f"{','.join(sorted(missing))}", file=sys.stderr)
    raise SystemExit(1)
print(f"selftest: mutant gate coverage {len(gates)}: {','.join(sorted(gates))}")
PY

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

# --- determinism: same seed twice -> identical verdict except `timing` ---
bash "$JDIR/grade.sh" "$GOOD" --seed 1 --json "$work/det1.json" > /dev/null
bash "$JDIR/grade.sh" "$GOOD" --seed 1 --json "$work/det2.json" > /dev/null
if python3 -I - "$work/det1.json" "$work/det2.json" <<'PY'
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
a.pop("timing", None); b.pop("timing", None)
sys.exit(0 if a == b else 1)
PY
then
    echo "selftest: determinism OK (two --seed 1 runs identical except timing)"
else
    echo "selftest: DETERMINISM FAILED: grade.sh --seed 1 differs between runs" >&2
    diff <(python3 -I -c 'import json,sys;d=json.load(open(sys.argv[1]));d.pop("timing",None);print(json.dumps(d,indent=2,sort_keys=True))' "$work/det1.json") \
         <(python3 -I -c 'import json,sys;d=json.load(open(sys.argv[1]));d.pop("timing",None);print(json.dumps(d,indent=2,sort_keys=True))' "$work/det2.json") >&2 || true
    exit 1
fi
echo "selftest: OK"
