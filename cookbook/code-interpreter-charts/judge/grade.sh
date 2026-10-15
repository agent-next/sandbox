#!/usr/bin/env bash
# code-interpreter-charts judge: grade one analysis.py artifact against the
# SPEC.md gates.
#   grade.sh <artifact-dir> [--data-dir DIR] [--seed N] [--json out.json]
# Prints one JSON verdict; exits 0 only if every gate passes.
#
# The artifact runs under the pinned interpreter (pandas + matplotlib) that
# judge/setup.sh installed; the judge engine itself only needs that
# interpreter for Pillow.  Judge integrity: the artifact never sees the
# judge tree, and the tree's sha256 is compared before and after grading.
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${CHART_VENV:-$HOME/.cache/code-interpreter-charts/venv}"
PY="$VENV/bin/python"

if [ $# -lt 1 ]; then
    echo "usage: grade.sh <artifact-dir> [--data-dir DIR] [--seed N]" \
         "[--json out.json]" >&2
    exit 2
fi
if [ ! -d "$1" ]; then
    echo "grade: artifact directory '$1' does not exist" >&2
    exit 2
fi
if [ ! -x "$PY" ]; then
    echo "grade: no pinned interpreter at $PY -- run judge/setup.sh first" >&2
    exit 2
fi

judge_sum() {
    (cd "$JDIR" && find . -type f ! -name '*.pyc' -print0 |
        sort -z | xargs -0 sha256sum | sha256sum)
}
before="$(judge_sum)"

set +e
"$PY" -I "$JDIR/charts_judge.py" "$@" --venv-python "$PY"
rc=$?
set -e

after="$(judge_sum)"
if [ "$before" != "$after" ]; then
    echo "grade: judge/ tree changed during grading -- failing closed" >&2
    exit 1
fi
exit $rc
