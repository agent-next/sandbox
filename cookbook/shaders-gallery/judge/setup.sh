#!/usr/bin/env bash
# judge/setup.sh — install the pinned toolchain for the shaders-gallery demo.
#
#   * Chromium 150.0.7871.100 (Debian bookworm .debs, sha256-verified
#     against judge/package-sha256.txt before install)
#   * playwright 1.63.0 (pip, requirements.txt with --hash)
#   * shaders 4.0.4 npm tarball (sha256-verified) extracted to
#     $HOME/.shaders-gallery/vendor/ — the only source of library code
#     the judge will ever serve.
#
# Idempotent.  Usage:  bash judge/setup.sh [--force]
# Exit codes: 0 ok, 1 install/verification failure, 2 no network/sources.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHA_FILE="$SCRIPT_DIR/package-sha256.txt"
REQ_FILE="$SCRIPT_DIR/requirements.txt"
VENDOR_DIR="$HOME/.shaders-gallery/vendor"
MARK="$HOME/.shaders-gallery/installed"

CHROMIUM_VERSION="150.0.7871.100-1~deb12u1"
SHADERS_VERSION="4.0.4"
SHADERS_TGZ_SHA256="7672322e80607339d2176d9f19d3d38bd588bdf4e0b94dbc9368c9b60a2fa48d"
SHADERS_URL="https://registry.npmjs.org/shaders/-/shaders-${SHADERS_VERSION}.tgz"

log() { echo "[setup] $*"; }
SUDO=""
if [[ "$(id -u)" -ne 0 ]]; then SUDO=sudo; fi

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

if [[ $FORCE -eq 0 && -f "$MARK" ]] && command -v chromium >/dev/null 2>&1 \
     && python3 -c "import playwright" >/dev/null 2>&1 \
     && [[ -f "$VENDOR_DIR/dist/core/index.js" ]]; then
    log "already installed (rm $MARK or pass --force to redo)"
    exit 0
fi

# --------------------------------------------------------------------------
# 1. Package lists.  Fail early if they did not actually come down.
# --------------------------------------------------------------------------
log "Fetching apt package lists..."
if ! $SUDO apt-get update -qq 2>&1 | tail -3; then
    log "ERROR: apt-get update failed"
    exit 2
fi
if [[ -z "$(find /var/lib/apt/lists -type f -name '*Packages*' -o -name '*deb.debian.org*' 2>/dev/null | head -1)" ]]; then
    log "ERROR: apt lists directory is empty after update"
    exit 2
fi
if [[ "$(apt-cache policy chromium)" != *"$CHROMIUM_VERSION"* ]]; then
    log "ERROR: chromium $CHROMIUM_VERSION not in apt lists"
    exit 2
fi

# --------------------------------------------------------------------------
# 2. Download + sha256-verify the pinned Chromium .debs, then install.
# --------------------------------------------------------------------------
if [[ "$(dpkg-query -W -f='${Version}' chromium 2>/dev/null || true)" != "$CHROMIUM_VERSION" ]]; then
    log "Downloading pinned Chromium packages..."
    DL="$(mktemp -d "${TMPDIR:-/tmp}/cr-dl.XXXXXX")"
    trap 'rm -rf "$DL"' EXIT
    cd "$DL"
    PKGSPECS=()
    while read -r sha fname; do
        [[ "$sha" == \#* || -z "$sha" ]] && continue
        name="${fname%%_*}"; ver="${fname#*_}"; ver="${ver%_*}"
        PKGSPECS+=("${name}=${ver}")
    done < "$SHA_FILE"
    if ! apt-get download "${PKGSPECS[@]}" >/dev/null 2>&1; then
        log "ERROR: could not download the pinned .deb set"
        exit 1
    fi
    log "Verifying sha256 of every downloaded .deb..."
    while read -r want fname; do
        [[ "$want" == \#* || -z "$want" ]] && continue
        got="$(sha256sum "$fname" | cut -d' ' -f1)"
        if [[ "$got" != "$want" ]]; then
            log "ERROR: sha256 mismatch on $fname"
            exit 1
        fi
    done < "$SHA_FILE"
    log "Installing (remaining dependencies resolve via apt)..."
    $SUDO apt-get install -y ./*.deb >/dev/null
    cd - >/dev/null
    rm -rf "$DL"; trap - EXIT
else
    log "chromium $CHROMIUM_VERSION already installed"
fi
chromium --version | head -1

# --------------------------------------------------------------------------
# 3. playwright (pinned + hashed) — used only to drive the browser.
#    Browsers are NOT playwright-installed; we launch the pinned system
#    chromium via executable_path.
# --------------------------------------------------------------------------
if ! python3 -c "import playwright, importlib.metadata as m; assert m.version('playwright')=='1.63.0'" >/dev/null 2>&1; then
    log "Installing pinned playwright..."
    python3 -m pip install --user -r "$REQ_FILE"
else
    log "playwright 1.63.0 already installed"
fi

# --------------------------------------------------------------------------
# 4. shaders 4.0.4 tarball — sha256-verified — extracted as the vendor bundle.
# --------------------------------------------------------------------------
if [[ ! -f "$VENDOR_DIR/dist/core/index.js" || $FORCE -eq 1 ]]; then
    log "Downloading shaders $SHADERS_VERSION tarball..."
    TMP="$(mktemp -d "${TMPDIR:-/tmp}/sh-dl.XXXXXX")"
    trap 'rm -rf "$TMP"' EXIT
    curl -fsSL "$SHADERS_URL" -o "$TMP/shaders.tgz"
    got="$(sha256sum "$TMP/shaders.tgz" | cut -d' ' -f1)"
    if [[ "$got" != "$SHADERS_TGZ_SHA256" ]]; then
        log "ERROR: sha256 mismatch on shaders tarball ($got)"
        exit 1
    fi
    mkdir -p "$VENDOR_DIR"
    tar xzf "$TMP/shaders.tgz" -C "$TMP"
    rm -rf "${VENDOR_DIR:?}/dist"
    cp -r "$TMP/package/dist" "$VENDOR_DIR/dist"
    cp "$TMP/package/LICENSE" "$VENDOR_DIR/LICENSE"
    echo "$SHADERS_VERSION" > "$VENDOR_DIR/VERSION"
    rm -rf "$TMP"; trap - EXIT
    log "vendor bundle at $VENDOR_DIR (shaders $SHADERS_VERSION)"
else
    log "vendor bundle already present (shaders $(cat "$VENDOR_DIR/VERSION" 2>/dev/null || echo '?'))"
fi

mkdir -p "$(dirname "$MARK")"
date -u +"%Y-%m-%dT%H:%M:%SZ" > "$MARK"
log "done"
