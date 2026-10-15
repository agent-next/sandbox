#!/bin/sh
# Self-test: prove the judge can fail. See SPEC.md.
#
# 1. the known-good example passes grade.sh;
# 2. every scripted single-edit mutant of it fails at least one gate;
# 3. grading is deterministic: two runs of the good batch produce
#    byte-identical verdicts (the `timing` key excluded);
# 4. judge/ checksums are unchanged after everything.
#
# Prints the kill rate; exits non-zero unless good passes, every mutant is
# killed and determinism holds.

set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
GOOD="$HERE/../examples/good/batch"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

echo "selftest: generating mutants"
MUT="$WORK/mutants"
PY="$HOME/.venvs/gpu-image-gen/bin/python"
[ -x "$PY" ] || { echo "selftest: judge venv missing; run judge/setup.sh first" >&2; exit 2; }
"$PY" "$HERE/mutants.py" "$GOOD" "$MUT" > "$WORK/names.txt"

JUDGE_SUM_BEFORE=$(cd "$HERE" && find . -type f | sort | xargs sha256sum | sha256sum)

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
    if bash "$HERE/grade.sh" "$MUT/$name" --json "$WORK/$name.json" >/dev/null 2>&1; then
        fails="$fails $name"
        echo "selftest: mutant $name: SURVIVED (judge did not kill it)" >&2
    else
        killed=$((killed + 1))
        gate=$("$PY" - "$WORK/$name.json" <<'EOF'
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

rate=$("$PY" -c "print(f'{$killed / $total * 100:.0f}')")
echo "selftest: kill rate: $killed/$total = ${rate}%"
if [ "$killed" -lt "$total" ]; then
    echo "selftest: SURVIVED mutants:$fails" >&2
fi

echo "selftest: determinism check (two grades of the good batch)"
bash "$HERE/grade.sh" "$GOOD" --json "$WORK/det1.json" >/dev/null 2>&1
bash "$HERE/grade.sh" "$GOOD" --json "$WORK/det2.json" >/dev/null 2>&1
if "$PY" - "$WORK/det1.json" "$WORK/det2.json" <<'EOF'
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

JUDGE_SUM_AFTER=$(cd "$HERE" && find . -type f | sort | xargs sha256sum | sha256sum)
if [ "$JUDGE_SUM_BEFORE" != "$JUDGE_SUM_AFTER" ]; then
    echo "selftest: judge/ checksums changed during self-test" >&2
    exit 1
fi

[ "$rate" -ge 90 ] || { echo "selftest: kill rate below 90%" >&2; exit 1; }
echo "selftest: ok"
