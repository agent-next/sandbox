#!/bin/sh
# Grade an app-builder-preview artifact. See SPEC.md for the gates.
#
#   judge/grade.sh <artifact-app-dir> [--seed N] [--json out.json] [--shots DIR]
#
# Exits 0 only if every gate passes; prints one JSON verdict on stdout.
# Delegates to judge/_grade.py, which runs the artifact from a copy in a
# fresh temp dir, drives it from judge/spec.json, and checksums judge/
# before and after.

set -eu

HERE=$(cd "$(dirname "$0")" && pwd)

if [ ! -x "$HOME/.tools/app-builder-preview/node/bin/node" ]; then
    echo "grade.sh: node missing; run judge/setup.sh first" >&2
    exit 2
fi

exec python3 "$HERE/_grade.py" --judge-dir "$HERE" "$@"
