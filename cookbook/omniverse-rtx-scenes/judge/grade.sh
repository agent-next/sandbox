#!/usr/bin/env bash
# judge/grade.sh — run every Stage-2 gate on a downloaded render and print
# one JSON verdict.  Exits 0 only if all gates pass.
#
# Usage:
#   judge/grade.sh <run_dir> [--json out.json] [--seed N]
#
# <run_dir> is the directory `run.py --out <dir>` produces:
#   frames/<scene>/*.png + scenes/<scene>/scene.usda
#
# The judge never mutates the artifact: judge/*.py is checksummed before
# and after (DEMO-STANDARD: "never let the artifact under test modify the
# judge"), and the artifact is copied to a scratch dir before grading.
# `grade_frames.py` is deterministic for a given frame set (the gates are
# numeric comparisons over pixels and USD, no RNG), so --seed is accepted
# only to prove that: two runs give byte-identical verdicts.
#
# Environment:
#   OMNV_JUDGE_PY  python to run the judge with (default:
#                  ~/.venv-omnv-judge/bin/python if judge/setup.sh ran,
#                  else python3)

set -euo pipefail

ARTIFACT_DIR=""
JSON_OUT=""
SEED=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --json)  JSON_OUT="$2"; shift 2 ;;
        --seed)  SEED="$2"; shift 2 ;;
        *)       ARTIFACT_DIR="$1"; shift ;;
    esac
done

if [[ -z "$ARTIFACT_DIR" || ! -d "$ARTIFACT_DIR" ]]; then
    echo "Usage: $0 <run_dir> [--json out.json] [--seed N]" >&2
    exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ABS_ARTIFACT="$(cd "$ARTIFACT_DIR" && pwd)"

PY="${OMNV_JUDGE_PY:-}"
if [[ -z "$PY" && -x "$HOME/.venv-omnv-judge/bin/python" ]]; then
    PY="$HOME/.venv-omnv-judge/bin/python"
fi
PY="${PY:-python3}"

# --- prove the artifact cannot modify the judge -------------------------- #
judge_sum() {
    (cd "$SCRIPT_DIR" && find . -name '*.py' -type f \
        ! -path './__pycache__/*' | sort | xargs sha256sum | sha256sum)
}
JUDGE_SUM_BEFORE=$(judge_sum)

SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/omnv-grade.XXXXXX")"
trap 'rm -rf "$SCRATCH"' EXIT
cp -r "$ABS_ARTIFACT" "$SCRATCH/artifact"

RC=0
if [[ -n "$JSON_OUT" ]]; then
    "$PY" "$SCRIPT_DIR/grade_frames.py" --run "$SCRATCH/artifact" --json \
        > "$SCRATCH/verdict.json" || RC=$?
    if [[ $RC -eq 0 ]]; then
        cp "$SCRATCH/verdict.json" "$JSON_OUT"
    else
        echo "[grade] verdict FAILED (exit $RC):" >&2
        "$PY" "$SCRIPT_DIR/grade_frames.py" --run "$SCRATCH/artifact" || true
    fi
else
    "$PY" "$SCRIPT_DIR/grade_frames.py" --run "$SCRATCH/artifact" || RC=$?
fi

JUDGE_SUM_AFTER=$(judge_sum)
if [[ "$JUDGE_SUM_BEFORE" != "$JUDGE_SUM_AFTER" ]]; then
    echo "[grade] ERROR: judge/*.py changed during grading" >&2
    exit 3
fi

exit "$RC"
