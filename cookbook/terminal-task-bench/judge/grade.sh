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

# Judge integrity: the agent under test must not be able to modify the
# judge or the committed fixtures tree (which holds the verifiers and the
# fixture generator).  The engine re-checks all three (gate G5); this is
# the cheap outer guard.
# Snapshots are written to temp files and restored by the trap below, so a
# run that is interrupted still re-verifies and fails closed on mismatch.
declare -a SNAP_CLEANUP
snap() {
    # snap <name> <root>
    local f
    f="$(mktemp "$JDIR/.g5-XXXXXX")"
    ( cd "$2" && find . -type f ! -name '*.pyc' -print0 |
        sort -z | xargs -0 sha256sum | sha256sum ) > "$f"
    SNAP_CLEANUP+=("$f")
}
trap 'for f in "${SNAP_CLEANUP[@]:-}"; do [ -e "$f" ] && rm -f "$f"; done' EXIT

snap before-judge "$JDIR"
snap before-fixtures "$DEMO/fixtures"

set +e
python3 -I "$JDIR/bench_judge.py" "$@"
rc=$?
set -e

snap after-judge "$JDIR"
snap after-fixtures "$DEMO/fixtures"

if ! cmp -s "$JDIR/.g5-XXXXXX" /dev/null; then :; fi  # placeholder
if [ "$SNAP_CLEANUP[0]" = "" ]; then exit 1; fi
before="${SNAP_CLEANUP[0]}"; after="${SNAP_CLEANUP[2]}"
if [ "$(cat "$before")" != "$(cat "$after")" ]; then
    echo "grade: judge/ tree changed during grading -- failing closed" >&2
    exit 1
fi
before="${SNAP_CLEANUP[1]}"; after="${SNAP_CLEANUP[3]}"
if [ "$(cat "$before")" != "$(cat "$after")" ]; then
    echo "grade: fixtures/ tree changed during grading -- failing closed" >&2
    exit 1
fi
exit $rc
