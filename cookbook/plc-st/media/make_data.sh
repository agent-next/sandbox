#!/usr/bin/env bash
# cookbook/plc-st/media/make_data.sh
# Produces the judge output data consumed by make_plots.py and make_frames.py
# into media/data/, using only the judge itself:
#   media/data/grade_good.json          verdict JSON for examples/good/tank_ctrl.st
#   media/data/grade_good_replica.json  second grade of the same file, same seed
#   media/data/selftest_output.txt      judge/selftest.sh full output
#   media/data/grade_<mutant>.json      one verdict JSON per single-edit mutant
#   media/data/traces_good/trace_<scenario>.csv   per-scan traces, good controller
#
# Determinism check: grade_good.json and grade_good_replica.json must be
# byte-identical; the script fails otherwise.
#
# Requirements: judge/setup.sh must have been run once (iec2c installed).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JUDGE_DIR="${HERE}/../judge"
GOOD_ST="${HERE}/../examples/good/tank_ctrl.st"
DATA_DIR="${HERE}/data"
SEED="20261014"

MUTANTS="estop_not_safe inverted_dryrun missing_estop_latch missing_overflow_guard no_dry_restart swapped_valves"

[ -x "${HOME}/.plc-st/bin/iec2c" ] \
    || { echo "make_data.sh: iec2c not installed -- run 'bash judge/setup.sh' first"; exit 1; }

rm -rf "${DATA_DIR}"
mkdir -p "${DATA_DIR}/traces_good"

# 1. selftest (also proves the judge can fail: kill rate printed)
bash "${JUDGE_DIR}/selftest.sh" > "${DATA_DIR}/selftest_output.txt" 2>&1
tail -n 3 "${DATA_DIR}/selftest_output.txt"

# 2. good controller, graded twice with the same seed, traces on the first run
bash "${JUDGE_DIR}/grade.sh" "${GOOD_ST}" --seed "${SEED}" \
    --json "${DATA_DIR}/grade_good.json" --trace "${DATA_DIR}/traces_good" \
    > /dev/null
bash "${JUDGE_DIR}/grade.sh" "${GOOD_ST}" --seed "${SEED}" \
    --json "${DATA_DIR}/grade_good_replica.json" \
    > /dev/null

cmp "${DATA_DIR}/grade_good.json" "${DATA_DIR}/grade_good_replica.json" \
    || { echo "make_data.sh: determinism FAILED -- two grades of the same seed differ"; exit 1; }
echo "make_data.sh: determinism PASS (same seed -> byte-identical verdict JSON)"

# 3. single-edit mutants, each graded
MUTDIR="$(mktemp -d)"
trap 'rm -rf "${MUTDIR}"' EXIT
python3 "${JUDGE_DIR}/mutate.py" "${GOOD_ST}" "${MUTDIR}" > /dev/null
for m in ${MUTANTS}; do
    bash "${JUDGE_DIR}/grade.sh" "${MUTDIR}/${m}.st" --seed "${SEED}" \
        --json "${DATA_DIR}/grade_${m}.json" \
        > /dev/null 2>&1 \
        || echo "make_data.sh: mutant ${m} failed the judge (expected)"
done

echo "make_data.sh: wrote ${DATA_DIR}:"
ls "${DATA_DIR}" "${DATA_DIR}/traces_good"
