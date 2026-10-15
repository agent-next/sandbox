#!/usr/bin/env bash
# judge/grade.sh — run every gate on one delivered artifact directory.
# Usage: judge/grade.sh <artifact_dir> [--seed N] [--json out.json]
#
# The artifact is graded from a scratch copy; the committed files are
# never touched, and judge/ is checksummed before and after to prove the
# artifact cannot modify the judge (DEMO-STANDARD.md, "Judge rules").

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${AICAD_VENV:-$HOME/.venvs/aicad}"
PY="$VENV/bin/python"

if [[ ! -x "$PY" ]]; then
    echo "[grade] ERROR: judge venv missing at $VENV — run judge/setup.sh" >&2
    exit 2
fi

if [[ $# -lt 1 || ! -d "$1" ]]; then
    echo "Usage: $0 <artifact_dir> [--seed N] [--json out.json]" >&2
    exit 2
fi

ARTIFACT="$(cd "$1" && pwd)"
shift

# judge integrity: sha256 of judge/ before and after the run
JUDGE_SUM_BEFORE="$(find "$SCRIPT_DIR" -type f ! -name '*.pyc' -print0 \
    | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)"
trap 'rm -rf "$SCRATCH"' EXIT
SCRATCH="$(mktemp -d /tmp/aicad-grade.XXXXXX)"
cp -r "$ARTIFACT" "$SCRATCH/artifact"

"$PY" "$SCRIPT_DIR/check_gates.py" "$SCRATCH/artifact" "$@"
rc=$?

JUDGE_SUM_AFTER="$(find "$SCRIPT_DIR" -type f ! -name '*.pyc' -print0 \
    | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)"
if [[ "$JUDGE_SUM_BEFORE" != "$JUDGE_SUM_AFTER" ]]; then
    echo "[grade] ERROR: judge/ changed during grading — refusing" >&2
    exit 3
fi
exit $rc
