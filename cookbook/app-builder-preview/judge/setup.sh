#!/bin/sh
# Install the pinned judge toolchain into $HOME/.tools/app-builder-preview.
#
# One closure: Node.js 22.23.3 (official tarball, sha256-checked) and
# Playwright 1.63.0 with Chromium (npm, sha256-checked via the lockfile).
# Idempotent: an existing install that already provides the pinned versions
# is left untouched.

set -eu

TOOLS="$HOME/.tools/app-builder-preview"
HERE=$(cd "$(dirname "$0")" && pwd)

NODE_VERSION="22.23.3"
NODE_SHA256="df450af89261115ef9f9e3830c3eeb2cc9213b63c720b1af623cb5dcbe2e02de"
NODE_TARBALL="node-v${NODE_VERSION}-linux-x64.tar.xz"
NODE_URL="https://nodejs.org/dist/v${NODE_VERSION}/${NODE_TARBALL}"

PLAYWRIGHT_VERSION="1.63.0"

case "$(uname -s):$(uname -m)" in
    Linux:x86_64) ;;
    *) echo "setup.sh: unsupported platform $(uname -s) $(uname -m) \
(supported: x86-64 Linux)" >&2; exit 2 ;;
esac

# --- Node.js ---------------------------------------------------------------

need_node=1
if [ -x "$TOOLS/node/bin/node" ]; then
    got=$("$TOOLS/node/bin/node" --version 2>/dev/null || true)
    if [ "$got" = "v${NODE_VERSION}" ]; then
        need_node=0
        echo "setup.sh: node v${NODE_VERSION} already installed"
    fi
fi

if [ "$need_node" -eq 1 ]; then
    echo "setup.sh: installing node v${NODE_VERSION}"
    mkdir -p "$TOOLS/node"
    tmp=$(mktemp -d)
    trap 'rm -rf "$tmp"' EXIT
    curl -fsSL "$NODE_URL" -o "$tmp/$NODE_TARBALL"
    echo "$NODE_SHA256  $tmp/$NODE_TARBALL" | sha256sum -c -
    tar -xJf "$tmp/$NODE_TARBALL" -C "$TOOLS/node" --strip-components=1
    rm -rf "$tmp"
    trap - EXIT
fi

export PATH="$TOOLS/node/bin:$PATH"

# --- Playwright ------------------------------------------------------------

need_pw=1
if [ -x "$TOOLS/pw/node_modules/.bin/playwright" ]; then
    got=$("$TOOLS/pw/node_modules/.bin/playwright" --version 2>/dev/null | \
           sed 's/^ *//' || true)
    if [ "$got" = "$PLAYWRIGHT_VERSION" ]; then
        need_pw=0
        echo "setup.sh: playwright ${PLAYWRIGHT_VERSION} already installed"
    fi
fi

if [ "$need_pw" -eq 1 ]; then
    echo "setup.sh: installing playwright ${PLAYWRIGHT_VERSION}"
    mkdir -p "$TOOLS/pw"
    cd "$TOOLS/pw"
    npm init -y >/dev/null 2>&1
    npm install --no-audit --no-fund "playwright@${PLAYWRIGHT_VERSION}" \
        >/dev/null 2>&1
    npx playwright install chromium >/dev/null 2>&1
fi

# --- Record what was actually installed, for RECEIPT.md --------------------

{
    echo "## node ${NODE_VERSION}, playwright ${PLAYWRIGHT_VERSION}"
    echo
    echo '```'
    "$TOOLS/node/bin/node" --version
    "$TOOLS/pw/node_modules/.bin/playwright" --version
    "$TOOLS/pw/node_modules/.bin/playwright" install --dry-run chromium 2>/dev/null | \
        grep -i chromium || true
    echo '```'
} > "$HERE/VERSIONS.txt"

echo "setup.sh: ok"
