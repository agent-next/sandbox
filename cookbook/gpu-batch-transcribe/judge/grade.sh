#!/usr/bin/env bash
# Grade a transcription artifact. See SPEC.md for the gates.
#
#   judge/grade.sh examples/good/transcriber.py [--seed N] [--json out.json]
#
# Exits 0 only if every gate passes; prints one JSON verdict on stdout.
# Delegates to judge/_grade.py, which runs the artifact from a scratch
# copy (redacted manifest + corpus audio) and checksums judge/ before
# and after so the artifact cannot modify the judge.

set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
PY="$HOME/.venvs/gpu-batch-transcribe/bin/python"

if [ ! -x "$PY" ]; then
    echo "grade.sh: judge venv missing; run judge/setup.sh first" >&2
    exit 2
fi

# The fresh clone ships no corpus/ (audio is downloaded by setup); the
# corpus digest check needs every pinned file, so install before
# complaining that one is missing.
if [ ! -d "$HERE/corpus" ] || [ ! -f "$HERE/corpus/corpus.json" ]; then
    bash "$HERE/setup.sh"
fi

exec "$PY" "$HERE/_grade.py" "$@"
