#!/usr/bin/env bash
# judge/setup.sh — install the pinned toolchain for the WebGL fluid judge,
# idempotently, into $HOME (plus a few Ubuntu apt libraries for Chromium,
# which are not pip/npm installable):
#
#   node          v20.19.5   (nodejs.org tarball, sha256-verified)
#   playwright-core 1.55.0   (npm registry tarball, sha256-verified)
#   chromium      build 1187 (Playwright CDN zip, sha256-verified)
#   upstream      WebGL-Fluid-Simulation @ a2d29293 (sha256-verified)
#
# Everything from the network is sha256-checked before use. Versions were
# chosen so the newest is at least two weeks old at demo build time
# (2026-10-15); each pin records its upstream release date.
#
# Usage:
#   bash judge/setup.sh            # install
#   bash judge/setup.sh --force    # reinstall even if already present
#
# Exit codes: 0 ok, 1 install/verification failure, 2 no network.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="$HOME/.wfs-fluid"
MARK="$PREFIX/.setup_done"
FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

log() { echo "[setup] $*"; }

# ---------------------------------------------------------------------------
# Pins (name, version, release date, sha256 of the downloaded artifact)
# ---------------------------------------------------------------------------
NODE_VERSION="v20.19.5"            # nodejs.org, released 2025-09-09 (LTS)
NODE_SHA256="315046739a513a70e03a4a55a8afda8cf979f30852e576075c340084e3f8ac0f"
NODE_URL="https://nodejs.org/dist/${NODE_VERSION}/node-${NODE_VERSION}-linux-x64.tar.xz"

PW_VERSION="1.55.0"                # npm, released 2025-08-20
PW_SHA256="6b63fdf41725afb924880728d39cf560d770f785a861d18c15611e99dd3172bd"
PW_URL="https://registry.npmjs.org/playwright-core/-/playwright-core-${PW_VERSION}.tgz"

CHROMIUM_REVISION="1187"           # Chromium 140.0.7339.16, Playwright build
CHROMIUM_SHA256="395e829e88f9ff3fc108cc9a3db49907afd9f5860066e9678694b01a406ee979"
CHROMIUM_URL="https://cdn.playwright.dev/dbazure/download/playwright/builds/chromium/${CHROMIUM_REVISION}/chromium-linux.zip"

UPSTREAM_SHA="a2d292931f19d9b3b9f564e23e6c32729d2121c3"
UPSTREAM_BASE="https://raw.githubusercontent.com/PavelDoGreat/WebGL-Fluid-Simulation/${UPSTREAM_SHA}"
SCRIPT_SHA256="291d86de38ea23b8fb63d1879afeea77e9a4556900bbd67e13bc1d5ea007ce4e"
DATGUI_SHA256="27976ca8ac2e125de97163455131890e8686ed2afc2007cd5524080b7d53ef7b"
LICENSE_SHA256="1be448ae1212de2bee77b4cf851ab0acea0a7f7f32d21cd73095dd94dc173f66"

# ---------------------------------------------------------------------------

if [[ $FORCE -eq 0 && -f "$MARK" ]]; then
    log "toolchain already installed at $PREFIX (use --force to redo)"
    exit 0
fi

SUDO=""
if [[ "$(id -u)" -ne 0 ]]; then SUDO=sudo; fi

# ---------------------------------------------------------------------------
# 1. Chromium runtime libraries (apt, from Ubuntu). Fail if `apt-get update`
#    did not actually fetch lists (empty apt lists are a known fresh-image
#    failure mode).
# ---------------------------------------------------------------------------
log "fetching apt package lists"
$SUDO apt-get update -qq
if [[ -z "$($SUDO apt-get -qq --print-uris install libnss3 2>/dev/null)" ]] &&
   ! dpkg -s libnss3 >/dev/null 2>&1; then
    log "ERROR: apt package lists are empty or broken"; exit 2
fi
log "installing chromium runtime libraries (apt)"
$SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 libpango-1.0-0 \
    libcairo2 libatspi2.0-0 libx11-6 libxcb1 libxext6 libxi6 libxtst6 \
    bc >/dev/null

fetch() {  # fetch <url> <dest> <sha256>
    log "downloading $(basename "$2")"
    if ! curl -sfL --retry 3 -o "$2" "$1"; then
        log "ERROR: download failed: $1"; exit 2
    fi
    local got; got=$(sha256sum "$2" | cut -d' ' -f1)
    if [[ "$got" != "$3" ]]; then
        log "ERROR: sha256 mismatch for $2"
        log "       expected $3"; log "       got      $got"
        exit 1
    fi
}

DL="$(mktemp -d "${TMPDIR:-/tmp}/wfs-setup.XXXXXX")"
trap 'rm -rf "$DL"' EXIT

mkdir -p "$PREFIX"/{node,playwright,chromium,upstream}

# ---------------------------------------------------------------------------
# 2. Node.js $NODE_VERSION
# ---------------------------------------------------------------------------
if [[ ! -x "$PREFIX/node/bin/node" ]]; then
    fetch "$NODE_URL" "$DL/node.tar.xz" "$NODE_SHA256"
    tar -xJf "$DL/node.tar.xz" -C "$PREFIX/node" --strip-components=1
