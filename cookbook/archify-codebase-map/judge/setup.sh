#!/usr/bin/env bash
# judge/setup.sh — pinned toolchain for the archify-codebase-map demo.
#
# Installs, idempotently, into $HOME:
#   * Node.js and Chromium from pinned Debian bookworm packages
#   * the archify skill v3.0.1 (pinned commit, sha256-checked tarball)
#     into $HOME/archify-skill/ (pure Node, no npm install needed)
#   * the target repo httpx 0.28.1 (pinned commit, sha256-checked tarball)
#     into $HOME/ground-truth/httpx-0.28.1/ (used by the judge to derive
#     the module dependency graph with Python's ast module)
#
# Usage:  bash judge/setup.sh        # install (skip if already done)
#         bash judge/setup.sh --force
# Exit:   0 ok, 1 verification failure, 2 network/source failure

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Pinned inputs ----------------------------------------------------------
# Debian bookworm packages (released long before this demo; apt metadata
# carries the signature chain — verified by apt itself on install).
NODE_VERSION="18.20.4+dfsg-1~deb12u3"
CHROMIUM_VERSION="155.0.8059.39-1~deb12u1"
CHROMIUM_COMMON="155.0.8059.39-1~deb12u1"

# archify v3.0.1 (MIT; see ../../third_party/archify-LICENSE.txt)
# release tag v3.0.1, commit 2ab3cae..., published 2026-09-28.
ARCHIFY_SHA256="e14ccec6d5765e842aa77907431aa068410f2e44fe373e13eae786d7697b0888"
ARCHIFY_URL="https://github.com/tt-a1i/archify/archive/2ab3cae7ac2c2a55d7386ca789d03c4fcd31816c.tar.gz"
ARCHIFY_DIR="$HOME/archify-skill"

# target repo: httpx 0.28.1 (BSD-3-Clause; encode/httpx), commit 26d48e0...
HTTPX_SHA256="41ce356ff41e37539b2abbb6b6b13b3f5c41d2c09422112e72074d2e96816e10"
HTTPX_URL="https://github.com/encode/httpx/archive/26d48e0634e6ee9cdc0533996db289ce4b430177.tar.gz"
TRUTH_DIR="$HOME/ground-truth/httpx-0.28.1"

VERSION_FILE="$HOME/.archify_demo_versions"
INSTALL_MARK="$HOME/.archify_demo_installed"

log() { echo "[setup] $*"; }

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

SUDO=""
if [[ "$(id -u)" -ne 0 ]]; then SUDO=sudo; fi

if [[ $FORCE -eq 0 && -f "$INSTALL_MARK" ]] \
   && command -v node >/dev/null 2>&1 \
   && command -v chromium >/dev/null 2>&1 \
   && [[ -f "$ARCHIFY_DIR/archify/bin/archify.mjs" ]] \
   && [[ -d "$TRUTH_DIR/httpx" ]]; then
    log "toolchain already installed (mark: $INSTALL_MARK)"
    log "re-run with --force to reinstall"
    exit 0
fi

# ---------------------------------------------------------------------------
# 1. apt package lists — fail loudly if they did not actually come down.
# ---------------------------------------------------------------------------
log "Fetching apt package lists..."
if ! apt_out=$($SUDO apt-get update -qq 2>&1); then
    echo "$apt_out" | tail -5
    log "ERROR: apt-get update failed"
    exit 2
fi
if [[ "$(apt-cache policy nodejs)" != *"$NODE_VERSION"* ]]; then
    log "ERROR: nodejs $NODE_VERSION not in apt lists (stale or missing lists)"
    exit 2
fi
if [[ "$(apt-cache policy chromium)" != *"$CHROMIUM_VERSION"* ]]; then
    log "ERROR: chromium $CHROMIUM_VERSION not in apt lists"
    exit 2
fi

log "Installing pinned Debian packages (nodejs $NODE_VERSION, chromium $CHROMIUM_VERSION)..."
$SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y \
    "nodejs=$NODE_VERSION" \
    "chromium=$CHROMIUM_VERSION" >/dev/null

