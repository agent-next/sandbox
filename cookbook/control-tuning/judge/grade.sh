#!/usr/bin/env bash
# Grade one controller artifact against all gates.
# Usage: grade.sh <artifact.json> [--seed N] [--json out.json] [--no-mc]
# Exits 0 only if every gate passes. The artifact is graded against a
# checksummed copy of judge/: any modification of the judge fails loudly.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${CT_PYTHON:-$HOME/ct-judge-venv/bin/python3}"
if [ ! -x "$PY" ]; then
  echo "grade.sh: judge venv not found; run judge/setup.sh first" >&2
  exit 2
fi

if [ $# -lt 1 ]; then
  echo "usage: grade.sh <artifact.json> [--seed N] [--json out.json] [--no-mc]" >&2
  exit 2
fi
ARTIFACT="$1"; shift

# Run against a copy of judge/ so a rogue artifact cannot edit the judge
# mid-run and have the edit count for this grading.
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cp -r "$HERE" "$WORK/judge"
BEFORE="$(find "$WORK/judge" -type f -exec sha256sum {} + | sort | sha256sum)"

RC=0
"$PY" -B -I "$WORK/judge/grade.py" "$ARTIFACT" "$@" || RC=$?

AFTER="$(find "$WORK/judge" -type f -exec sha256sum {} + | sort | sha256sum)"
if [ "$BEFORE" != "$AFTER" ]; then
  echo "grade.sh: judge/ was modified during grading" >&2
  exit 3
fi
exit "$RC"
