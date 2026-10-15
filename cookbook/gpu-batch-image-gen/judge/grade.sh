#!/bin/sh
# Grade a rendered batch artifact. See SPEC.md for the gates.
#
#   judge/grade.sh examples/good/batch [--seed N] [--json out.json]
#
# Exits 0 only if every gate passes; prints one JSON verdict on stdout.
# Delegates to judge/_grade.py, which runs single-threaded and checksums
# judge/ before and after.

set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
PY="$HOME/.venvs/gpu-image-gen/bin/python"

if [ ! -x "$PY" ]; then
    echo "grade.sh: judge venv missing; run judge/setup.sh first" >&2
    exit 2
fi

exec "$PY" "$HERE/_grade.py" --judge-dir "$HERE" "$@"
