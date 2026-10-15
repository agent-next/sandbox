#!/bin/sh
# Grade a sweep artifact. See SPEC.md for the gates.
#
#   judge/grade.sh examples/good/sweep.json [--seed N] [--json out.json]
#                        [--cpu-check] [--speedup-floor F]
#
# Exits 0 only if every gate passes; prints one JSON verdict on stdout.
# Delegates to judge/_grade.py, which runs the artifact from a copy in a
# fresh temp dir and checksums judge/ before and after.

set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
PY="$HOME/.venvs/gpu-sim-sweep/bin/python"

if [ ! -x "$PY" ]; then
    echo "grade.sh: judge venv missing; run judge/setup.sh first" >&2
    exit 2
fi

exec "$PY" "$HERE/_grade.py" "$@"
