#!/usr/bin/env bash
# The known-good bench agent.
#
# The judge runs one solutions/<task-id>/apply.sh per task, with cwd set to
# the task's scratch dir and WORK exported as the absolute path of its
# work/ tree.  This file is a convenience wrapper so a human can run the
# whole agent against a fixture tree by hand:
#
#     bash examples/good/agent.sh <fixture-dir>   # dir holding <task>/work
#
# It does exactly what judge/grade.sh does, one task at a time.
set -euo pipefail

FIXTURES="${1:?usage: agent.sh <fixture-dir>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for task in "$HERE"/solutions/*/; do
    id="$(basename "$task")"
    work="$FIXTURES/$id/work"
    if [ ! -d "$work" ]; then
        echo "agent: no fixture for $id at $work" >&2
        exit 1
    fi
    echo "agent: $id"
    ( cd "$FIXTURES/$id" && WORK="$work" bash "$HERE/solutions/$id/apply.sh" )
done
echo "agent: all tasks repaired"
