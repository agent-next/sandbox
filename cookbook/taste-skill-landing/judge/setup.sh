#!/usr/bin/env bash
# judge/setup.sh — install the pinned judge toolchain into $HOME.
#   python3 venv (playwright 1.63.0, hashes in judge/requirements.txt)
#   Chromium     (browser build pinned by the playwright version)
#   axe-core     4.10.3 (npm tarball, sha256-checked)
# Idempotent: a marker file skips an already-complete install.
#
# Usage: bash judge/setup.sh [--force]
# Exit codes: 0 ok, 1 install/verification failure, 2 no network/sources.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JUDGE_HOME="$HOME/.taste-judge"
VENV="$JUDGE_HOME/venv"
VENV_PY="$VENV/bin/python"
MARKER="$JUDGE_HOME/installed"

PLAYWRIGHT_VERSION="1.63.0"
AXE_VERSION="4.10.3"
AXE_SHA256="0f2b4d7dcdf7d1219df8d1959ad68e565f51d14c3f0d88bb71cd59abeb956292"
AXE_URL="https://registry.npmjs.org/axe-core/-/axe-core-${AXE_VERSION}.tgz"

log() { echo "[setup] $*"; }

SUDO=""
[[ "$(id -u)" -ne 0 ]] && SUDO=sudo
FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

export PLAYWRIGHT_BROWSERS_PATH="$HOME/.cache/ms-playwright"

installed_ok() {
    [[ $FORCE -eq 1 ]] && return 1
    [[ -f "$MARKER" && -x "$VENV_PY" && -f "$JUDGE_HOME/axe/axe.min.js" ]] || return 1
    grep -q "^playwright=${PLAYWRIGHT_VERSION}$" "$MARKER" || return 1
    grep -q "^axe-core=${AXE_VERSION}$" "$MARKER" || return 1
    "$VENV_PY" -c "import playwright" 2>/dev/null || return 1
    "$VENV_PY" -c "from playwright.sync_api import sync_playwright" 2>/dev/null || return 1
}

if installed_ok; then
    log "judge toolchain already installed ($(cat "$MARKER" | tr '\n' ' '))"
    exit 0
fi

# --------------------------------------------------------------------------
# 1. apt lists — fail loudly if the lists did not actually come down.
# --------------------------------------------------------------------------
log "Fetching apt package lists..."
if ! apt_out=$($SUDO apt-get update 2>&1); then
    echo "$apt_out" | tail -3
    log "ERROR: apt-get update failed"
    exit 2
fi
if [[ -z "$(apt-cache policy python3-venv 2>/dev/null | grep Candidate:)" ]] \
   || $(apt-cache policy python3-venv | grep -q 'Candidate: (none)'); then
    log "ERROR: apt lists missing (python3-venv has no candidate)"
    exit 2
fi

$SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    python3-venv python3-pip >/dev/null
log "python3-venv present"

# --------------------------------------------------------------------------
# 2. venv with hashed pins.
# --------------------------------------------------------------------------
log "Creating venv with pinned playwright ${PLAYWRIGHT_VERSION} (hashed)..."
python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip >/dev/null
"$VENV/bin/pip" install --quiet --require-hashes -r "$SCRIPT_DIR/requirements.txt"
"$VENV/bin/pip" check >/dev/null
V=$("$VENV_PY" -m playwright --version)
[[ "$V" == "Version ${PLAYWRIGHT_VERSION}" ]] || {
    log "ERROR: playwright is '$V', expected ${PLAYWRIGHT_VERSION}"; exit 1; }
log "playwright ${PLAYWRIGHT_VERSION} installed (hash-verified wheels)"

# --------------------------------------------------------------------------
# 3. Chromium, build pinned by the playwright package's browsers.json.
#    (Integrity is enforced by playwright's own registry manifest; the build
#     id and browser version are recorded in VERSIONS.txt below.)
# --------------------------------------------------------------------------
log "Installing Chromium (build pinned by playwright ${PLAYWRIGHT_VERSION})..."
"$VENV_PY" -m playwright install --with-deps chromium
"$VENV_PY" - <<'PY' || exit 1
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    exe = p.chromium.executable_path
    assert exe and __import__("os").path.exists(exe), f"chromium missing at {exe}"
    print("[setup] chromium executable:", exe)
PY

# --------------------------------------------------------------------------
# 4. axe-core tarball, sha256-checked.
# --------------------------------------------------------------------------
log "Fetching axe-core ${AXE_VERSION} (sha256-checked)..."
mkdir -p "$JUDGE_HOME/axe"
DL="$(mktemp -d "${TMPDIR:-/tmp}/axe-dl.XXXXXX")"
trap 'rm -rf "$DL"' EXIT
curl -sfL "$AXE_URL" -o "$DL/axe.tgz"
GOT=$(sha256sum "$DL/axe.tgz" | cut -d' ' -f1)
[[ "$GOT" == "$AXE_SHA256" ]] || {
    log "ERROR: axe-core sha256 mismatch"; log "  want $AXE_SHA256"; log "  got  $GOT"; exit 1; }
tar -xzf "$DL/axe.tgz" -C "$DL"
cp "$DL/package/axe.min.js" "$JUDGE_HOME/axe/axe.min.js"
log "axe-core ${AXE_VERSION} verified (sha256 ${AXE_SHA256:0:16}...)"

# --------------------------------------------------------------------------
# 5. Record versions, write the marker.
# --------------------------------------------------------------------------
CHROME_VER=$("$VENV_PY" - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch()
    v = b.version
    b.close()
    print(v)
PY
)
PY_VER=$("$VENV_PY" --version)
cat > "$SCRIPT_DIR/VERSIONS.txt" <<EOF
# recorded by judge/setup.sh at $(date -Iseconds)
playwright: ${PLAYWRIGHT_VERSION} (pip, --require-hashes judge/requirements.txt)
chromium: ${CHROME_VER} (${PLAYWRIGHT_BROWSERS_PATH}, build pinned by playwright ${PLAYWRIGHT_VERSION})
axe-core: ${AXE_VERSION} (npm tarball, sha256 ${AXE_SHA256})
${PY_VER}
pip freeze:
$("$VENV/bin/pip" freeze)
EOF

cat > "$MARKER" <<EOF
playwright=${PLAYWRIGHT_VERSION}
axe-core=${AXE_VERSION}
chromium=${CHROME_VER}
installed_at=$(date -Iseconds)
EOF

log "judge toolchain installed: playwright ${PLAYWRIGHT_VERSION}, chromium ${CHROME_VER}, axe-core ${AXE_VERSION}"
log "(versions in judge/VERSIONS.txt)"
