#!/usr/bin/env bash
# Install the pinned tools for the web-scrape-dataset judge into $HOME.
#
#   bash judge/setup.sh
#
# Idempotent: re-running it re-verifies the hashes and does nothing else.
# Everything lands under $HOME so the judge never needs root:
#
#   $HOME/.web-scrape-dataset/venv         Playwright 1.63.0 (pinned wheel, sha256)
#   $HOME/.web-scrape-dataset/browsers     Chromium headless shell 153.0.8010.12
#   $HOME/.web-scrape-dataset/VERSIONS.txt what was actually installed
#
# If a system Playwright browser tree already exists (PLAYWRIGHT_BROWSERS_PATH,
# or the image's own /opt/ms-playwright) the download is skipped and the
# existing tree is hashed into VERSIONS.txt instead, so a pre-warmed image does
# not re-fetch 115 MB. The judge exports PLAYWRIGHT_BROWSERS_PATH to match.
#
# No `latest` anywhere: the wheel, the browser build and the version pins are
# exact. Nothing here is published in the last two weeks.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="${WSD_HOME:-$HOME/.web-scrape-dataset}"
VENV="$ROOT/venv"
BROWSERS="$ROOT/browsers"
VERSIONS="$ROOT/VERSIONS.txt"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# ---- pinned versions -------------------------------------------------------
PLAYWRIGHT_VERSION=1.63.0
# the wheel sha256 lives in judge/requirements.txt, which pip checks with
# --require-hashes; the browser archive hash is checked below by hand
CHROMIUM_BUILD=153.0.8010.12
CHROMIUM_REV=1243
CHROMIUM_ZIP_SHA256=a9da028861a0cf789ff25c2fed45f5f1aaf969ed9247835b6a7821a4f7af9d1d
CHROMIUM_URL="https://cdn.playwright.dev/builds/cft/${CHROMIUM_BUILD}/linux64/chrome-headless-shell-linux64.zip"
CHROMIUM_FALLBACK="https://playwright.download.prss.microsoft.com/dbazure/download/playwright/builds/cft/${CHROMIUM_BUILD}/linux64/chrome-headless-shell-linux64.zip"

log() { printf '[setup] %s\n' "$*"; }
die() { printf '[setup] ERROR: %s\n' "$*" >&2; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || die "missing required tool: $1"; }
need python3
need curl
need sha256sum
need tar

mkdir -p "$ROOT"

# ---- 1. Playwright + runtime deps, hash-checked ---------------------------
installed_version() {
    "$VENV/bin/python" -c \
        'from importlib.metadata import version; print(version("playwright"))' \
        2>/dev/null || true
}

if [ "$(installed_version)" = "$PLAYWRIGHT_VERSION" ] \
   && "$VENV/bin/python" -c 'import playwright.sync_api' 2>/dev/null; then
    log "Playwright $PLAYWRIGHT_VERSION already installed in $VENV"
else
    log "installing Playwright $PLAYWRIGHT_VERSION (hash-pinned requirements)"
    rm -rf "$VENV"
    python3 -m venv "$VENV"
    "$VENV/bin/python" -m pip install --quiet --upgrade pip >/dev/null
    # --require-hashes: every artifact must match judge/requirements.txt
    "$VENV/bin/python" -m pip install --quiet --require-hashes \
        -r "$HERE/requirements.txt"
fi
[ "$(installed_version)" = "$PLAYWRIGHT_VERSION" ] \
    || die "Playwright version check failed: got '$(installed_version)'"
log "playwright $PLAYWRIGHT_VERSION importable"

# ---- 2. Chromium headless shell, sha256-checked ---------------------------
preinstalled=""
for cand in "${PLAYWRIGHT_BROWSERS_PATH:-}" /opt/ms-playwright "$HOME/.cache/ms-playwright"; do
    [ -n "$cand" ] || continue
    if [ -x "$cand/chromium_headless_shell-$CHROMIUM_REV/chrome-headless-shell-linux64/chrome-headless-shell" ]; then
        preinstalled="$cand"
        break
    fi
done

if [ -n "$preinstalled" ]; then
    log "using the pre-installed browser tree at $preinstalled"
    BROWSERS="$preinstalled"
