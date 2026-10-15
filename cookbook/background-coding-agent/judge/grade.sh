#!/usr/bin/env bash
# background-coding-agent judge: grade one delivery against the SPEC.md
# gates.
#   grade.sh <delivery.patch> [--seed N] [--json out.json] [--pr PR.md]
# Prints one JSON verdict; exits 0 only if every gate passes.
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ $# -lt 1 ] || [ ! -f "$1" ]; then
    echo "usage: grade.sh <delivery.patch> [--seed N] [--json out.json] [--pr PR.md]" >&2
    exit 2
fi

# Judge integrity: the artifact under test must not be able to modify the
# judge.  The engine works from temp copies; verify the judge tree is
# untouched before and after grading.
judge_sum() {
    (cd "$JDIR" && find . -type f ! -name '*.pyc' \
        ! -path '*/__pycache__/*' -print0 |
        sort -z | xargs -0 sha256sum | sha256sum)
}
before="$(judge_sum)"

set +e
python3 -I "$JDIR/grade_engine.py" "$@"
rc=$?
set -e

after="$(judge_sum)"
if [ "$before" != "$after" ]; then
    echo "grade: judge/ tree changed during grading -- failing closed" >&2
    exit 1
fi
exit $rc
