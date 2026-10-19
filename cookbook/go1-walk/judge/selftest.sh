#!/usr/bin/env bash
# Runs the judge self-test on one GPU lease. mutants.py needs numpy;
# setup.sh installs it into ~/.venvs/go1-walk (fall back to system
# python3 if the venv is absent and numpy is importable there).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="$HOME/.venvs/go1-walk/bin/python"
if [ ! -x "$PY" ]; then PY=python3; fi
exec "$PY" "$HERE/selftest.py" "$@"
