#!/usr/bin/env bash
# Grade one delivered artifact directory: judge/grade.sh <dir> [--seed N]
#                                                       [--json out.json]
# Prints one JSON verdict; exits 0 only if every gate passes.
# The artifact under test can never modify the judge: the grader runs from a
# throwaway copy and the judge tree is checksummed before and after.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="${AICAD_JUDGE_PY:-$HOME/.venvs/aicad-judge/bin/python}"
if [ ! -x "$VENV_PY" ]; then
    echo "FATAL: judge venv missing; run judge/setup.sh first" >&2
    exit 2
fi

JUDGE_SUM_BEFORE="$(find "$HERE" -type f ! -name VERSIONS.txt -print0 | sort -z | xargs -0 sha256sum | sha256sum)"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cp -r "$HERE" "$WORK/judge"

"$VENV_PY" "$WORK/judge/judge.py" "$@"
rc=$?

JUDGE_SUM_AFTER="$(find "$HERE" -type f ! -name VERSIONS.txt -print0 | sort -z | xargs -0 sha256sum | sha256sum)"
if [ "$JUDGE_SUM_BEFORE" != "$JUDGE_SUM_AFTER" ]; then
    echo "FATAL: judge/ changed while grading" >&2
    exit 2
fi
exit $rc
