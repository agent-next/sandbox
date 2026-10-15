#!/usr/bin/env bash
# terminal-task-bench judge: grade one agent directory against the SPEC gates.
#   grade.sh <agent-dir> [--seed N] [--json out.json] [--tasks a,b]
# Prints one JSON verdict; exits 0 only if every gate passes.
#
# The engine (bench_judge.py) enforces oracle integrity end to end: each
# task's verifier is staged and fingerprinted before the agent runs, and
# only the judge's staged copy ever executes.  This wrapper adds the
# outer guard -- the two committed trees (judge/, fixtures/) are
# fingerprinted before and after the whole run, so a tampered engine or
# generator cannot paper over its own tracks.
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$JDIR/.." && pwd)"

if [ $# -lt 1 ] || [ ! -d "$1" ]; then
    echo "usage: grade.sh <agent-dir> [--seed N] [--json out.json]" >&2
    exit 2
fi

tree_sha() {  # sha256 of every file under $1 (name + bytes)
    ( cd "$1" && find . -type f ! -name '*.pyc' -print0 |
        sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1 )
}

before_judge="$(tree_sha "$JDIR")"
before_fixtures="$(tree_sha "$DEMO/fixtures")"

set +e
python3 -I "$JDIR/bench_judge.py" "$@"
rc=$?
set -e

after_judge="$(tree_sha "$JDIR")"
after_fixtures="$(tree_sha "$DEMO/fixtures")"

if [ "$before_judge" != "$after_judge" ]; then
    echo "grade: judge/ tree changed during grading -- failing closed" >&2
    exit 1
fi
if [ "$before_fixtures" != "$after_fixtures" ]; then
    echo "grade: fixtures/ tree changed during grading -- failing closed" >&2
    exit 1
fi
exit "$rc"
