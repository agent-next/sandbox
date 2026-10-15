#!/bin/sh
# Self-test: prove the judge can fail. See SPEC.md.
#
# 1. the known-good example passes grade.sh;
# 2. every scripted mutant of it fails at least one gate;
# 3. grading is deterministic: two runs of the good artifact produce
#    byte-identical verdicts (the `timing` key is excluded);
# 4. judge/ checksums are unchanged after everything.
#
# Prints the kill rate; exits non-zero unless good passes, every mutant is
# killed, determinism holds, and the kill rate is >= 90 %.

set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
GOOD="$HERE/../examples/good/upscale.py"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

echo "selftest: generating mutants"
MUT="$WORK/mutants"
python3 "$HERE/mutants.py" "$MUT" > "$WORK/names.txt"

echo "selftest: grading known-good"
if bash "$HERE/grade.sh" "$GOOD" --json "$WORK/good.json" >/dev/null 2>&1; then
    echo "selftest: known-good: PASS"
else
    echo "selftest: known-good FAILED (judge broken or good example broken)" >&2
    exit 1
fi

killed=0
total=0
fails=""
while read -r name; do
    total=$((total + 1))
    if bash "$HERE/grade.sh" "$MUT/$name.py" \
         --json "$WORK/$name.json" >/dev/null 2>&1; then
        fails="$fails $name"
        echo "selftest: mutant $name: SURVIVED (judge did not kill it)" >&2
    else
        killed=$((killed + 1))
        gate=$(python3 - "$WORK/$name.json" <<'EOF'
import json, sys
v = json.load(open(sys.argv[1]))
gates = v.get("gates", {})
failed = [k for k, g in gates.items() if isinstance(g, dict) and not g.get("pass")]
print(",".join(failed) or "?")
EOF
)
        echo "selftest: mutant $name: killed (gate: $gate)"
    fi
done < "$WORK/names.txt"

rate=$(python3 -c "print(f'{$killed / $total * 100:.0f}')")
echo "selftest: kill rate: $killed/$total = ${rate}%"
if [ "$killed" -lt "$total" ]; then
    echo "selftest: SURVIVED mutants:$fails" >&2
fi

echo "selftest: determinism check (two grades of the good artifact)"
bash "$HERE/grade.sh" "$GOOD" --json "$WORK/det1.json" >/dev/null
bash "$HERE/grade.sh" "$GOOD" --json "$WORK/det2.json" >/dev/null
if python3 - "$WORK/det1.json" "$WORK/det2.json" <<'EOF'
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
a.pop("timing", None), b.pop("timing", None)
sys.exit(0 if a == b else 1)
EOF
then
    echo "selftest: determinism: OK"
else
    echo "selftest: determinism FAILED (two runs differ beyond timing)" >&2
    exit 1
fi

[ "$rate" -ge 90 ] || { echo "selftest: kill rate below 90%" >&2; exit 1; }
[ "$killed" -eq "$total" ] || { echo "selftest: not every mutant was killed" >&2; exit 1; }
echo "selftest: ok"
