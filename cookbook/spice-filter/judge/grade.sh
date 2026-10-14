#!/usr/bin/env bash
# spice-filter judge: grade one netlist artifact against the SPEC.md gates.
#   grade.sh <artifact.cir> [--seed N] [--json out.json]
# Prints one JSON verdict; exits 0 only if every gate passes.
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ $# -lt 1 ] || [ ! -f "$1" ]; then
    echo "usage: grade.sh <artifact.cir> [--seed N] [--json out.json]" >&2
    exit 2
fi

# Judge integrity: the artifact under test must not be able to modify the
# judge.  Everything is run from temp copies by the engine; verify the
# judge tree is untouched before and after grading.
judge_sum() {
    (cd "$JDIR" && find . -type f ! -name '*.pyc' -print0 |
        sort -z | xargs -0 sha256sum | sha256sum)
}
before="$(judge_sum)"

# The engine works from a copy in its own temp dir; pass the original path.
set +e
python3 -I "$JDIR/spice_filter_judge.py" "$@"
rc=$?
set -e

after="$(judge_sum)"
if [ "$before" != "$after" ]; then
    echo "grade: judge/ tree changed during grading -- failing closed" >&2
    exit 1
fi
exit $rc
