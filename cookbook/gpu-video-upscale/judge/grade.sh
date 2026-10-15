#!/bin/sh
# Grade an artifact with the pinned judge toolchain. See SPEC.md.
#
#   grade.sh <artifact> [--seed N] [--json out.json] [--clip PATH]
#              [--frames N] [--tile N]
#
# Prints one JSON verdict; exits 0 only if every gate passes. The artifact is
# graded from a copy in a fresh temp dir and judge/ checksums are verified
# before and after.

set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
VENV="$HOME/.venvs/gpu-video-upscale"
DEMO=$(cd "$HERE/.." && pwd)

if [ ! -x "$VENV/bin/python" ]; then
    echo "grade.sh: judge toolchain not installed; run judge/setup.sh first" >&2
    exit 2
fi

# shellcheck disable=SC2086
exec "$VENV/bin/python" "$HERE/_grade.py" "$@"
