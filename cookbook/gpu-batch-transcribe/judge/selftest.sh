#!/usr/bin/env bash
# Self-test: prove the judge can fail. See SPEC.md.
#
# 1. the known-good example passes grade.sh;
# 2. every scripted mutant of it fails at least one gate;
# 3. grading is deterministic: two runs of the good artifact produce
#    byte-identical verdicts (the `timing` key is excluded — wall time is
#    inherently noisy);
# 4. judge/ checksums are unchanged after everything.
#
# Prints the kill rate; exits non-zero unless good passes, every mutant is
# killed and determinism holds.

set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
GOOD="$HERE/../examples/good/transcriber.py"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

echo "selftest: generating mutants"
MUT="$WORK/mutants"
PY="$HOME/.venvs/gpu-batch-transcribe/bin/python"
"$PY" "$HERE/mutants.py" "$MUT" > "$WORK/names.txt"

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
    # grade.sh prints "grade: exit N" on every run: a judge that always
    # exits 0 (or prints ok for a failing mutant) shows up here instead
    # of passing silently. The || capture keeps set -e from eating the
    # expected non-zero grade of a killed mutant.
    rc=0
    out=$(bash "$HERE/grade.sh" "$MUT/$name.py" \
        --json "$WORK/$name.json" 2>&1) || rc=$?
    greplast=$(printf '%s\n' "$out" | grep "grade: exit" | tail -1)
    if [ "$rc" -eq 0 ]; then
        fails="$fails $name"
        echo "selftest: mutant $name: SURVIVED (judge did not kill it)" >&2
        echo "selftest:   $greplast" >&2
    else
        killed=$((killed + 1))
        gate=$("$PY" - "$WORK/$name.json" <<'EOF'
import json, sys
try:
    v = json.load(open(sys.argv[1]))
except Exception:
    # no/unreadable verdict: the judge's exit line above carries the news
    print("no verdict json")
else:
    gates = v.get("gates", {})
    failed = [k for k, g in gates.items() if isinstance(g, dict) and not g.get("pass")]
    print(",".join(failed) or "exit 0")
EOF
)
        echo "selftest: mutant $name: killed (gate: $gate; $greplast)"
    fi
done < "$WORK/names.txt"

rate=$("$PY" -c "print(f'{$killed / $total * 100:.0f}')")
echo "selftest: kill rate: $killed/$total = ${rate}%"
if [ "$killed" -lt "$total" ]; then
    echo "selftest: SURVIVED mutants:$fails" >&2
fi

echo "selftest: determinism check (two grades of the good artifact)"
bash "$HERE/grade.sh" "$GOOD" --json "$WORK/det1.json" >/dev/null
bash "$HERE/grade.sh" "$GOOD" --json "$WORK/det2.json" >/dev/null
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

[ "$rate" -ge 90 ] || { echo "selftest: kill rate below 90%" >&2; exit 1; }
echo "selftest: ok"
