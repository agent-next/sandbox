#!/bin/bash
# Self-test for the 3dprint-gcode judge (per DEMO-STANDARD.md):
#   1. the known-good artifact must pass;
#   2. every known-bad mutant must fail at least one gate (kill rate >= 90%);
#   3. grading twice with the same seed is byte-identical except for "timing";
#   4. judge/ is not modified by grading (sha256 before/after).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GOOD="$DEMO_DIR/examples/good"
BAD_DIR="$(mktemp -d)"
trap 'rm -rf "$BAD_DIR"' EXIT

judge_hash() { find "$SCRIPT_DIR" -type f -exec sha256sum {} + | sha256sum | cut -d' ' -f1; }
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
if "$SCRIPT_DIR/grade.sh" "$GOOD" --seed 42 --json "$BAD_DIR/good.json" >/dev/null 2>&1; then
    echo "known-good: PASS (expected)"
else
    echo "known-good: FAIL (unexpected)" >&2
    exit 1
fi

echo "== selftest: generating known-bad mutants =="
python3 "$SCRIPT_DIR/mutants.py" "$BAD_DIR" || exit 1

total=0; killed=0
for d in "$BAD_DIR"/*/; do
    name=$(basename "$d")
    [ "$name" = "good" ] && continue
    total=$((total + 1))
    if "$SCRIPT_DIR/grade.sh" "$d" --seed 42 --json "$BAD_DIR/$name.json" >/dev/null 2>&1; then
        echo "mutant $name: PASS (unexpected)" >&2
    else
        killed=$((killed + 1))
        echo "mutant $name: FAIL (expected) -- killed by gate: $(failing_gates "$BAD_DIR/$name.json")"
    fi
done

kill_rate=$(python3 -c "print(100*$killed//$total)")
echo "== selftest summary =="
echo "known-good: passed"
echo "kill rate: $killed/$total ($kill_rate%)"
[ "$kill_rate" -ge 90 ] || { echo "kill rate below 90%" >&2; exit 1; }

echo "== selftest: determinism (grade twice with --seed 42) =="
"$SCRIPT_DIR/grade.sh" "$GOOD" --seed 42 --json "$BAD_DIR/det1.json" >/dev/null 2>&1
"$SCRIPT_DIR/grade.sh" "$GOOD" --seed 42 --json "$BAD_DIR/det2.json" >/dev/null 2>&1
if python3 -c '
import json, sys
def load(p):
    d = json.load(open(p)); d.pop("timing", None); return d
sys.exit(0 if load(sys.argv[1]) == load(sys.argv[2]) else 1)
' "$BAD_DIR/det1.json" "$BAD_DIR/det2.json"; then
    echo "determinism: PASS (two --seed 42 runs identical excluding \"timing\")"
else
    echo "determinism: FAIL (two --seed 42 runs differ beyond the timing key)" >&2
    exit 1
fi

HASH_AFTER=$(judge_hash)
if [ "$HASH_BEFORE" != "$HASH_AFTER" ]; then
    echo "judge/ was modified during grading" >&2
    exit 1
fi
echo "selftest: PASS"
exit 0
