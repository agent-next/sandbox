#!/usr/bin/env bash
# Grade a spreadsheet-recalc artifact. See SPEC.md for the gates.
#
#   judge/grade.sh <artifact.xlsx> [--json out.json]
#
# Exits 0 only if every gate passes; prints one JSON verdict on stdout.
# Delegates to judge/_grade.py, which recalculates the workbook with
# LibreOffice, reads computed values, and compares against the closed-form
# DCF oracle.

set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
PY="${PYTHON:-python3}"

if ! command -v libreoffice >/dev/null 2>&1; then
    echo "grade.sh: libreoffice not found; run judge/setup.sh first" >&2
    exit 2
fi

exec "$PY" "$HERE/_grade.py" --judge-dir "$HERE" "$@"
