#!/usr/bin/env bash
# viral-microgen judge: grade one artifact directory against the SPEC.md gates.
#   grade.sh <artifact_dir> [--seed N] [--json out.json]
# Prints one JSON verdict; exits 0 only if every gate passes.
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${VIRAL_VENV:-$HOME/.viral-microgen-venv}"

if [ $# -lt 1 ] || [ ! -d "$1" ]; then
    echo "usage: grade.sh <artifact_dir> [--seed N] [--json out.json]" >&2
    exit 2
fi

if [ -x "$VENV/bin/python" ]; then
    PY="$VENV/bin/python"
else
    echo "grade: $VENV is missing -- run judge/setup.sh first" >&2
    exit 2
fi

# Judge integrity: the artifact under test must not be able to modify the
# judge.  The engine grades a temp copy of the artifact, but verify the judge
# tree itself is untouched before and after anyway.
judge_sum() {
    (cd "$JDIR" && find . -type f ! -name '*.pyc' -print0 |
        sort -z | xargs -0 sha256sum | sha256sum)
}
before="$(judge_sum)"

set +e
"$PY" -I "$JDIR/viral_judge.py" "$@"
rc=$?
set -e

after="$(judge_sum)"
if [ "$before" != "$after" ]; then
    echo "grade: judge/ tree changed during grading -- failing closed" >&2
    exit 1
fi
exit $rc