fi
export PATH="$PREFIX/node/bin:$PATH"
hash -r

# ---------------------------------------------------------------------------
# 3. playwright-core (into judge/vendor/node_modules, so run_scene.cjs has
#    zero-install deps resolved by Node's own module lookup)
# ---------------------------------------------------------------------------
VENDOR="$SCRIPT_DIR/vendor"
if [[ ! -d "$VENDOR/node_modules/playwright-core" ]]; then
    fetch "$PW_URL" "$DL/pw.tgz" "$PW_SHA256"
    mkdir -p "$VENDOR/node_modules"
    tar -xzf "$DL/pw.tgz" -C "$VENDOR/node_modules"
    mv "$VENDOR/node_modules/package" "$VENDOR/node_modules/playwright-core"
fi

# ---------------------------------------------------------------------------
# 4. Chromium build 1187 (SwiftShader WebGL works headless on CPU)
# ---------------------------------------------------------------------------
if [[ ! -x "$PREFIX/chromium/chrome-linux/chrome" ]]; then
    fetch "$CHROMIUM_URL" "$DL/chromium.zip" "$CHROMIUM_SHA256"
    (cd "$PREFIX/chromium" && python3 -m zipfile -e "$DL/chromium.zip" .)
    # python's zipfile does not restore the execute bit
    chmod -R u+rwX,go+rX "$PREFIX/chromium"
    chmod +x "$PREFIX/chromium/chrome-linux/chrome" \
             "$PREFIX/chromium/chrome-linux/chrome_crashpad_handler" \
             "$PREFIX/chromium/chrome-linux/chrome_sandbox" 2>/dev/null || true
    find "$PREFIX/chromium/chrome-linux" -maxdepth 1 -name "*.so" -o \
         -maxdepth 1 -name "swiftshader" -type d | while read -r f; do
        [[ -d "$f" ]] && chmod +x "$f"/lib*.so 2>/dev/null; done
fi
export PLAYWRIGHT_BROWSERS_PATH="$PREFIX"
# Symlink into the layout playwright-core expects:
# $PLAYWRIGHT_BROWSERS_PATH/chromium-1187/chrome-linux/chrome
mkdir -p "$PREFIX"
if [[ ! -e "$PREFIX/chromium-${CHROMIUM_REVISION}" ]]; then
    ln -s "$PREFIX/chromium" "$PREFIX/chromium-${CHROMIUM_REVISION}"
fi
# playwright >= 1.50 launches the separate headless_shell binary by default;
# the classic chromium build carries chrome only. A rebuild is a one-line
# shim: point playwright at the full chrome for headless launches too.
if [[ ! -e "$PREFIX/chromium_headless_shell-${CHROMIUM_REVISION}" ]]; then
    ln -s "$PREFIX/chromium" \
          "$PREFIX/chromium_headless_shell-${CHROMIUM_REVISION}"
    ln -sf chrome "$PREFIX/chromium/chrome-linux/headless_shell" 2>/dev/null ||
        cp "$PREFIX/chromium/chrome-linux/chrome" \
           "$PREFIX/chromium/chrome-linux/headless_shell"
fi

# ---------------------------------------------------------------------------
# 5. Upstream sources at the pinned commit (LICENSE required by MIT)
# ---------------------------------------------------------------------------
UP="$SCRIPT_DIR/upstream"
mkdir -p "$UP"
fetch "${UPSTREAM_BASE}/script.js"      "$UP/script.js"      "$SCRIPT_SHA256"
fetch "${UPSTREAM_BASE}/dat.gui.min.js" "$UP/dat.gui.min.js" "$DATGUI_SHA256"
fetch "${UPSTREAM_BASE}/LICENSE"        "$UP/LICENSE"        "$LICENSE_SHA256"

# ---------------------------------------------------------------------------
# 6. Record what is actually installed.
# ---------------------------------------------------------------------------
{
    echo "# What judge/setup.sh actually installed (tool-reported versions)"
    echo "# reproduce: bash judge/setup.sh && bash judge/versions.sh > judge/VERSIONS.txt"
    echo
    echo "\$ node --version"
    "$PREFIX/node/bin/node" --version
    echo
    echo "\$ chromium --version (build $CHROMIUM_REVISION)"
    "$PREFIX/chromium/chrome-linux/chrome" --version
    echo
    echo "\$ node -p playwright-core/package.json .version"
    "$PREFIX/node/bin/node" -p \
        "require('$VENDOR/node_modules/playwright-core/package.json').version"
    echo
    echo "# upstream: PavelDoGreat/WebGL-Fluid-Simulation @ $UPSTREAM_SHA"
    sha256sum "$UP"/script.js "$UP"/dat.gui.min.js "$UP"/LICENSE
    echo
    echo "# apt: chromium runtime libraries"
    for p in libnss3 libatk-bridge2.0-0 libcups2 libgbm1 libasound2; do
        echo "$p $(dpkg-query -W -f='${Version}' "$p" 2>/dev/null || echo MISSING)"
    done
} > "$SCRIPT_DIR/VERSIONS.txt"

date -Iseconds > "$MARK"
log "done -- versions recorded in judge/VERSIONS.txt"