node_v="$(node --version)"
chr_v="$(chromium --version)"
[[ "$node_v" == "v18.20.4" ]] || { log "ERROR: node reports $node_v"; exit 1; }
[[ "$chr_v" == "Chromium 155."* ]] || { log "ERROR: chromium reports $chr_v"; exit 1; }

# ---------------------------------------------------------------------------
# 2. sha256-checked tarballs; never trust the download.
# ---------------------------------------------------------------------------
DL="$(mktemp -d /tmp/archify-dl.XXXXXX)"
trap 'rm -rf "$DL"' EXIT
cd "$DL"

log "Downloading archify v3.0.1 tarball..."
curl -fsSL --retry 3 --max-time 120 -o archify.tar.gz "$ARCHIFY_URL"
got=$(sha256sum archify.tar.gz | cut -d' ' -f1)
[[ "$got" == "$ARCHIFY_SHA256" ]] || {
    log "ERROR: archify sha256 mismatch (want $ARCHIFY_SHA256, got $got)"; exit 1; }

log "Downloading httpx 0.28.1 tarball..."
curl -fsSL --retry 3 --max-time 120 -o httpx.tar.gz "$HTTPX_URL"
got=$(sha256sum httpx.tar.gz | cut -d' ' -f1)
[[ "$got" == "$HTTPX_SHA256" ]] || {
    log "ERROR: httpx sha256 mismatch (want $HTTPX_SHA256, got $got)"; exit 1; }

# ---------------------------------------------------------------------------
# 3. Unpack to fixed homes (replace any partial previous install).
# ---------------------------------------------------------------------------
rm -rf "$ARCHIFY_DIR"
mkdir -p "$ARCHIFY_DIR"
tar xzf archify.tar.gz -C "$ARCHIFY_DIR" --strip-components=1
# The directory we actually call is $ARCHIFY_DIR/archify (the skill root);
# keep only what the render path needs? No — keep the whole tree so the demo
# mirrors what a user gets when they install the skill.

mkdir -p "$(dirname "$TRUTH_DIR")"
rm -rf "$TRUTH_DIR"
mkdir -p "$TRUTH_DIR"
tar xzf httpx.tar.gz -C "$TRUTH_DIR" --strip-components=1

# ---------------------------------------------------------------------------
# 4. Verify the render path end-to-end: validate a known example.
# ---------------------------------------------------------------------------
log "Verifying archify renders..."
node "$ARCHIFY_DIR/archify/bin/archify.mjs" validate architecture \
    "$ARCHIFY_DIR/archify/examples/web-app.architecture.json" >/dev/null

log "Verifying httpx tree has the expected package dir..."
[[ -f "$TRUTH_DIR/httpx/_client.py" ]] || { log "ERROR: httpx tree wrong"; exit 1; }

cat > "$VERSION_FILE" <<EOF
node=$node_v
chromium=$chr_v
archify=v3.0.1 commit 2ab3cae7ac2c2a55d7386ca789d03c4fcd31816c sha256=$ARCHIFY_SHA256
httpx=0.28.1 commit 26d48e0634e6ee9cdc0533996db289ce4b430177 sha256=$HTTPX_SHA256
installed_at=$(date -Iseconds)
EOF
touch "$INSTALL_MARK"

cat > "$SCRIPT_DIR/VERSIONS.txt" <<EOF
node                $node_v            (Debian bookworm nodejs=$NODE_VERSION)
chromium            $chr_v     (Debian bookworm chromium=$CHROMIUM_VERSION)
archify             v3.0.1, commit 2ab3cae7ac2c2a55d7386ca789d03c4fcd31816c, MIT
httpx (target repo) 0.28.1, commit 26d48e0634e6ee9cdc0533996db289ce4b430177, BSD-3-Clause
EOF

log "OK.  node $node_v  |  chromium $chr_v"
log "archify skill : $ARCHIFY_DIR/archify"
log "httpx src     : $TRUTH_DIR"
log "(versions recorded in judge/VERSIONS.txt)"