else
    shell="$BROWSERS/chromium_headless_shell-$CHROMIUM_REV/chrome-headless-shell-linux64/chrome-headless-shell"
    if [ -x "$shell" ]; then
        log "Chromium headless shell $CHROMIUM_BUILD already installed in $BROWSERS"
    else
        log "downloading Chromium headless shell $CHROMIUM_BUILD"
        zip="$TMP/chrome-headless-shell-linux64.zip"
        if ! curl -fsSL --retry 3 --retry-delay 2 -o "$zip" "$CHROMIUM_URL"; then
            log "primary CDN failed, trying the fallback mirror"
            curl -fsSL --retry 3 --retry-delay 2 -o "$zip" "$CHROMIUM_FALLBACK" \
                || die "could not download $CHROMIUM_URL"
        fi
        got="$(sha256sum "$zip" | cut -d' ' -f1)"
        [ "$got" = "$CHROMIUM_ZIP_SHA256" ] \
            || die "chromium zip sha256 mismatch: got $got want $CHROMIUM_ZIP_SHA256"
        log "zip sha256 ok: $got"
        mkdir -p "$BROWSERS/chromium_headless_shell-$CHROMIUM_REV"
        tar -xzf "$zip" -C "$BROWSERS/chromium_headless_shell-$CHROMIUM_REV"
        # Playwright only treats a browser dir as installed when this marker
        # exists; without it `playwright install` would try to re-download.
        : > "$BROWSERS/chromium_headless_shell-$CHROMIUM_REV/INSTALLATION_COMPLETE"
        [ -x "$shell" ] || die "extracted archive has no chrome-headless-shell at $shell"
    fi
fi

browser_bin="$BROWSERS/chromium_headless_shell-$CHROMIUM_REV/chrome-headless-shell-linux64/chrome-headless-shell"

# ---- 3. system libraries the browser needs --------------------------------
# Chromium links against a handful of shared libraries a slim image may not
# ship. Install them only when one is actually missing: a real run once died on
# libGL.so.1 that no static checklist had caught. `apt-get update` is checked
# (this image can start with empty lists) and a failure is reported, never
# swallowed.
needed_libs() {
    local shell="$1" missing=()
    while read -r lib; do
        [ -n "$lib" ] || continue
        case "$lib" in libEGL.so.1|libGLESv2.so.2|libvk_swiftshader.so) continue ;; esac
        missing+=("$lib")
    done < <(ldd "$shell" 2>/dev/null | awk '/not found/{print $1}')
    printf '%s\n' "${missing[@]}"
}

missing_libs="$(needed_libs "$browser_bin")"
if [ -n "$missing_libs" ]; then
    log "missing shared libraries: $(echo "$missing_libs" | tr '\n' ' ')"
    command -v apt-get >/dev/null 2>&1 \
        || die "cannot install missing libraries: no apt-get, and the browser needs $missing_libs"
    if [ "$(id -u)" = 0 ]; then SUDO=""; else SUDO="sudo"; fi
    $SUDO apt-get update -qq \
        || die "apt-get update failed; cannot install: $missing_libs"
    $SUDO apt-get install -y -qq --no-install-recommends \
        libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
        libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
        libgbm1 libasound2 libpango-1.0-0 libcairo2 libglib2.0-0 \
        || die "apt-get install failed; cannot supply: $missing_libs"
    still="$(needed_libs "$browser_bin")"
    [ -z "$still" ] || die "libraries still missing after install: $(echo "$still" | tr '\n' ' ')"
    log "system libraries installed"
else
    log "all browser shared libraries present"
fi

# ---- 4. record what we actually installed ---------------------------------
{
    echo "playwright_python: $(installed_version)"
    echo "python: $(python3 --version 2>&1)"
    echo "browsers_path: $BROWSERS"
    echo "chromium_headless_shell_rev: $CHROMIUM_REV"
    echo "chromium_headless_shell_version: $("$browser_bin" --version 2>/dev/null || echo 'unknown')"
    echo "chromium_binary_sha256: $(sha256sum "$browser_bin" | cut -d' ' -f1)"
    echo "uname: $(uname -srm)"
} > "$VERSIONS"

log "versions:"
sed 's/^/  /' "$VERSIONS"
log "done"
