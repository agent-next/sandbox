#!/bin/bash
# collect.sh -- run the judge for real and save every output the media needs.
#
#   bash media/collect.sh              # full: 1 good + 9 mutants + selftest
#
# Writes media/data/verdict-*.json, media/data/grade-*.txt,
# media/data/selftest.log and media/data/mutants.txt.  Nothing here
# synthesises a number: every file is the judge's own output
# (judge/grade.sh, judge/selftest.sh) or the exact mutant list
# judge/mutants.py printed.
#
# The grades and the self-test are independent (the self-test works in its
# own temp dir), so they run as two streams to use both cores; the numbers
# are identical to a serial run.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$HERE/.." && pwd)"
JUDGE="$DEMO/judge"
DATA="$HERE/data"
SEED=42

mkdir -p "$DATA"
command -v uv >/dev/null 2>&1 || {
    echo "collect.sh: uv not found; run bash judge/setup.sh first" >&2
    exit 3;
}
export PATH="$HOME/tools/bin:$PATH"

# grade <artifact-dir> <name> — a failing verdict is an expected result,
# so a non-zero exit must not stop the collection.
grade() {  # grade <artifact-dir> <name>
    if ! "$JUDGE/grade.sh" "$DEMO/$1" --seed "$SEED" \
            --json "$DATA/verdict-$2.json" > "$DATA/grade-$2.txt"; then
        echo "collect.sh: $1: judge verdict FAIL (expected for known-bad)"
    fi
}

MUT_DIR="$HERE/scratch/mutants"
rm -rf "$MUT_DIR"
python3 "$JUDGE/mutants.py" "$MUT_DIR" | tee "$DATA/mutants.txt"
NAMES=$(cat "$DATA/mutants.txt")
N=$(echo "$NAMES" | wc -l)
HALF=$(( (N + 1) / 2 ))

echo "== collect.sh: grading examples/good + the first $HALF mutants (stream A) =="
(
    grade examples/good good
    i=0
    for name in $NAMES; do
        i=$((i + 1))
        [ "$i" -gt "$HALF" ] && break
        echo "== collect.sh: grading mutant $name =="
        grade "media/scratch/mutants/$name" "$name"
    done
) > "$DATA/stream-a.log" 2>&1 &
A=$!

echo "== collect.sh: grading the last $((N - HALF)) mutants + self-test (stream B) =="
(
    i=0
    for name in $NAMES; do
        i=$((i + 1))
        [ "$i" -le "$HALF" ] && continue
        echo "== collect.sh: grading mutant $name =="
        grade "media/scratch/mutants/$name" "$name"
    done
    echo "== collect.sh: judge self-test (proves the judge can fail) =="
    "$JUDGE/selftest.sh" > "$DATA/selftest.log" 2>&1
    echo "selftest: exit ok"
) > "$DATA/stream-b.log" 2>&1 &
B=$!

rc=0
wait "$A" || { echo "collect.sh: stream A failed -- see $DATA/stream-a.log" >&2; rc=1; }
wait "$B" || { echo "collect.sh: stream B failed -- see $DATA/stream-b.log" >&2; rc=1; }
[ "$rc" -eq 0 ] || exit "$rc"

echo "collect.sh: done"
