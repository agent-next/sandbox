#!/bin/bash
# judge/setup.sh — install the pinned tools for the ci-test-matrix demo.
#
# Idempotent.  Every download is sha256-checked against the digest below,
# which was computed from the file actually downloaded from the release URL,
# so a re-uploaded or substituted release fails loudly here instead of
# silently changing the tool under the judge.
#
# Installs into $HOME/tools/bin:
#   uv 0.12.16   (GitHub release tarball, sha256-pinned)
#
# The five CPython interpreters (3.9, 3.10, 3.11, 3.12, 3.13; uv fetches
# the latest patch it knows for each) and the pinned pytest wheel set are
# fetched by uv itself, per matrix cell, from judge/requirements.txt
# (hash-pinned).
#
# Usage: bash judge/setup.sh [--force]
# Exit codes: 0 ok, 1 download/verification failure, 2 no network or sources.
set -euo pipefail

INSTALL_DIR="$HOME/tools/bin"
mkdir -p "$INSTALL_DIR"

UV_VERSION="0.12.16"
UV_TARBALL="uv-x86_64-unknown-linux-gnu.tar.gz"
UV_URL="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/${UV_TARBALL}"
# sha256 of the file at $UV_URL, computed here and recorded below:
UV_SHA256="8e5c6e5523dffc2dcf615bd995554c84c9feb4e577808a3fb8698a639d3f8d9c"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSIONS_FILE="$SCRIPT_DIR/VERSIONS.txt"
FORCE=0
[ "${1:-}" = "--force" ] && FORCE=1

log() { echo "[setup] $*"; }

uv_version() {   # prints "0.12.16" from `uv --version`
    "$INSTALL_DIR/uv" --version 2>/dev/null | awk '{print $2}'
}

uv_pinned_version_present() {   # 0 = the pinned uv is installed
    [ -x "$INSTALL_DIR/uv" ] || return 1
    [ "$(uv_version)" = "$UV_VERSION" ]
}

fetch() {  # fetch <url> <sha256> <dest>
    local url="$1" want="$2" dest="$3"
    if [ -f "$dest" ] && echo "$want  $dest" | sha256sum -c --status -; then
        echo "== cached $dest (sha256 ok) =="
    else
        echo "== downloading $url =="
        if ! curl -fsSL -o "$dest" "$url"; then
            echo "download failed: $url" >&2
            return 1
        fi
    fi
    # verify what is on disk right now, whether cached or just fetched
    echo "$want  $dest" | sha256sum -c -
}

if [ "$FORCE" = 1 ] || ! uv_pinned_version_present; then
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT
    fetch "$UV_URL" "$UV_SHA256" "$tmp/$UV_TARBALL" || exit 2
    tar -xzf "$tmp/$UV_TARBALL" -C "$tmp"
    install -m 0755 "$tmp/uv-x86_64-unknown-linux-gnu/uv" "$INSTALL_DIR/uv"
    rm -rf "$tmp"
    trap - EXIT
fi

# Fail loudly rather than leave a half-matching state behind.
if ! uv_pinned_version_present; then
    echo "uv $UV_VERSION not correctly installed at $INSTALL_DIR/uv" >&2
    exit 1
fi
log "uv: $("$INSTALL_DIR/uv" --version)"

# --- record what is installed, from the tools' own --version output -----
{
    echo "# What judge/setup.sh actually installed — recorded by the tools'"
    echo "# own --version output, not by hand."
    echo "#"
    echo "# Reproduce:"
    echo "#   bash judge/setup.sh && bash judge/versions.sh > judge/VERSIONS.txt"
    echo ""
    echo "### uv (GitHub release tarball, sha256-pinned)"
    echo ""
    echo "\$ $INSTALL_DIR/uv --version"
    "$INSTALL_DIR/uv" --version
    echo ""
    echo "uv release: ${UV_VERSION}"
    echo "uv tarball: ${UV_URL}"
    echo "uv sha256 : ${UV_SHA256}"
    echo ""
    echo "### interpreters and pytest (uv-managed, pinned by hash)"
    echo ""
    echo "Interpreter major.minor pins (SPEC.md): 3.9 3.10 3.11 3.12 3.13"
    echo "Wheel pins: judge/requirements.txt (--require-hashes)"
} > "$VERSIONS_FILE"

log "setup complete -> $INSTALL_DIR/uv"
