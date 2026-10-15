#!/usr/bin/env bash
# terminal-task-bench judge: grade one agent directory against the SPEC gates.
#   grade.sh <agent-dir> [--seed N] [--json out.json] [--tasks a,b] [--jobs N]
# Prints one JSON verdict; exits 0 only if every gate passes.
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ $# -lt 1 ] || [ ! -d "$1" ]; then
    echo "usage: grade.sh <agent-dir> [--seed N] [--json out.json]" >&2
    exit 2
fi

# Judge integrity: the agent under test must not be able to modify the judge.
# The engine also re-checks this (gate G5); this is the cheap outer guard.
judge_sum() {
    (cd "$JDIR" && find . -type f ! -name '*.pyc' -print0 |
        sort -z | xargs -0 sha256sum | sha256sum)
}
before="$(judge_sum)"

set +e
python3 -I "$JDIR/bench_judge.py" "$@"
rc=$?
set -e

after="$(judge_sum)"
if [ "$before" != "$after" ]; then
    echo "grade: judge/ tree changed during grading -- failing closed" >&2
    exit 1
fi
exit $rc
