#!/usr/bin/env bash
# cookbook/rp1-mujoco judge: grade one controller artifact.
#
# Usage:
#   bash judge/grade.sh <controller.py> [--seed N] [--json out.json]
#
# 1. checks the pinned tools are installed (judge/setup.sh)
# 2. assembles the judged scene: a scratch copy of the pinned model with the
#    scene include rewritten to robot_24dof.xml (upstream rp1_flat.xml points
#    at the 30-dof robot.xml)
# 3. copies the artifact into a scratch dir and runs every gate (grade.py)
# 4. verifies the judge sources were not modified by the artifact
#
# Exit 0 iff every gate passes.  Prints one verdict JSON object.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${HOME}/.rp1-mujoco-tools"
VENV="${PREFIX}/venv"
MODEL_DIR="${PREFIX}/rp1_description"
PY="${VENV}/bin/python"

ARTIFACT="${1:-}"
SEED="20261014"
JSON_OUT=""
while [ $# -gt 1 ]; do
    case "$2" in
        --seed) SEED="$3"; shift 2 ;;
        --json) JSON_OUT="$3"; shift 2 ;;
        *) shift ;;
    esac
done

fail() { echo "grade: $*" >&2; exit 1; }

[ -n "$ARTIFACT" ] || fail "usage: grade.sh <controller.py> [--seed N] [--json out.json]"
[ -f "$ARTIFACT" ] || fail "artifact not found: $ARTIFACT"
[ -x "$PY" ] || fail "pinned venv missing -- run 'bash judge/setup.sh' first (expected ${PY})"
[ -f "${MODEL_DIR}/mjcf/robot_24dof.xml" ] \
    || fail "pinned model clone missing -- run 'bash judge/setup.sh' first (expected ${MODEL_DIR})"

# hash the judge before any artifact code runs
JUDGE_HASH_BEFORE="$(cd "$HERE" && find . -type f ! -name VERSIONS.txt | sort | xargs sha256sum | sha256sum)"

SCRATCH="$(mktemp -d)"
trap 'rm -rf "${SCRATCH}"' EXIT
mkdir -p "${SCRATCH}/agent"
cp "$ARTIFACT" "${SCRATCH}/agent/controller.py"

# assemble the scene: pinned model copy with the 24-dof robot
cp -r "${MODEL_DIR}/mjcf" "${SCRATCH}/mjcf"
cp -r "${MODEL_DIR}/meshes" "${SCRATCH}/meshes"
sed -i 's|<include file="robot.xml"/>|<include file="robot_24dof.xml"/>|' \
    "${SCRATCH}/mjcf/rp1_flat.xml"
grep -q 'robot_24dof.xml' "${SCRATCH}/mjcf/rp1_flat.xml" \
    || fail "scene rewrite failed: no robot.xml include found to rewrite"

export OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1

set +e
"$PY" "${HERE}/grade.py" \
    --artifact "${SCRATCH}/agent/controller.py" \
    --scene "${SCRATCH}/mjcf/rp1_flat.xml" \
    --urdf "${MODEL_DIR}/urdf/rp1_24dof.urdf" \
    --params "${HERE}/params.json" \
    --judge-dir "${HERE}" \
    --seed "$SEED" ${JSON_OUT:+--json "$JSON_OUT"}
RC=$?
set -e

# the artifact must not have touched the judge
JUDGE_HASH_AFTER="$(cd "$HERE" && find . -type f ! -name VERSIONS.txt | sort | xargs sha256sum | sha256sum)"
[ "$JUDGE_HASH_BEFORE" = "$JUDGE_HASH_AFTER" ] \
    || fail "judge sources changed during grading (checksum mismatch)"

exit $RC
