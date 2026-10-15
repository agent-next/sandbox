#!/bin/bash
# collect.sh -- run the judge for real and save every output the media needs.
#
#   bash media/collect.sh              # full: 12 grade.sh runs + selftest (~12 min)
#   bash media/collect.sh quick        # 1 good + 2 mutants + selftest smoke (~2 min)
#
# Writes media/data/verdict-*.json, media/data/selftest.log and
# media/data/mutants.txt.  Nothing here synthesises a number: every file is
# the judge's own output (judge/grade.sh, judge/selftest.sh) or the exact
# mutant list judge/mutants.py printed.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$HERE/.." && pwd)"
JUDGE="$DEMO/judge"
DATA="$HERE/data"
SEED=42
QUICK=0
[ "${1:-}" = "quick" ] && QUICK=1

mkdir -p "$DATA"
command -v uv >/dev/null 2>&1 || {
    echo "collect.sh: uv not found; run bash judge/setup.sh first" >&2
    exit 3;
}
export PATH="$HOME/tools/bin:$PATH"

grade() {  # grade <artifact-dir> <name>
    "$JUDGE/grade.sh" "$DEMO/$1" --seed "$SEED" \
        --json "$DATA/verdict-$2.json" > "$DATA/grade-$2.txt"
}

MUT_DIR="$HERE/scratch/mutants"
rm -rf "$MUT_DIR"
python3 "$JUDGE/mutants.py" "$MUT_DIR" | tee "$DATA/mutants.txt"

echo "== collect.sh: grading examples/good =="
grade examples/good good

NAMES=$(cat "$DATA/mutants.txt")
if [ "$QUICK" -eq 0 ]; then
    for name in $NAMES; do
        echo "== collect.sh: grading mutant $name =="
        grade "scratch/mutants/$name" "$name"
    done
else
    for name in $(echo "$NAMES" | head -3); do
        echo "== collect.sh: quick mode: grading mutant $name =="
        grade "scratch/mutants/$name" "$name"
    done
fi

echo "== collect.sh: judge self-test (proves the judge can fail) =="
"$JUDGE/selftest.sh" > "$DATA/selftest.log" 2>&1

echo "collect.sh: done"
