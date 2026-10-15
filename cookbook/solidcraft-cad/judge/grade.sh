#!/usr/bin/env bash
# solidcraft-cad judge: grade one SolidCraft design script against SPEC.md.
#   grade.sh <design.json> [--seed N] [--json out.json]
# Prints one JSON verdict; exits 0 only if every gate passes.
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$HOME/.local/solidcraft-judge-venv/bin/python"

if [ $# -lt 1 ] || [ ! -f "$1" ]; then
    echo "usage: grade.sh <design.json> [--seed N] [--json out.json]" >&2
    exit 2
fi
if [ ! -x "$PY" ]; then
    echo "grade: $PY missing; run judge/setup.sh first" >&2
    exit 2
fi

# Judge integrity: the design under test must not be able to modify the
# judge.  The engine builds from a copy in its own temp dir; verify the
# judge tree (and spec.json) are untouched before and after grading.
judge_sum() {
    (cd "$JDIR/.." && find judge spec.json -type f ! -name '*.pyc' ! -name VERSIONS.txt -print0 |
        sort -z | xargs -0 sha256sum | sha256sum)
}
before="$(judge_sum)"

set +e
"$PY" -I "$JDIR/solidcraft_judge.py" "$@"
rc=$?
set -e

after="$(judge_sum)"
if [ "$before" != "$after" ]; then
    echo "grade: judge/ tree changed during grading -- failing closed" >&2
    exit 1
fi
exit $rc
