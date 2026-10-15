#!/usr/bin/env bash
# judge/grade.sh — run all gates on an artifact directory.
# Usage: judge/grade.sh <artifact_dir> [--seed N] [--json out.json]
# The artifact is graded in a scratch copy (check_gates.py does the copy);
# judge/ is sha256-checksummed before and after to prove the artifact
# cannot modify the judge.

set -euo pipefail

ARTIFACT_DIR=""
JSON_OUT=""
SEED=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --json)  JSON_OUT="$2"; shift 2 ;;
        --seed)  SEED="$2"; shift 2 ;;
        *)       ARTIFACT_DIR="$1"; shift ;;
    esac
done

if [[ -z "$ARTIFACT_DIR" || ! -d "$ARTIFACT_DIR" ]]; then
    echo "Usage: $0 <artifact_dir> [--seed N] [--json out.json]" >&2
    exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

judge_sum() {
    find "$SCRIPT_DIR" -type f ! -name '*.pyc' ! -path '*__pycache__*' \
        -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1
}

BEFORE="$(judge_sum)"

rc=0
if [[ -n "$JSON_OUT" ]]; then
    python3 "$SCRIPT_DIR/check_gates.py" "$ARTIFACT_DIR" --seed "$SEED" \
        --json "$JSON_OUT" || rc=$?
else
    python3 "$SCRIPT_DIR/check_gates.py" "$ARTIFACT_DIR" --seed "$SEED" || rc=$?
fi

AFTER="$(judge_sum)"
if [[ "$BEFORE" != "$AFTER" ]]; then
    echo "[grade] ERROR: judge/ checksum changed during grading" >&2
    echo "  before: $BEFORE" >&2
    echo "  after:  $AFTER" >&2
    exit 1
fi

exit "$rc"
