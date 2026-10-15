#!/usr/bin/env bash
# usd-validate-fix judge: grade one .usda artifact against the SPEC.md gates.
#   grade.sh <artifact.usda> [--seed N] [--json out.json]
# Prints one JSON verdict; exits 0 only if every gate passes.
#
# The artifact never runs loose in the judge: it is graded from a scratch
# copy, and the judge/ tree is checksummed before and after (any change fails
# the grade).  --seed is accepted for API compatibility and recorded, but no
# gate is randomised.
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$JDIR/.." && pwd)"
VENV="$HOME/.usd-validate-fix-venv"

if [ ! -x "$VENV/bin/nvidia_usd_validate" ]; then
    echo "grade: $VENV missing -- run judge/setup.sh first" >&2
    exit 1
fi
if [ $# -lt 1 ] || [ ! -f "$1" ]; then
    echo "usage: grade.sh <artifact.usda> [--seed N] [--json out.json]" >&2
    exit 2
fi

judge_sum() {
    (cd "$JDIR" && find . -type f ! -name '*.pyc' ! -name 'VERSIONS.txt' \
        -print0 | sort -z | xargs -0 sha256sum | sha256sum)
}
before="$(judge_sum)"

set +e
"$VENV/bin/python" -I "$JDIR/grade_engine.py" "$@"
rc=$?
set -e

if [ "$(judge_sum)" != "$before" ]; then
    echo "grade: judge/ tree changed during grading -- failing closed" >&2
    exit 1
fi
exit $rc
