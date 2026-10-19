#!/usr/bin/env bash
# Self-test for the backtest-equity judge (cookbook/DEMO-STANDARD.md).
#
#   1. the known-good artifact passes every gate
#   2. every known-bad mutant (judge/mutants.py) fails at least one gate
#      -- the kill rate is printed and must be >= 90%
#   3. determinism: two grade.sh runs with the same seed give byte-identical
#      verdict JSON except the "timing" key
#   4. judge integrity: judge/checksum before == after
#
# Exits non-zero if any of those fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GOOD="$DEMO_DIR/examples/good"
SEED=42

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# judge/VERSIONS.txt is written by judge/setup.sh (the standard requires it
# to live there); it records installs, not judge logic, so it is excluded.
# __pycache__ is created by importing judge/reference.py and is also not
# judge logic.
judge_hash() {
    find "$SCRIPT_DIR" -type f \
         ! -name VERSIONS.txt ! -path '*/__pycache__/*' -print0 \
        | LC_ALL=C sort -z \
        | xargs -0 sha256sum 2>/dev/null | sha256sum | cut -d' ' -f1
}
HASH_BEFORE=$(judge_hash)

failing_gates() {  # failing_gates <verdict.json> -> comma-separated gate names
    python3 -c '
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("no verdict (judge crashed)"); raise SystemExit
bad = [k for k, v in d.get("gates", {}).items() if not v["pass"]]
print(", ".join(bad) if bad else "(all gates passed)")
' "$1" 2>/dev/null || echo "no verdict file"
}

echo "== selftest: known-good artifact =="
if "$SCRIPT_DIR/grade.sh" "$GOOD" --seed "$SEED" --json "$WORK/good.json" >/dev/null; then
    echo "known-good: PASS (expected)"
else
    echo "known-good: FAIL (unexpected)" >&2
    "$SCRIPT_DIR/grade.sh" "$GOOD" --seed "$SEED" --json "$WORK/good-fail.json" >&2
    exit 1
fi

echo "== selftest: generating known-bad mutants =="
python3 "$SCRIPT_DIR/mutants.py" "$WORK" >"$WORK/mutant.list" || exit 1

total=0
killed=0
escaped=0
while read -r name; do
    [ -n "$name" ] || continue
    total=$((total + 1))
    if "$SCRIPT_DIR/grade.sh" "$WORK/$name" --seed "$SEED" \
            --json "$WORK/$name.json" >/dev/null 2>&1; then
        echo "mutant $name: PASS (unexpected)" >&2
        escaped=$((escaped + 1))
    else
        killed=$((killed + 1))
        echo "mutant $name: FAIL (expected) -- killed by gate: $(failing_gates "$WORK/$name.json")"
    fi
done < "$WORK/mutant.list"

kill_rate=$(python3 -c "print(100*$killed//$total)")
echo "== selftest summary =="
echo "known-good: passed"
echo "kill rate: $killed/$total ($kill_rate%)"
# a mutant that escapes the judge fails the self-test outright, whatever the
# kill rate says: an escaped mutant means a gate rule is missing its teeth
[ "$escaped" -eq 0 ] || { echo "$escaped mutant(s) escaped the judge" >&2; exit 1; }
[ "$kill_rate" -ge 90 ] || { echo "kill rate below 90%" >&2; exit 1; }

echo "== selftest: determinism (grade twice with --seed $SEED) =="
"$SCRIPT_DIR/grade.sh" "$GOOD" --seed "$SEED" --json "$WORK/det1.json" >/dev/null
"$SCRIPT_DIR/grade.sh" "$GOOD" --seed "$SEED" --json "$WORK/det2.json" >/dev/null
if python3 -c '
import json, sys
def load(p):
    with open(p) as fh:
        d = json.load(fh)
    d.pop("timing", None)
    return d
sys.exit(0 if load(sys.argv[1]) == load(sys.argv[2]) else 1)
' "$WORK/det1.json" "$WORK/det2.json"; then
    echo "determinism: PASS (two --seed $SEED runs identical excluding \"timing\")"
else
    echo "determinism: FAIL (two --seed $SEED runs differ beyond the timing key)" >&2
    exit 1
fi

HASH_AFTER=$(judge_hash)
if [ "$HASH_BEFORE" != "$HASH_AFTER" ]; then
    echo "judge/ was modified during grading" >&2
    exit 1
fi
echo "judge integrity: PASS (judge/ checksum unchanged by grading)"
echo "selftest: PASS"
exit 0
