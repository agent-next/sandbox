#!/bin/bash
# Collect the real judge outputs the media is built from, into media/data/:
#   verdicts/     grade.sh --json verdicts for the good example and every
#                 mutant, in the replay order a fixing agent would hit
#                 them (bad -> partly fixed -> good)
#   traces/       grade.sh --trace S11 sweep CSVs, one <case>__ prefix
#                 per graded artifact (only sim-bearing grades emit them)
#   grade_logs/   the [PASS]/[FAIL] gate lines of each grade run
#   selftest.txt  one full judge/selftest.sh run (kill rate + determinism)
#
# Requires judge/setup.sh to have run once. The collected files are
# committed; make_media.sh reuses them and never re-runs the solver.
# Idempotent: a case whose verdict JSON already exists is skipped
# (FORCE=1 bash media/make_data.sh re-collects everything).
set -euo pipefail
MEDIA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "$MEDIA")"
cd "$DEMO"
source judge/env.sh

VD="$MEDIA/data/verdicts"
TR="$MEDIA/data/traces"
GL="$MEDIA/data/grade_logs"
mkdir -p "$VD" "$TR" "$GL"

"$RF_PY" judge/mutants.py generate >/dev/null

# grade one artifact, save verdict JSON + S11 traces + gate log.
# run <case-name> <artifact> <pass|fail (expected)>
run() {
    local name="$1" art="$2" expect="$3" rc=0 trt
    if [ "${FORCE:-0}" != 1 ] && [ -s "$VD/$name.json" ]; then
        echo "== grade $name: verdict exists, skipping =="
        return 0
    fi
    trt="$(mktemp -d)"
    echo "== grade $name (expect $expect) =="
    if bash judge/grade.sh "$art" --json "$VD/$name.json" \
            --trace "$trt" >"$GL/$name.log" 2>&1; then
        rc=0
    else
        rc=$?
    fi
    for f in "$trt"/*.csv; do
        if [ -e "$f" ]; then mv "$f" "$TR/${name}__$(basename "$f")"; fi
    done
    rm -rf "$trt"
    if [ "$expect" = pass ] && [ "$rc" -ne 0 ]; then
        echo "make_data: $name expected PASS, got rc=$rc (see $GL/$name.log)" >&2
        exit 1
    fi
    if [ "$expect" = fail ] && [ "$rc" -eq 0 ]; then
        echo "make_data: $name expected FAIL but passed" >&2
        exit 1
    fi
    echo "   -> rc=$rc, verdict + traces saved"
}

# replay order a fixing agent plausibly works through: parameter-block and
# sanity mistakes first (killed before any sim), then geometry mistakes
# (sim runs but misses the spec), then the feed match, then the good design.
run bad_nan_er          examples/bad/bad_nan_er.py          fail
run bad_substrate_er    examples/bad/bad_substrate_er.py    fail
run bad_thick_substrate examples/bad/bad_thick_substrate.py fail
run bad_coarse_mesh     examples/bad/bad_coarse_mesh.py     fail
run bad_patch_length    examples/bad/bad_patch_length.py    fail
run bad_no_ground       examples/bad/bad_no_ground.py       fail
run bad_feed_center     examples/bad/bad_feed_center.py     fail
run bad_no_result       examples/bad/bad_no_result.py       fail
run bad_lie_scalars     examples/bad/bad_lie_scalars.py     fail
run bad_replay_cached   examples/bad/bad_replay_cached.py   fail
run bad_fake_curve      examples/bad/bad_fake_curve.py      fail
run bad_oracle_tamper   examples/bad/bad_oracle_tamper.py   fail
run bad_fine_geometry   examples/bad/bad_fine_geometry.py   fail
run bad_fine_fabricated examples/bad/bad_fine_fabricated.py fail
run bad_plant_pyc       examples/bad/bad_plant_pyc.py       fail
run good                examples/good/antenna.py            pass

if [ "${FORCE:-0}" = 1 ] || [ ! -s "$MEDIA/data/selftest.txt" ]; then
    echo "== selftest (good + 15 mutants + determinism, ~25-35 min) =="
    bash judge/selftest.sh 2>&1 | tee "$MEDIA/data/selftest.txt"
else
    echo "== selftest: log exists, skipping =="
fi

echo "make_data: judge outputs collected in $MEDIA/data"
