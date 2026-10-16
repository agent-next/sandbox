#!/usr/bin/env bash
# judge/selftest.sh — prove the Stage-2 judge can FAIL: the untouched real
# frames must PASS and every known-bad single-edit mutant must be killed.
#
# Usage:
#   judge/selftest.sh <run_dir> [--seed N]
#
# <run_dir> is `run.py --out <dir>`: its downloaded real frames are the only
# input (mutants are single edits of them — never synthesised frames, see
# DEMO-STANDARD §Judge rules).  Prints the kill rate and exits non-zero if
# the good set fails, if any mutant survives, or if a second grading of the
# good set is not byte-identical to the first (determinism).

set -euo pipefail

ARTIFACT_DIR=""
SEED=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --seed) SEED="$2"; shift 2 ;;
        *)       ARTIFACT_DIR="$1"; shift ;;
    esac
done

if [[ -z "$ARTIFACT_DIR" || ! -d "$ARTIFACT_DIR" ]]; then
    echo "Usage: $0 <run_dir> [--seed N]" >&2
    exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ABS_ARTIFACT="$(cd "$ARTIFACT_DIR" && pwd)"

PY="${OMNV_JUDGE_PY:-}"
if [[ -z "$PY" && -x "$HOME/.venv-omnv-judge/bin/python" ]]; then
    PY="$HOME/.venv-omnv-judge/bin/python"
fi
PY="${PY:-python3}"

SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/omnv-selftest.XXXXXX")"
trap 'rm -rf "$SCRATCH"' EXIT
cp -r "$ABS_ARTIFACT" "$SCRATCH/artifact"

MUT_DIR="$SCRATCH/mutants"
RC=0
"$PY" "$SCRIPT_DIR/mutate_frames.py" --frames "$SCRATCH/artifact/frames" \
    --out "$MUT_DIR" --selftest > "$SCRATCH/selftest.txt" || RC=$?
cat "$SCRATCH/selftest.txt"

if [[ $RC -ne 0 ]]; then
    echo "[selftest] FAILED (exit $RC)" >&2
    exit "$RC"
fi

# --- determinism: grading the good set twice must be identical ----------- #
A="$SCRATCH/det1.json"; B="$SCRATCH/det2.json"
"$PY" "$SCRIPT_DIR/grade_frames.py" --run "$MUT_DIR/good" --json > "$A" || {
    echo "[selftest] good set did not grade; refusing to report a pass" >&2
    exit 1; }
"$PY" "$SCRIPT_DIR/grade_frames.py" --run "$MUT_DIR/good" --json > "$B" || {
    echo "[selftest] second grading of the good set errored" >&2
    exit 1; }
if ! cmp -s "$A" "$B"; then
    echo "[selftest] ERROR: verdict not deterministic across identical runs" >&2
    exit 1
fi
echo "[selftest] determinism: two gradings of good/ are byte-identical"

grep -q "mutants killed: \(.*\)/" "$SCRATCH/selftest.txt"
KILLED_LINE=$(grep "mutants killed:" "$SCRATCH/selftest.txt")
TOTAL=$(echo "$KILLED_LINE" | sed 's|.*/||')
KILLED_N=$(echo "$KILLED_LINE" | sed 's|mutants killed: ||; s|/.*||')
RATE=$(( 100 * KILLED_N / TOTAL ))
echo "[selftest] kill rate ${RATE}% (${KILLED_N}/${TOTAL}) — must be >= 90%"
if [[ $RATE -lt 90 ]]; then
    exit 1
fi
exit 0
