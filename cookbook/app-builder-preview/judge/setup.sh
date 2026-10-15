#!/bin/sh
# Install the pinned judge toolchain for app-builder-preview.
#
# One closure, into $HOME/.tools/app-builder-preview:
#   - Node.js 22.23.3 (official tarball, sha256-checked)
#   - Chromium for Playwright 1.63.0 (pinned CDN builds, sha256-checked,
#     unpacked into the browsers dir Playwright expects)
#   - a warm npm cache holding the app's pinned dependencies
#
# The Playwright Python binding itself (1.63.0) ships with the sandbox
# image; this script only verifies its exact version and never upgrades
# it. Chromium goes into $TOOLS/pw-browsers (writable): the image's
# PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright is read-only and must not
# be inherited by the install or the judge.
#
# Idempotent: every step checks for the pinned result before doing work.

set -eu

TOOLS="$HOME/.tools/app-builder-preview"
HERE=$(cd "$(dirname "$0")" && pwd)
APP="$HERE/../examples/good/app"

NODE_VERSION="22.23.3"
NODE_SHA256="df450af89261115ef9f9e3830c3eeb2cc9213b63c720b1af623cb5dcbe2e02de"
NODE_TARBALL="node-v${NODE_VERSION}-linux-x64.tar.xz"
NODE_URL="https://nodejs.org/dist/v${NODE_VERSION}/${NODE_TARBALL}"

PLAYWRIGHT_VERSION="1.63.0"
CHROME_BUILD="153.0.8010.12"
CHROME_SHA256="8aac35011c18f6e2d10696154af89a5728ac2ddd6dc6fad24ffdf243c3fcfd5a"
SHELL_SHA256="a9da028861a0cf789ff25c2fed45f5f1aaf969ed9247835b6a7821a4f7af9d1d"
CHROME_URL="https://cdn.playwright.dev/builds/cft/${CHROME_BUILD}/linux64/chrome-linux64.zip"
SHELL_URL="https://cdn.playwright.dev/builds/cft/${CHROME_BUILD}/linux64/chrome-headless-shell-linux64.zip"
CHROME_REV="1243"

BROWSERS="$TOOLS/pw-browsers"

case "$(uname -s):$(uname -m)" in
    Linux:x86_64) ;;
    *) echo "setup.sh: unsupported platform $(uname -s) $(uname -m) \
(supported: x86-64 Linux)" >&2; exit 2 ;;
esac

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

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
    curl -fsSL "$NODE_URL" -o "$tmp/$NODE_TARBALL"
    echo "$NODE_SHA256  $tmp/$NODE_TARBALL" | sha256sum -c -
    tar -xJf "$tmp/$NODE_TARBALL" -C "$TOOLS/node" --strip-components=1
fi

export PATH="$TOOLS/node/bin:$PATH"

# --- Playwright binding (version-checked, never upgraded) ------------------

got_pw=$(python3 -m playwright --version 2>/dev/null | awk '{print $NF}')
if [ "$got_pw" != "$PLAYWRIGHT_VERSION" ]; then
    echo "setup.sh: playwright ${PLAYWRIGHT_VERSION} (python binding) required, \
found '${got_pw:-none}' in the sandbox image" >&2
    exit 1
fi
echo "setup.sh: playwright ${PLAYWRIGHT_VERSION} (python binding) present"

# --- Chromium (pinned CDN builds, sha256-checked) --------------------------

# The image default PLAYWRIGHT_BROWSERS_PATH points at a read-only dir;
# everything we install and later use lives under $BROWSERS.
export PLAYWRIGHT_BROWSERS_PATH="$BROWSERS"

