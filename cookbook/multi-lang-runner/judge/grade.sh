#!/usr/bin/env bash
# cookbook/multi-lang-runner judge: run every gate on an artifact.
#
# Usage:
#   bash judge/grade.sh <artifact_root> [--seed N] [--json out.json] [--cases-dir DIR]
#
# Exit 0 iff every gate passes.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ARTIFACT="${1:-}"
SEED="20261015"
JSON_OUT=""
CASES_DIR=""
while [ $# -gt 1 ]; do
    case "$2" in
        --seed) SEED="$3"; shift 2 ;;
        --json) JSON_OUT="$3"; shift 2 ;;
        --cases-dir) CASES_DIR="$3"; shift 2 ;;
        *) shift ;;
    esac
done

fail() { echo "grade: $*" >&2; exit 1; }

[ -n "$ARTIFACT" ] || fail "usage: grade.sh <artifact_root> [--seed N] [--json out.json] [--cases-dir DIR]"
[ -d "$ARTIFACT" ] || fail "artifact dir not found: $ARTIFACT"

# hash the judge before any artifact code runs
JUDGE_HASH_BEFORE="$(find "$HERE" -type f ! -name 'grade.sh' ! -name 'selftest.sh' \
                     ! -name 'RECEIPT.md' -exec sha256sum {} + | sort | sha256sum)"

SEED_FLAG="--seed $SEED"
JSON_FLAG=""
CASES_FLAG=""
[ -n "$JSON_OUT" ] && JSON_FLAG="--json $JSON_OUT"
[ -n "$CASES_DIR" ] && CASES_FLAG="--cases-dir $CASES_DIR"

python3 "${HERE}/grade.py" "$ARTIFACT" $SEED_FLAG $JSON_FLAG $CASES_FLAG

# the artifact must not have touched the judge
JUDGE_HASH_AFTER="$(find "$HERE" -type f ! -name 'grade.sh' ! -name 'selftest.sh' \
                    ! -name 'RECEIPT.md' -exec sha256sum {} + | sort | sha256sum)"
[ "$JUDGE_HASH_BEFORE" = "$JUDGE_HASH_AFTER" ] \
    || fail "judge sources changed during grading (checksum mismatch)"

echo "grade: PASS (all gates; judge integrity verified)"
