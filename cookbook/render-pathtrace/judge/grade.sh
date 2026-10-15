#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON="$HOME/.local/share/render-pathtrace/venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    echo "Run judge/setup.sh first (missing pinned environment)" >&2
    exit 2
fi
export PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export PYTHONPATH="$HOME/.local/share/render-pathtrace/deps${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON" "$HERE/grade.py" "$@"
