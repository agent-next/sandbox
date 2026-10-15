#!/usr/bin/env bash
# skill-ab-bench judge: grade one experiment record against the SPEC.md gates.
#   grade.sh <dir> [--seed N] [--json out.json] [--arms skill,noskill[,placebo]]
#            [--bootstrap N]
# Prints one JSON verdict on stdout; exits 0 only if every gate passes.
#
# The engine (judge/grade.py) is run with -I so the artifact cannot put a
# module on the interpreter's path, and it grades a copy of the artifact, so
# nothing under test can touch judge/.
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ $# -lt 1 ]; then
    echo "usage: grade.sh <dir> [--seed N] [--json out.json]" \
         "[--arms skill,noskill[,placebo]] [--bootstrap N]" >&2
    exit 2
fi

# Judge integrity: checksum the judge tree before and after grading and fail
# closed if anything moved.  grade.py does the same check internally; this is
# the outer belt for the shell wrapper itself.
judge_sum() {
    (cd "$JDIR" && find . -type f ! -name '*.pyc' -print0 |
        sort -z | xargs -0 sha256sum | sha256sum)
}
before="$(judge_sum)"

set +e
python3 -I "$JDIR/grade.py" "$@"
rc=$?
set -e

after="$(judge_sum)"
if [ "$before" != "$after" ]; then
    echo "grade: judge/ tree changed during grading -- failing closed" >&2
    exit 1
fi
exit $rc
