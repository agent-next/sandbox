#!/usr/bin/env bash
# code-interpreter-charts self-test: prove the judge can fail.
#   1. the known-good artifact passes every gate
#   2. every known-bad single-edit mutant fails at least one gate
#   3. kill rate >= 90 %, else exit non-zero
#   4. two runs on the good artifact give byte-identical verdict JSON
#      apart from the `timing` key
#
#   --verdicts DIR   also copy each verdict JSON the run produced into DIR
#                    (good.json + mutants/<name>.json); media/make_media.sh
#                    uses them so the figures carry only real judge output.
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$JDIR/.." && pwd)"
GOOD="$DEMO/examples/good"
VERDICTS=""

while [ $# -gt 0 ]; do
    case "$1" in
        --verdicts) VERDICTS="$2"; shift 2 ;;
        *) echo "selftest: unknown argument '$1'" >&2; exit 2 ;;
    esac
done
if [ -n "$VERDICTS" ]; then
    mkdir -p "$VERDICTS/mutants"
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

echo "selftest: grading known-good $GOOD"
if bash "$JDIR/grade.sh" "$GOOD" --json "$work/good.json" > /dev/null; then
    echo "selftest: known-good PASSED all gates"
    [ -z "$VERDICTS" ] || cp "$work/good.json" "$VERDICTS/good.json"
else
    echo "selftest: known-good FAILED -- the judge or the example is broken" >&2
    cat "$work/good.json" >&2
    exit 1
fi

python3 -I "$JDIR/mutants.py" "$GOOD/analysis.py" "$work/mutants" \
    > "$work/mutants.log"
cat "$work/mutants.log"

total=0
killed=0
for m in "$work"/mutants/*/; do
    name="$(basename "$m")"
    total=$((total + 1))
    if bash "$JDIR/grade.sh" "$m" --json "$work/$name.json" > /dev/null 2>&1
    then
        echo "selftest: SURVIVED  $name (judge let it pass!)"
    else
        gate="$(python3 -I -c "
import json,sys
v=json.load(open(sys.argv[1]))
print(v.get('failed_gate') or '?')
" "$work/$name.json" 2>/dev/null || echo '?')"
        echo "selftest: killed    $name (gate: $gate)"
        killed=$((killed + 1))
    fi
    [ -z "$VERDICTS" ] || cp "$work/$name.json" "$VERDICTS/mutants/$name.json"
done

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

# --- determinism: two runs differ only in `timing` ---------------------
bash "$JDIR/grade.sh" "$GOOD" --seed 1 --json "$work/det1.json" > /dev/null
bash "$JDIR/grade.sh" "$GOOD" --seed 1 --json "$work/det2.json" > /dev/null
strip_timing() {
    python3 -I -c "
import json,sys
v=json.load(open(sys.argv[1]))
v.pop('timing', None)
print(json.dumps(v, sort_keys=True))
" "$1"
}
if [ "$(strip_timing "$work/det1.json")" = "$(strip_timing "$work/det2.json")" ]
then
    echo "selftest: determinism OK (two --seed 1 runs identical but timing)"
else
    echo "selftest: DETERMINISM FAILED: verdicts differ beyond timing" >&2
    diff "$work/det1.json" "$work/det2.json" >&2 || true
    exit 1
fi
echo "selftest: OK"