install_zip() {
    # install_zip <url> <sha256> <dest-dir> <top-dir-in-zip>
    url=$1; want=$2; dest=$3; top=$4
    curl -fsSL "$url" -o "$tmp/dl.zip"
    echo "$want  $tmp/dl.zip" | sha256sum -c -
    rm -rf "$dest"
    mkdir -p "$dest"
    python3 - "$tmp/dl.zip" "$dest" "$top" <<'EOF'
import os, stat, sys, zipfile
zip_path, dest, top = sys.argv[1], sys.argv[2], sys.argv[3]
with zipfile.ZipFile(zip_path) as zf:
    for name in zf.namelist():
        if not name.startswith(top + "/"):
            raise SystemExit(f"setup.sh: unexpected zip layout: {name}")
    zf.extractall(dest)
for root, dirs, files in os.walk(os.path.join(dest, top)):
    for f in files:
        p = os.path.join(root, f)
        if f in ("chrome", "chrome-headless-shell", "chrome_crashpad_handler",
                 "chrome_sandbox") or f.endswith(".so"):
            os.chmod(p, os.stat(p).st_mode | stat.S_IRWXU)
EOF
    touch "$dest/INSTALLATION_COMPLETE" "$dest/DEPENDENCIES_VALIDATED"
}

need_chrome=0
[ -f "$BROWSERS/chromium-${CHROME_REV}/INSTALLATION_COMPLETE" ] || need_chrome=1
need_shell=0
[ -f "$BROWSERS/chromium_headless_shell-${CHROME_REV}/INSTALLATION_COMPLETE" ] || need_shell=1

if [ "$need_chrome" -eq 1 ]; then
    echo "setup.sh: installing chromium ${CHROME_BUILD} (rev ${CHROME_REV})"
    install_zip "$CHROME_URL" "$CHROME_SHA256" \
        "$BROWSERS/chromium-${CHROME_REV}" chrome-linux64
else
    echo "setup.sh: chromium rev ${CHROME_REV} already installed"
fi
if [ "$need_shell" -eq 1 ]; then
    echo "setup.sh: installing chromium headless shell ${CHROME_BUILD}"
    install_zip "$SHELL_URL" "$SHELL_SHA256" \
        "$BROWSERS/chromium_headless_shell-${CHROME_REV}" chrome-headless-shell-linux64
else
    echo "setup.sh: chromium headless shell rev ${CHROME_REV} already installed"
fi

# --- launch probe: the browsers must actually start ------------------------

if ! python3 - <<'EOF'
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    pg = b.new_page()
    pg.set_content("<h1>probe</h1>")
    assert pg.inner_text("h1") == "probe"
    b.close()
EOF
then
    echo "setup.sh: chromium launch probe failed (missing system libraries? \
see the traceback above)" >&2
    exit 1
fi
echo "setup.sh: chromium launch probe ok"

# --- warm npm cache with the app's pinned dependencies ---------------------

if [ ! -d "$TOOLS/npm-cache/_cacache" ]; then
    echo "setup.sh: warming npm cache from app/package-lock.json"
    mkdir -p "$TOOLS/npm-cache" "$tmp/warm"
    cp "$APP/package.json" "$APP/package-lock.json" "$tmp/warm/"
    (cd "$tmp/warm" && npm ci --cache "$TOOLS/npm-cache" \
        --no-audit --no-fund --silent)
else
    echo "setup.sh: npm cache already warm"
fi

# --- Record what was actually installed, for RECEIPT.md --------------------

{
    echo "## installed by judge/setup.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo
    echo '```'
    echo "node $("$TOOLS/node/bin/node" --version)"
    echo "npm  $("$(dirname "$("$TOOLS/node/bin/node" --print process.execPath)")/npm" --version)"
    echo "playwright (python binding) $(python3 -m playwright --version | awk '{print $NF}')"
    echo "chromium ${CHROME_BUILD} rev ${CHROME_REV} (sha256-checked CDN zips)"
    node -e "const l=require('$APP/package-lock.json').packages; \
for (const p of ['node_modules/react','node_modules/react-dom','node_modules/vite','node_modules/@vitejs/plugin-react']) \
console.log(p.replace('node_modules/','')+' '+(l[p]&&l[p].version))"
    echo '```'
} > "$HERE/VERSIONS.txt"

echo "setup.sh: ok"
