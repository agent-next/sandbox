#!/usr/bin/env bash
# climate-glacier-model judge: grade one artifact against the SPEC.md gates.
#   grade.sh <artifact-dir> [--seed N] [--json out.json]
# Prints one JSON verdict; exits 0 only if every gate passes.
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ $# -lt 1 ] || [ ! -d "$1" ]; then
    echo "usage: grade.sh <artifact-dir> [--seed N] [--json out.json]" >&2
    exit 2
fi

# Judge integrity: the artifact under test must not be able to modify the
# judge.  The engine copies the artifact into its own temp dir and runs it
# there; here we verify the judge tree itself is untouched by the grade.
judge_sum() {
    (cd "$JDIR" && find . -type f ! -name '*.pyc' ! -path './__pycache__/*' \
        -print0 | sort -z | xargs -0 sha256sum | sha256sum)
}
before="$(judge_sum)"

set +e
python3 -I "$JDIR/glacier_judge.py" "$@"
rc=$?
set -e

after="$(judge_sum)"
if [ "$before" != "$after" ]; then
    echo "grade: judge/ tree changed during grading -- failing closed" >&2
    exit 1
fi
exit $rc
