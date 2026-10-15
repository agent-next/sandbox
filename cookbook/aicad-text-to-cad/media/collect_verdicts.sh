#!/bin/bash
# Collect the real judge outputs every figure and the video are built from.
#
#   media/collect_verdicts.sh          (run after judge/setup.sh)
#
# Produces under media/data/ (git-ignored; regenerate any time):
#   verdicts/good_<part>.json   grade.sh examples/good/<part> --seed 42
#   verdicts/<mutant>.json      grade.sh <regenerated mutant> --seed 42
#   replay.txt                  the replayed fixing-agent iteration order
#                               on adapter_plate (see bottom of this file)
#   selftest.txt                the full judge/selftest.sh log
#   mutants/                    the regenerated mutant artifacts
#
# Nothing here is invented: every number the media plots comes from one of
# these JSONs or logs, each produced by the real judge in this run.
set -euo pipefail

MEDIA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "$MEDIA")"
SEED=42

VENV="${AICAD_JUDGE_VENV:-$HOME/.venvs/aicad-judge}"
[ -x "$VENV/bin/python" ] || { echo "judge venv missing -- run judge/setup.sh" >&2; exit 1; }

MUTANTS="plate-hole-count plate-hole-diameter plate-hole-drift plate-flipped-facet
         bracket-missing-fillet bracket-fillet-radius bushing-scale-25_4
         bushing-non-watertight"

mkdir -p "$MEDIA/data/verdicts" "$MEDIA/work"

echo "== regenerate the 8 mutants with the pinned tool (judge/mutants.py) =="
rm -rf "$MEDIA/work/mutants"
"$VENV/bin/python" "$DEMO/judge/mutants.py" --out "$MEDIA/work/mutants"
for m in $MUTANTS; do
    [ -f "$MEDIA/work/mutants/$m/model.stl" ] || { echo "mutant $m not built" >&2; exit 1; }
done
cp -r "$MEDIA/work/mutants" "$MEDIA/data/mutants"

echo "== grade the 3 known-good parts =="
for part in bushing adapter_plate bracket; do
    echo "-- good/$part"
    "$DEMO/judge/grade.sh" "$DEMO/examples/good/$part" --seed "$SEED" \
        --json "$MEDIA/data/verdicts/good_$part.json" >/dev/null \
        && echo "   good_$part: PASS (exit 0)" \
        || { echo "   good_$part FAILED -- media cannot show a passing demo" >&2; exit 1; }
done

echo "== grade the 8 mutants (each must FAIL; a pass means the judge is fooled) =="
for m in $MUTANTS; do
    echo "-- $m"
    if "$DEMO/judge/grade.sh" "$MEDIA/data/mutants/$m" --seed "$SEED" \
            --json "$MEDIA/data/verdicts/$m.json" >/dev/null 2>&1; then
        echo "   $m PASSED (unexpected -- judge fooled)" >&2; exit 1
    else
        echo "   $m: FAIL (expected)"
    fi
done

# The fixing agent's loop, REPLAYED (not a live trace): the same mutant
# artifacts above are the intermediate states an agent fixing
# adapter_plate would go through -- wrong hole count, then wrong hole
# diameter, then drifted first-hole angle, then the good part.  Each step
# was graded for real above; this file only records the iteration order
# the loop figure and the video narrate.  Figures label it a replay.
printf '%s\n' plate-hole-count plate-hole-diameter plate-hole-drift \
    good_adapter_plate > "$MEDIA/data/replay.txt"

echo "== selftest.sh (regenerates + regrades everything itself) =="
bash "$DEMO/judge/selftest.sh" 2>&1 | tee "$MEDIA/data/selftest.txt"

echo "done: $MEDIA/data"
