#!/usr/bin/env bash
# Regenerate every file in media/data/ from real judge runs in THIS sandbox.
#
# Nothing here is synthesised: bench.py runs the 48 (arm, task) pairs again,
# mutants.py rewrites the known-bad records and mutated judges, grade.sh
# writes one verdict JSON per record, selftest.sh proves the judge can fail.
# The "agent loop" (bad -> partly fixed -> good) is a REPLAY of graded
# records, not a live trace: the three records it grades in sequence are
# mutants.py's scripted known-bad records plus the fresh bench run.
#
# Usage: bash media/replay_judge.sh        (from cookbook/skill-ab-bench/)
set -euo pipefail

DEMO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA="$DEMO/media/data"
SEED="${SEED:-20261014}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

mkdir -p "$DATA"
: > "$DATA/bench-run.log"

echo "replay: setup"
bash "$DEMO/judge/setup.sh" > "$work/setup.log"
tail -1 "$work/setup.log"

echo "replay: fresh bench run (seed $SEED)"
python3 -I "$DEMO/judge/bench.py" "$work/bench" --seed "$SEED" \
    2>&1 | tee "$DATA/bench-run.log"
cp "$work/bench/results.json" "$DATA/bench-fresh-results.json"

echo "replay: grade known-good examples/good"
bash "$DEMO/judge/grade.sh" "$DEMO/examples/good" --seed "$SEED" \
    --json "$DATA/verdict-good.json" > "$work/vg.json"
echo "  verdict-good.json: $(jq -r .verdict "$DATA/verdict-good.json")"

echo "replay: grade the fresh bench record"
bash "$DEMO/judge/grade.sh" "$work/bench" --seed "$SEED" \
    --json "$DATA/verdict-bench-fresh.json" > "$work/vb.json"
echo "  verdict-bench-fresh.json: $(jq -r .verdict "$DATA/verdict-bench-fresh.json")"

echo "replay: write the known-bad mutants, grade every one"
python3 -I "$DEMO/judge/mutants.py" "$DEMO/examples/good" "$work/mutants" \
    | tee "$DATA/mutants.log"
for m in "$work"/mutants/records/*/; do
    name="$(basename "$m")"
    bash "$DEMO/judge/grade.sh" "$m" --seed "$SEED" \
        --json "$DATA/verdict-$name.json" > "$work/v-$name.json" || true
    echo "  verdict-$name.json: $(jq -r '"\(.verdict) \(.failed_gate)"' \
        "$DATA/verdict-$name.json")"
done
for m in "$work"/mutants/judge/*/; do
    name="$(basename "$m")"
    bash "$DEMO/judge/grade.sh" "$DEMO/examples/good" --seed "$SEED" \
        --judge-dir "$m" --json "$DATA/verdict-judge-$name.json" \
        > "$work/vj-$name.json" || true
    echo "  verdict-judge-$name.json: $(jq -r '"\(.verdict) \(.failed_gate)"' \
        "$DATA/verdict-judge-$name.json")"
done

echo "replay: self-test (kill rate + determinism)"
bash "$DEMO/judge/selftest.sh" 2>&1 | tee "$DATA/selftest.log" | tail -4

echo "replay: done — data in $DATA"
