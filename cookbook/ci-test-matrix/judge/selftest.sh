#!/bin/bash
# Self-test for the ci-test-matrix judge.
#
# 1. the known-good artifact must pass every gate;
# 2. every known-bad mutant (judge/mutants.py) must fail >= 1 gate;
# 3. the kill rate must be >= 90%;
# 4. grading the good artifact twice with the same seed must give
#    byte-identical verdict JSON except the "timing" key;
# 5. judge/ must be unchanged (checksummed before and after).
#
# Exits non-zero if any of those fail.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GOOD="$DEMO_DIR/examples/good"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

NEED_TOTAL=5          # SPEC.md names 5 mutants; mutants.py generates more
MIN_KILL_RATE=90

# The artifact under test must never modify the judge: checksum before/after.
judge_hash() { find "$SCRIPT_DIR" -type f -print0 \
    | LC_ALL=C sort -z \
    | xargs -0 sha256sum \
    | sha256sum | cut -d' ' -f1; }
HASH_BEFORE=$(judge_hash)

failing_gates() {  # failing_gates <verdict.json> -> comma-separated gate names
    python3 - "$1" <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("no verdict (judge crashed)")
    raise SystemExit
bad = [k for k, v in d.get("gates", {}).items() if not v["pass"]]
print(", ".join(bad) if bad else "(all gates passed)")
PY
}

echo "== selftest: known-good artifact =="
if "$SCRIPT_DIR/grade.sh" "$GOOD" --seed 42 --json "$WORK/good.json" \
        > "$WORK/good.txt" 2>&1; then
    echo "known-good: PASS (expected)"
else
    echo "known-good: FAIL (unexpected)" >&2
    tail -40 "$WORK/good.txt" >&2
    exit 1
fi

echo "== selftest: generating known-bad mutants =="
python3 "$SCRIPT_DIR/mutants.py" "$WORK/mutants" > "$WORK/mutants.list"
LISTED=$(wc -l < "$WORK/mutants.list")
echo "$LISTED mutants generated"

total=0
killed=0
declare -a survived=()
for d in "$WORK/mutants"/*/; do
    name=$(basename "$d")
    total=$((total + 1))
    if timeout 3600 "$SCRIPT_DIR/grade.sh" "$d" --seed 42 \
            --json "$WORK/$name.json" > "$WORK/$name.txt" 2>&1; then
        echo "mutant $name: PASS (unexpected)" >&2
        survived+=("$name")
    else
        killed=$((killed + 1))
        echo "mutant $name: FAIL (expected) -- killed by gate: $(failing_gates "$WORK/$name.json")"
    fi
done

kill_rate=$(python3 -c "print(100*$killed//$total)")
echo "== selftest summary =="
echo "mutants: $total listed, $total graded"
echo "kill rate: $killed/$total (${kill_rate}%)"

if [ "$total" -lt "$NEED_TOTAL" ]; then
    echo "expected at least $NEED_TOTAL mutants" >&2
    exit 1
fi
if [ "$kill_rate" -lt "$MIN_KILL_RATE" ]; then
    echo "kill rate below ${MIN_KILL_RATE}%" >&2
    exit 1
fi

echo "== selftest: determinism (grade the good artifact twice with --seed 42) =="
"$SCRIPT_DIR/grade.sh" "$GOOD" --seed 42 --json "$WORK/det1.json" >/dev/null
"$SCRIPT_DIR/grade.sh" "$GOOD" --seed 42 --json "$WORK/det2.json" >/dev/null
if python3 - "$WORK/det1.json" "$WORK/det2.json" <<'PY'
import json, sys
def load(p):
    d = json.load(open(p))
    d.pop("timing", None)
    return d
raise SystemExit(0 if load(sys.argv[1]) == load(sys.argv[2]) else 1)
PY
then
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
