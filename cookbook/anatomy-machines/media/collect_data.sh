#!/usr/bin/env bash
#
# collect_data.sh -- regenerate media/data/ from the judge.
#
# Everything the figures plot is produced by a real run:
#   - verdict-good.json        grade.sh verdict for examples/good, taken
#                              from selftest.sh's own passing grade
#                              (SELFTEST_OUT preserves it)
#   - verdict-<mutant>.json    grade.sh verdict for each of the 7
#                              mutants.py artifacts, same selftest run
#   - selftest.log             full judge/selftest.sh output
#   - shots-good/angle_*.png,  the judge's own gate-2 canvas captures of
#     shots-good/spin_*.png    the good figure (grade.sh --shots)
#
# Needs judge/setup.sh to have run. Takes ~5-6 min (one full selftest
# plus one grade with --shots).

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "${HERE}")"
DATA="${HERE}/data"
SELFTEST_OUT="${DATA}/selftest"
SHOTS="${DATA}/shots-good"
SEED="${SEED:-42}"

if [[ ! -x "$HOME/.anatomy-judge/venv/bin/python" ]]; then
    echo "collect_data: judge toolchain missing; run judge/setup.sh" >&2
    exit 3
fi

rm -rf "${SELFTEST_OUT}" "${SHOTS}"
mkdir -p "${DATA}" "${SELFTEST_OUT}" "${SHOTS}"

# One real selftest run supplies every verdict JSON + the log.
SELFTEST_OUT="${SELFTEST_OUT}" \
    bash "${DEMO}/judge/selftest.sh" 2>&1 | tee "${DATA}/selftest.log"

cp "${SELFTEST_OUT}/good.json" "${DATA}/verdict-good.json"
for m in blank_canvas missing_parts console_error static_camera \
         wrong_labels no_interaction tiny_capture; do
    cp "${SELFTEST_OUT}/${m}.json" "${DATA}/verdict-${m}.json"
done

# The judge's own canvas screenshots of the good figure (gate 2 drags).
bash "${DEMO}/judge/grade.sh" "${DEMO}/examples/good/four-stroke-engine" \
    --seed "${SEED}" --json "${DATA}/grade-good.json" \
    --shots "${SHOTS}" >/dev/null

echo "collect_data: wrote ${DATA} (verdict-*.json, selftest.log, shots-good/)"
