#!/usr/bin/env bash
# notebook-exec-report judge: grade one notebook artifact against SPEC.md.
#   grade.sh <artifact.ipynb> [--seed N] [--json out.json]
# Prints one JSON verdict; exits 0 only if every gate passes.
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$JDIR/.." && pwd)"
VENV="$HOME/.judge-venv"

if [ $# -lt 1 ] || [ ! -f "$1" ]; then
    echo "usage: grade.sh <artifact.ipynb> [--seed N] [--json out.json]" >&2
    exit 2
fi

# the pinned interpreter: nbclient / ipykernel / sklearn versions decide the
# numbers, so grade.sh refuses a different Python minor.
PY=""
for cand in "$VENV/bin/python3" "$VENV/bin/python"; do
    [ -x "$cand" ] || continue
    v="$("$cand" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
    if [ "$v" = "3.11" ]; then PY="$cand"; fi
done
if [ -z "$PY" ]; then
    echo "grade: $VENV has no python3.11; run bash judge/setup.sh first" >&2
    exit 2
fi

# Judge integrity: the artifact under test must not be able to modify the
# judge.  Everything runs from temp copies; verify the tree is untouched.
judge_sum() {
    (cd "$JDIR" && find . -type f ! -name '*.pyc' -print0 |
        sort -z | xargs -0 sha256sum | sha256sum)
}
before="$(judge_sum)"

set +e
"$PY" -I "$JDIR/notebook_judge.py" "$@"
rc=$?
set -e

after="$(judge_sum)"
if [ "$before" != "$after" ]; then
    echo "grade: judge/ tree changed during grading -- failing closed" >&2
    exit 1
fi
exit $rc
