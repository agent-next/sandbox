#!/usr/bin/env bash
#
# setup.sh -- install the tools this demo judges with, pinned and
# sha256-checked, into $HOME.  Idempotent: a second run is a no-op.
#
# Sourced in this order of preference:
#   1. exact pip wheel, sha256 verified          (mujoco 3.14.0)
#   2. git clone at a pinned SHA                 (rp1_description, robot model)
# Nothing is downloaded from a `latest` URL; every version is spelled out.

set -euo pipefail

PREFIX="${HOME}/.rp1-mujoco-tools"
VENV="${PREFIX}/venv"
MODEL_DIR="${PREFIX}/rp1_description"
mkdir -p "${PREFIX}"

log() { printf 'setup: %s\n' "$*"; }

# --------------------------------------------------------------------------
# 0. Interpreter.  Python >= 3.10, < 3.16 (mujoco 3.14.0 ships cp310..cp315
#    wheels).  A venv keeps the pinned mujoco off the system site-packages.
# --------------------------------------------------------------------------
PY="$(command -v python3 || true)"
if [ -z "$PY" ]; then
    echo "setup: python3 not found on PATH" >&2
    exit 1
fi
"$PY" - <<'PYPYVER'
import sys
major, minor = sys.version_info[:2]
if major != 3 or not (10 <= minor <= 15):
    raise SystemExit(
        f"setup: python {major}.{minor} unsupported "
        "(need 3.10..3.15 for the pinned mujoco wheel)")
PYPYVER

# --------------------------------------------------------------------------
# 1. mujoco 3.14.0 + numpy -- exact wheels pinned by
#    judge/requirements.txt, hash-checked by pip itself.
# --------------------------------------------------------------------------
REQ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/requirements.txt"

if [ ! -x "${VENV}/bin/python" ]; then
    log "creating venv ${VENV}"
    "$PY" -m venv "${VENV}"
fi
PIP="${VENV}/bin/pip"

# pip needs to be new enough for --require-hashes on modern wheels; the
# Debian python3-venv pip is often too old, so bootstrap via get-pip only
# if the venv pip is older than 23.
PIPVER="$("${PIP}" --version | awk '{print $2}')"
PIP_MAJOR="${PIPVER%%.*}"
if [ "${PIP_MAJOR:-0}" -lt 23 ]; then
    log "bootstrapping pip 24.2 (pinned, sha256-checked)"
    GETPIP_SHA256="5da5ff19ab1dfb47b180a4eb2ba60486764f56b7e1b2e1b7dec969321f3b5b1c"
    curl -fsSL --retry 5 --retry-delay 3 --retry-all-errors \
        -o "${PREFIX}/get-pip.py.part" \
        https://bootstrap.pypa.io/get-pip.py
    echo "${GETPIP_SHA256}  ${PREFIX}/get-pip.py.part" | sha256sum -c - \
        || { rm -f "${PREFIX}/get-pip.py.part"; echo "setup: bad get-pip download" >&2; exit 1; }
    mv "${PREFIX}/get-pip.py.part" "${PREFIX}/get-pip.py"
    "${VENV}/bin/python" "${PREFIX}/get-pip.py" "pip==24.2" -q
    rm -f "${PREFIX}/get-pip.py"
fi

log "installing pinned wheels from judge/requirements.txt (hashes enforced)"
"${PIP}" install --quiet --require-hashes -r "${REQ}"

MUJOCO_VER="$("${VENV}/bin/python" -c 'import mujoco; print(mujoco.__version__)')"
NUMPY_VER="$("${VENV}/bin/python" -c 'import numpy; print(numpy.__version__)')"

# --------------------------------------------------------------------------
# 2. rp1_description at the pinned SHA.  Cloned at run time, never copied
#    into this repo (the upstream repo has no licence file).
# --------------------------------------------------------------------------
MODEL_SHA="84529a55649b5c9796d49093c266208c879f9f29"
MODEL_URL="https://github.com/Roboparty/rp1_description"

if [ -d "${MODEL_DIR}/.git" ]; then
    HAVE="$(git -C "${MODEL_DIR}" rev-parse HEAD 2>/dev/null || echo none)"
    if [ "${HAVE}" != "${MODEL_SHA}" ]; then
        log "rp1_description present but at ${HAVE}; re-cloning at pinned SHA"
        rm -rf "${MODEL_DIR}"
    fi
fi
if [ ! -d "${MODEL_DIR}/.git" ]; then
    log "cloning rp1_description"
    git clone --quiet --no-checkout "${MODEL_URL}" "${MODEL_DIR}"
    git -C "${MODEL_DIR}" checkout --quiet "${MODEL_SHA}"
    HAVE="$(git -C "${MODEL_DIR}" rev-parse HEAD)"
    if [ "${HAVE}" != "${MODEL_SHA}" ]; then
        echo "setup: cloned rp1_description at ${HAVE}, expected ${MODEL_SHA}" >&2
        exit 1
    fi
else
    log "rp1_description already at pinned SHA"
fi

# The files the demo actually needs:
for f in mjcf/rp1_flat.xml mjcf/robot_24dof.xml urdf/rp1_24dof.urdf; do
    if [ ! -f "${MODEL_DIR}/${f}" ]; then
        echo "setup: ${MODEL_DIR}/${f} missing after checkout" >&2
        exit 1
    fi
done

# --------------------------------------------------------------------------
# 3. Record what is installed: judge/VERSIONS.txt holds the pinned versions
#    and the tools' own --version output, next to the scripts that installed
#    them.
# --------------------------------------------------------------------------
JUDGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
{
    echo "# VERSIONS.txt -- recorded by judge/setup.sh"
    echo "# One entry per tool this demo judges with: the pinned version, the"
    echo "# sha256 the download was verified against, and the tool's own"
    echo "# --version output as actually installed."
    echo
    echo "mujoco ${MUJOCO_VER} (pip, pinned sha256 in judge/requirements.txt)"
    "${VENV}/bin/python" -c 'import mujoco; print("  mujoco", mujoco.__version__)'
    echo
    echo "numpy ${NUMPY_VER} (pip, pinned sha256 in judge/requirements.txt)"
    "${VENV}/bin/python" -c 'import numpy; print("  numpy", numpy.__version__)'
    echo
    echo "python3"
    "${VENV}/bin/python" --version 2>&1 | sed 's/^/  /'
    echo
    echo "rp1_description"
    echo "  url : ${MODEL_URL}"
    echo "  sha : ${MODEL_SHA}"
    git -C "${MODEL_DIR}" log -1 --format='  %H %cI %s' | sed 's/^/  /'
} > "${JUDGE_DIR}/VERSIONS.txt"

log "wrote ${JUDGE_DIR}/VERSIONS.txt"
log "done"
