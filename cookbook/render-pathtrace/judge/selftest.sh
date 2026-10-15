#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$HOME/.local/share/render-pathtrace/deps${PYTHONPATH:+:$PYTHONPATH}"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
exec "$HOME/.local/share/render-pathtrace/venv/bin/python" "$HERE/selftest.py" "$@"
