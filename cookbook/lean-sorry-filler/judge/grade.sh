#!/bin/sh
# Grade a lean-sorry-filler artifact. See SPEC.md for the gates.
#
#   judge/grade.sh <artifact-dir> [--seed N] [--json out.json]
#
# Exits 0 only if every gate passes; prints one JSON verdict on stdout.
# Delegates to judge/_grade.py, which builds the artifact from a copy in
# a fresh temp dir and checksums judge/ before and after. Needs the
# pinned toolchain from judge/setup.sh.

set -eu

HERE=$(cd "$(dirname "$0")" && pwd)

if [ ! -x "${ELAN_HOME:-$HOME/.elan}/bin/lean" ] && \
   [ ! -x "$HOME/.elan-test/bin/lean" ]; then
    echo "grade.sh: no Lean toolchain found; run judge/setup.sh first" >&2
    exit 2
fi

exec python3 "$HERE/_grade.py" --judge-dir "$HERE" "$@"
