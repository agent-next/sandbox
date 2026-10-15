#!/bin/sh
# Grade an untrusted-code-isolation artifact. See SPEC.md for the gates.
#
#   judge/grade.sh examples/good/runner.py [--seed N] [--json out.json]
#
# Exits 0 only if every gate passes; prints one JSON verdict on stdout.
# Delegates to judge/_grade.py, which runs the artifact against every snippet
# and scores containment from effects the artifact does not control.

set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
PY="$HOME/.venvs/untrusted-code-isolation/bin/python"

if [ ! -x "$PY" ]; then
    echo "grade.sh: judge interpreter missing; run judge/setup.sh first" >&2
    exit 2
fi

exec "$PY" "$HERE/_grade.py" --judge-dir "$HERE" "$@"
