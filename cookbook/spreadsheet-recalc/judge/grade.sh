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

# Resolve the interpreter: prefer the pinned venv created by setup.sh,
# then $PYTHON, then python3. run.py invokes each script as a separate
# sbx exec, so PYTHON cannot be relied on to persist across steps.
VENV_PY="$HOME/.venvs/spreadsheet-recalc/bin/python"
if [ -n "${PYTHON:-}" ] && command -v "$PYTHON" >/dev/null 2>&1; then
    PY="$PYTHON"
elif [ -x "$VENV_PY" ]; then
    PY="$VENV_PY"
else
    PY=python3
fi

if ! command -v libreoffice >/dev/null 2>&1; then
    echo "grade.sh: libreoffice not found; run judge/setup.sh first" >&2
    exit 2
fi

exec "$PY" "$HERE/_grade.py" --judge-dir "$HERE" "$@"
