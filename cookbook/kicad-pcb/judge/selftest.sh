#!/usr/bin/env bash
# judge/selftest.sh — verify the judge itself.
#
#  1. checksum judge/ before and after (artifact must not modify judge)
#  2. known-good project passes, graded twice -> identical verdict JSON
#     (determinism; no volatile fields in the verdict)
#  3. every scripted mutant fails at least one gate; kill rate >= 90%
#
# Exit 0 iff all checks hold.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(dirname "$SCRIPT_DIR")"
GOOD_DIR="$DEMO_DIR/examples/good/555-blinker"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

judge_sum() {
    find "$SCRIPT_DIR" -type f \( -name '*.sh' -o -name '*.py' \) \
        | sort | xargs sha256sum
}

BEFORE=$(judge_sum)

echo "=== selftest: grade known-good (run 1)"
bash "$SCRIPT_DIR/grade.sh" "$GOOD_DIR" --json "$WORK/good1.json" || {
    echo "FAIL: good project did not pass"; exit 1; }

echo "=== selftest: grade known-good (run 2, determinism)"
bash "$SCRIPT_DIR/grade.sh" "$GOOD_DIR" --json "$WORK/good2.json" || {
    echo "FAIL: good project did not pass on rerun"; exit 1; }
if cmp -s "$WORK/good1.json" "$WORK/good2.json"; then
    echo "    determinism: identical verdict JSON"
else
    echo "FAIL: verdict JSON differs between identical runs"; exit 1
fi

echo "=== selftest: mutants"
python3 "$SCRIPT_DIR/mutants.py" "$GOOD_DIR" "$WORK/mutants"

TOTAL=0
KILLED=0
for mdir in "$WORK/mutants"/*/; do
    name=$(basename "$mdir")
    TOTAL=$((TOTAL + 1))
    if bash "$SCRIPT_DIR/grade.sh" "$mdir" --json "$WORK/$name.json" \
            >"$WORK/$name.log" 2>&1; then
        echo "    $name: SURVIVED (bad)"; cat "$WORK/$name.log"
    else
        failed=$(python3 -c "
import json,sys
v=json.load(open('$WORK/$name.json'))
print(' '.join(k for k,g in v['gates'].items() if not g['pass']))" \
            2>/dev/null || echo "?")
        echo "    $name: killed (failed: $failed)"
        KILLED=$((KILLED + 1))
    fi
done

RATE=$((KILLED * 100 / TOTAL))
echo "=== selftest: kill rate $KILLED/$TOTAL = ${RATE}%"

AFTER=$(judge_sum)
[[ "$BEFORE" == "$AFTER" ]] || { echo "FAIL: judge/ changed during grading"; exit 1; }
echo "=== selftest: judge/ checksum unchanged"

if [[ $RATE -ge 90 ]]; then
    echo "SELFTEST PASS"
    exit 0
fi
echo "SELFTEST FAIL (kill rate < 90%)"
exit 1
