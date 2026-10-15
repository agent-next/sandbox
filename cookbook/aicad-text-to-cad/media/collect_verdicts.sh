#!/bin/bash
# Collect the real judge outputs the media is built from.
#   - regenerates the 8 mutants into media/work/mutants/ (judge/mutants.py)
#   - grades the 3 known-good parts + every mutant with
#     grade.sh --seed 42 --json into media/data/verdicts/
#   - replays a fixing agent's loop on adapter_plate (bad -> partly
#     fixed -> good); those grades are the same JSONs, the replay
#     order is recorded in data/replay.txt
#   - reruns judge/selftest.sh, saving output to data/selftest.txt
# Requires judge/setup.sh to have run (venv at ~/.venvs/aicad-judge).
set -euo pipefail
MEDIA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "$MEDIA")"
SEED=42

VENV="${AICAD_JUDGE_VENV:-$HOME/.venvs/aicad-judge}"
[ -x "$VENV/bin/python" ] || { echo "judge venv missing -- run judge/setup.sh" >&2; exit 1; }

MUTANTS="plate-hole-count plate-hole-diameter plate-hole-drift \
         plate-flipped-facet bracket-missing-fillet bracket-fillet-radius \
         bushing-scale-25_4 bushing-non-watertight"

mkdir -p "$MEDIA/data/verdicts" "$MEDIA/work/mutants"

echo "== regenerate mutants (judge/mutants.py) =="
"$VENV/bin/python" "$DEMO/judge/mutants.py" --out "$MEDIA/work/mutants"

for part in bushing adapter_plate bracket; do
    echo "== grade good/$part =="
    "$DEMO/judge/grade.sh" "$DEMO/examples/good/$part" --seed $SEED \
        --json "$MEDIA/data/verdicts/good_$part.json" >/dev/null \
        && echo "good_$part: PASS" \
        || { echo "good_$part failed" >&2; exit 1; }
done

for m in $MUTANTS; do
    echo "== grade mutant $m =="
    if "$DEMO/judge/grade.sh" "$MEDIA/work/mutants/$m" --seed $SEED \
            --json "$MEDIA/data/verdicts/$m.json" >/dev/null 2>&1; then
        echo "$m: PASS (unexpected -- judge fooled)" >&2; exit 1
    else
        echo "$m: FAIL (expected)"
    fi
done

# the fixing agent's replay on adapter_plate: wrong count -> wrong
# diameter -> drifted angle -> good.  Same seed, same JSONs as above;
# this file only records the order the figure uses.
printf '%s\n' plate-hole-count plate-hole-diameter plate-hole-drift \
    good_adapter_plate > "$MEDIA/data/replay.txt"

echo "== selftest =="
bash "$DEMO/judge/selftest.sh" | tee "$MEDIA/data/selftest.txt"

echo "verdicts + replay + selftest log collected in $MEDIA/data"
