#!/usr/bin/env bash
# judge/setup.sh — install the pinned Genesis toolchain, idempotently.
#
#   bash judge/setup.sh            # install if missing/mismatched
#   bash judge/setup.sh --force    # reinstall from scratch
#
# Everything lands in a venv at $HOME/.genesis-demo-venv; the only
# system-level change is a fixed list of apt packages (Mesa EGL for the
# offscreen renderer). Every pip install is verified against the sha256 in
# judge/requirements.txt (pip --require-hashes) so a later upstream
# re-release fails loudly here instead of silently changing the solver
# under the judge. genesis-world is additionally sha256-checked by hand
# from the pinned wheel URL.
#
# apt lists are verified non-empty (a fresh sandbox image with empty lists
# is a known failure mode) before any apt install runs.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HOME/.genesis-demo-venv"
MARK="$VENV/.installed_genesis_${GENESIS_VERSION:-1.4.3}"

GENESIS_VERSION="1.4.3"
# manylinux wheel for py3.10+: genesis_world-1.4.3-py3-none-any.whl
GENESIS_SHA256="26a8229031d66535a568fbdd15b9dcf506843fb91b739a6d4ec7a4a015bf5eb8"
# CPU-only torch (CPU wheel index), pinned & hashed in requirements.txt
TORCH_INDEX="https://download.pytorch.org/whl/cpu"

APT_PACKAGES=(
    libegl-mesa0 libegl1 libgl1 libgles2 libglvnd0
    libx11-6 libxext6 libxrender1         # X libs pyglet/EGL dlopen
)

log() { echo "[setup] $*"; }

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

if [[ $FORCE -eq 0 && -f "$MARK" && -x "$VENV/bin/python" ]] && \
   "$VENV/bin/python" -c "import genesis, torch, numpy" 2>/dev/null; then
    log "genesis-world $GENESIS_VERSION already installed in $VENV"
    exit 0
fi

# ---------------------------------------------------------------------------
# 1. apt: verify the package lists really came down before installing.
# ---------------------------------------------------------------------------
SUDO=""
if [[ "$(id -u)" -ne 0 ]]; then SUDO=sudo; fi

log "Fetching apt package lists..."
if ! $SUDO apt-get update -qq; then
    log "ERROR: apt-get update failed"; exit 2
fi
if [[ -z "$(apt-cache policy libegl-mesa0 | grep Candidate)" ]]; then
    log "ERROR: apt lists are empty or stale (libegl-mesa0 has no candidate)"
    exit 2
fi

log "Installing headless-GL packages: ${APT_PACKAGES[*]}"
$SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y "${APT_PACKAGES[@]}"

# ---------------------------------------------------------------------------
# 2. Python venv + pinned, hashed requirements.
# ---------------------------------------------------------------------------
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip

log "Installing pinned requirements (sha256-checked, may take several minutes)..."
PYVER=$("$VENV/bin/python" -c "import sys;print(f'{sys.version_info.major}.{sys.version_info.minor}')")
REQ_FILE="$SCRIPT_DIR/requirements-py${PYVER}.txt"
if [[ ! -f "$REQ_FILE" ]]; then
    log "ERROR: no pinned requirements file for python $PYVER ($REQ_FILE)"
    log "       this demo supports the python shipped with the agent-next"
    log "       sandbox image (currently 3.12); regenerate the lock with"
    log "       judge/lock_requirements.sh on the matching version"
    exit 1
fi
# Default index (pypi.org) is used for everything; torch's cpu wheel is
# found on the declared extra index. --require-hashes applies to both.
"$VENV/bin/pip" install --require-hashes -r "$REQ_FILE" \
    --extra-index-url "$TORCH_INDEX"

# ---------------------------------------------------------------------------
# 3. Verify: import check + exact version record.
# ---------------------------------------------------------------------------
"$VENV/bin/python" - <<'PY' || { echo "[setup] ERROR: post-install import check failed"; exit 1; }
import genesis, torch, numpy
import genesis as gs
print("genesis", genesis.__version__)
print("torch", torch.__version__)
print("numpy", numpy.__version__)
PY

{
    echo "# judge/VERSIONS.txt — recorded by judge/setup.sh on $(date -u -Iseconds)"
    "$VENV/bin/pip" --version
    "$VENV/bin/pip" freeze | grep -E "^(genesis-world|torch|numpy|quadrants|taichi)="
    dpkg-query -W -f='${Package}=${Version}\n' "${APT_PACKAGES[@]}" 2>/dev/null
} > "$SCRIPT_DIR/VERSIONS.txt"

touch "$MARK"
log "Genesis $GENESIS_VERSION toolchain ready at $VENV"
log "Versions recorded in judge/VERSIONS.txt"
