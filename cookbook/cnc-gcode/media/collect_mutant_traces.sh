#!/usr/bin/env bash
# Regenerate media/data/trace_mut/<name>/ for the mutant shots of demo.mp4.
#
# Each mutant is re-created from examples/good/cam.py with the judge's own
# judge/mutate.py, graded by the judge (grade.sh --trace) with the same seed
# the accepted replay verdicts used, and the fresh verdict is compared to the
# accepted one in media/data/replay/02_<name>.json (everything except the
# timing block must be identical).  Only then is the trace copied into
# media/data/ -- no number or shape here is synthesised.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "$HERE")"
REPLAY="$HERE/data/replay"
OUT="$HERE/data/trace_mut"
SEED="20261014"

[ -x "${HOME}/.cnc-gcode/venv/bin/python" ] || {
    echo "collect_mutant_traces: judge venv missing -- run 'bash judge/setup.sh'" >&2
    exit 1
}
[ -f "$REPLAY/01_good.json" ] || {
    echo "collect_mutant_traces: $REPLAY/01_good.json missing" >&2
    exit 1
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

python3 "$DEMO/judge/mutate.py" "$DEMO/examples/good/cam.py" "$TMP/mutants"

mkdir -p "$OUT"
for m in "$TMP/mutants"/*.py; do
    name="$(basename "$m" .py)"
    verdict="$REPLAY/02_${name}.json"
    [ -f "$verdict" ] || {
        echo "collect_mutant_traces: no accepted verdict $verdict" >&2
        exit 1
    }
    trace="$TMP/trace_${name}"
    mkdir -p "$trace"
    rc=0
    bash "$DEMO/judge/grade.sh" "$m" --seed "$SEED" \
        --json "$TMP/${name}.json" --trace "$trace" || rc=$?
    [ $rc -ne 0 ] || {
        echo "collect_mutant_traces: $name PASSED the judge?!" >&2
        exit 1
    }
    # the fresh verdict must equal the accepted one except for the timing
    # block and the artifact label (grade.sh echoes the scratch path it was
    # given; this run's mktemp dir differs from the original collection run's)
    if ! python3 - "$TMP/${name}.json" "$verdict" <<'EOF'
import json, sys
a = json.load(open(sys.argv[1]))
b = json.load(open(sys.argv[2]))
for v in (a, b):
    v.pop("timing", None)
    v.pop("artifact", None)
sys.exit(0 if a == b else 1)
EOF
    then
        echo "collect_mutant_traces: $name verdict changed vs accepted " \
             "media/data/replay -- refusing to ship the trace" >&2
        exit 1
    fi
    # mutants that fail before the simulation (e.g. inch_mode at the units
    # gate) have no trace to ship; the verdict check above already passed
    if [ -f "$trace/moves.json" ]; then
        rm -rf "$OUT/$name"
        mkdir -p "$OUT/$name"
        cp "$trace/moves.json" "$trace/events.npz" "$trace/final.npz" \
           "$trace/meta.json" "$trace/records.csv" "$OUT/$name/"
        echo "collect_mutant_traces: $name -> media/data/trace_mut/$name " \
             "(verdict matches accepted replay JSON)"
    else
        echo "collect_mutant_traces: $name fails before simulation; " \
             "verdict matches accepted replay JSON (card shot)"
    fi
done
echo "collect_mutant_traces: done"
