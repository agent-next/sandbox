#!/usr/bin/env bash
# cookbook/scheduled-agent-digest judge: grade an artifact directory.
#
# Usage:
#   bash judge/grade.sh <artifact-dir> [--seed N] [--json out.json]
#
# The artifact is a directory holding `digest.py` + `schedule.json` (and
# nothing judge-shaped).  grade.py runs every gate from SPEC.md against a
# *copy* of it, and this script verifies the judge's own tree was not
# modified in the process (SPEC "Judge-integrity rule").
#
# Exit 0 iff every gate passes.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ARTIFACT="${1:-}"
SEED="20261015"
JSON_OUT=""
shift || true
while [ $# -gt 0 ]; do
    case "$1" in
        --seed) SEED="$2"; shift 2 ;;
        --json) JSON_OUT="$2"; shift 2 ;;
        *) shift ;;
    esac
done

fail() { echo "grade: $*" >&2; exit 1; }

[ -n "$ARTIFACT" ] || fail "usage: grade.sh <artifact-dir> [--seed N] [--json out.json]"
[ -d "$ARTIFACT" ] || fail "artifact directory not found: $ARTIFACT"
[ -f "$ARTIFACT/digest.py" ] || fail "artifact has no digest.py: $ARTIFACT"
[ -f "$ARTIFACT/schedule.json" ] || fail "artifact has no schedule.json: $ARTIFACT"

# prefer the tools judge/setup.sh pinned into $HOME
PINNED_BIN="${HOME}/.scheduled-agent-digest/bin"
[ -d "$PINNED_BIN" ] && export PATH="${PINNED_BIN}:${PATH}"

command -v python3 >/dev/null 2>&1 || fail "python3 missing -- run 'bash judge/setup.sh' first"
command -v sqlite3 >/dev/null 2>&1 || fail "sqlite3 missing -- run 'bash judge/setup.sh' first"

# hash the judge before any artifact code runs (SPEC judge-integrity rule)
JUDGE_HASH_BEFORE="$(find "$HERE" -type f ! -path '*/__pycache__/*' \
                     ! -name 'setup.sh' ! -name 'grade.sh' \
                     ! -name 'selftest.sh' ! -name 'RECEIPT.md' -exec sha256sum {} + \
                     | sort | sha256sum | awk '{print $1}')"

set +e
python3 "${HERE}/grade.py" "$ARTIFACT" --seed "$SEED" ${JSON_OUT:+--json "$JSON_OUT"}
rc=$?
set -e

# the artifact must not have touched the judge
JUDGE_HASH_AFTER="$(find "$HERE" -type f ! -path '*/__pycache__/*' \
                    ! -name 'setup.sh' ! -name 'grade.sh' \
                    ! -name 'selftest.sh' ! -name 'RECEIPT.md' -exec sha256sum {} + \
                    | sort | sha256sum | awk '{print $1}')"
[ "$JUDGE_HASH_BEFORE" = "$JUDGE_HASH_AFTER" ] \
    || fail "judge sources changed during grading (checksum mismatch)"

if [ "$rc" -eq 0 ]; then
    echo "grade: PASS (all gates; judge integrity verified)"
else
    echo "grade: FAIL (exit $rc; judge integrity verified)" >&2
fi
exit "$rc"
