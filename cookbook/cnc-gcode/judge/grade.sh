#!/usr/bin/env bash
# cookbook/cnc-gcode judge: run an artifact's cam.py and grade every gate.
#
# Usage:
#   bash judge/grade.sh <cam.py> [--seed N] [--json out.json]
#
# 1. hashes the judge sources (the artifact must not modify them)
# 2. copies the artifact + the repo's own spec.json into a scratch dir
# 3. runs  python3 cam.py --spec spec.json --out part.nc   (venv interpreter)
# 4. grades part.nc with grade.py: program, envelope, stepdown, stepover,
#    process, rapid_safety, residual, gouge, simulator_selfcheck
# 5. re-hashes the judge sources; any change is a failure
#
# Exit 0 iff every gate passes.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${HOME}/.cnc-gcode/venv"
PYBIN="${VENV}/bin/python"

ARTIFACT="${1:-}"
SEED="20261014"
JSON_OUT=""
rc=0
while [ $# -gt 1 ]; do
    case "$2" in
        --seed) SEED="$3"; shift 2 ;;
        --json) JSON_OUT="$3"; shift 2 ;;
        *) shift ;;
    esac
done

fail() { echo "grade: $*" >&2; exit 1; }

[ -n "$ARTIFACT" ] || fail "usage: grade.sh <cam.py> [--seed N] [--json out.json]"
[ -f "$ARTIFACT" ] || fail "artifact not found: $ARTIFACT"
[ -x "$PYBIN" ] || fail "judge venv missing ($PYBIN) -- run 'bash judge/setup.sh' first"

# judge integrity hash before the artifact runs
JUDGE_HASH_BEFORE="$(find "$HERE" -type f \
    ! -name setup.sh ! -name grade.sh ! -name selftest.sh ! -name VERSIONS.txt \
    ! -name RECEIPT.md ! -path '*/__pycache__/*' -exec sha256sum {} + | sort | sha256sum | awk '{print $1}')"

# scratch: the artifact + the repo's own spec (never the artifact's spec)
WORK="$(mktemp -d)/grading"
mkdir -p "$WORK"
cp "$ARTIFACT" "$WORK/cam.py"
cp "$HERE/../spec.json" "$WORK/spec.json"

"$PYBIN" "$HERE/grade.py" \
    --work-dir "$WORK" \
    --artifact-label "$ARTIFACT" \
    --spec "$WORK/spec.json" \
    --seed "$SEED" ${JSON_OUT:+--json "$JSON_OUT"} || rc=$?

# the artifact must not have touched the judge
JUDGE_HASH_AFTER="$(find "$HERE" -type f \
    ! -name setup.sh ! -name grade.sh ! -name selftest.sh ! -name VERSIONS.txt \
    ! -name RECEIPT.md ! -path '*/__pycache__/*' -exec sha256sum {} + | sort | sha256sum | awk '{print $1}')"
[ "$JUDGE_HASH_BEFORE" = "$JUDGE_HASH_AFTER" ] \
    || fail "judge sources changed during grading (checksum mismatch)"

exit "${rc:-0}"
