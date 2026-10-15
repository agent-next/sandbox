#!/usr/bin/env bash
set -euo pipefail
JDIR="$(cd "$(dirname "$0")" && pwd)"
export PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
exec "$HOME/.local/video-edit-mlt/venv/bin/python" -B "$JDIR/grade.py" "$@"
