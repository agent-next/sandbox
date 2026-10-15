#!/usr/bin/env bash
# judge/setup.sh — install the pinned render+grade toolchain for the
# hyperframes-video demo (Debian bookworm, x86_64):
#
#   * Node.js v22.23.3 (tarball, sha256-pinned)      -> $JH/node
#   * hyperframes 0.8.61 (npm ci, committed lock)    -> $JH/app
#   * Chrome Headless Shell 152.0.7977.30 (sha256)   -> ~/.cache/hyperframes/...
#   * ffmpeg, tesseract-ocr(+eng), libtesseract5, liblept5, fonts-dejavu-core
#     as sha256-checked .debs (judge/package-sha256.txt)
#   * vendored judge/vendor/gsap.min.js (3.14.2, digest re-verified)
#
# Idempotent: every component is checked individually; --force reinstalls.
# Exit codes: 0 ok, 1 install/verification failure, 2 no network/sources.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SHA_FILE="$SCRIPT_DIR/package-sha256.txt"
JH="$HOME/.hyperframes-judge"
NODE_VER="v22.23.3"
CHS_VER="152.0.7977.30"
CHS_HOME="$HOME/.cache/hyperframes/chrome/chrome-headless-shell/$CHS_VER"
ENV_FILE="$JH/env.sh"
MARK="$JH/.installed"

log() { echo "[setup] $*"; }

SUDO=""
if [[ "$(id -u)" -ne 0 ]]; then SUDO=sudo; fi

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

# --- fast path: everything already in place ---------------------------------
debs_ok() {
    while read -r sha fname url; do
        [[ "$sha" == \#* || -z "$sha" ]] && continue
        [[ "$fname" == *.deb ]] || continue
        name="${fname%%_*}"; ver="${fname#*_}"; ver="${ver%_*}"
        [[ "$(dpkg-query -W -f='${Version}' "$name" 2>/dev/null)" == "$ver" ]] \
            || return 1
    done < "$SHA_FILE"
}
if [[ $FORCE -eq 0 && -f "$MARK" \
        && -x "$JH/node/bin/node" \
        && "$("$JH/node/bin/node" --version 2>/dev/null)" == "$NODE_VER" \
        && -x "$JH/app/node_modules/.bin/hyperframes" \
        && -x "$CHS_HOME/chrome-headless-shell-linux64/chrome-headless-shell" \
        && "$(sha256sum "$SCRIPT_DIR/vendor/gsap.min.js" | cut -d' ' -f1)" \
            == "c174bfce53a729418d57a8ad8625e7247c793a22fef8e2851e3cfa3de9cd8280" ]] \
        && debs_ok; then
    log "toolchain already installed and verified (use --force to reinstall)"
    exit 0
fi

mkdir -p "$JH"

# ---------------------------------------------------------------------------
# 1. apt lists — fail early if they did not actually come down.
# ---------------------------------------------------------------------------
log "Fetching apt package lists..."
if ! out=$($SUDO apt-get update -qq 2>&1); then
    echo "$out" | tail -3
    log "ERROR: apt-get update failed"
    exit 2
fi
if [[ "$(apt-cache policy tesseract-ocr | awk '/Candidate:/{print $2}')" == "(none)" \
   || -z "$(apt-cache policy tesseract-ocr | awk '/Candidate:/{print $2}')" ]]; then
    log "ERROR: apt lists fetched but tesseract-ocr has no candidate"
    exit 2
fi

# ---------------------------------------------------------------------------
# 2. Infrastructure deps (download helpers + Chrome runtime libraries).
#    These are host plumbing, not graded outputs; versions float within
#    bookworm. The tools whose bytes reach the verdict are pinned below.
# ---------------------------------------------------------------------------
log "Installing infra packages (curl, unzip, chrome runtime libs)..."
$SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    curl ca-certificates xz-utils unzip fontconfig \
    libasound2 libatk-bridge2.0-0 libatk1.0-0 libatspi2.0-0 libcairo2 \
    libcups2 libdbus-1-3 libdrm2 libexpat1 libgbm1 libglib2.0-0 libnspr4 \
    libnss3 libpango-1.0-0 libx11-6 libxcb1 libxcomposite1 libxdamage1 \
    libxext6 libxfixes3 libxkbcommon0 libxrandr2 libxshmfence1 >/dev/null

# ---------------------------------------------------------------------------
# 3. Download every entry in package-sha256.txt, verify digests.
# ---------------------------------------------------------------------------
log "Downloading pinned artifacts..."
DL="$(mktemp -d "${TMPDIR:-/tmp}/hf-dl.XXXXXX")"
trap 'rm -rf "$DL"' EXIT

while read -r want fname url; do
    [[ "$want" == \#* || -z "$want" ]] && continue
    [[ "$fname" == gsap-* ]] && continue   # vendored, verified below
    if [[ ! -f "$DL/$fname" ]]; then
        curl -fsSL --retry 3 --connect-timeout 15 -o "$DL/$fname" "$url" \
            || { log "ERROR: download failed: $url"; exit 2; }
    fi
    got=$(sha256sum "$DL/$fname" | cut -d' ' -f1)
    if [[ "$got" != "$want" ]]; then
        log "ERROR: sha256 mismatch for $fname"
        log "       expected $want"; log "       got      $got"
        exit 1
    fi
done < "$SHA_FILE"
log "sha256 OK: all downloads match judge/package-sha256.txt"

# ---------------------------------------------------------------------------
# 4. Pinned .debs.
# ---------------------------------------------------------------------------
log "Installing pinned .debs (ffmpeg, tesseract, fonts-dejavu-core)..."
$SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y "$DL"/*.deb >/dev/null

# ---------------------------------------------------------------------------
# 5. Node.js tarball -> $JH/node
# ---------------------------------------------------------------------------
if [[ ! -x "$JH/node/bin/node" \
      || "$("$JH/node/bin/node" --version 2>/dev/null || true)" != "$NODE_VER" ]]; then
    log "Installing Node.js $NODE_VER -> $JH/node"
    rm -rf "$JH/node" "$JH/node-$NODE_VER-linux-x64"
    tar -xJf "$DL/node-$NODE_VER-linux-x64.tar.xz" -C "$JH"
    mv "$JH/node-$NODE_VER-linux-x64" "$JH/node"
fi
"$JH/node/bin/node" --version | grep -qx "$NODE_VER"

# ---------------------------------------------------------------------------
# 6. hyperframes 0.8.61 via the committed lockfile -> $JH/app
# ---------------------------------------------------------------------------
if [[ ! -x "$JH/app/node_modules/.bin/hyperframes" || $FORCE -eq 1 ]]; then
    log "Installing hyperframes 0.8.61 (npm ci, judge/package-lock.json)"
    rm -rf "$JH/app"
    mkdir -p "$JH/app"
    cp "$SCRIPT_DIR/package.json" "$SCRIPT_DIR/package-lock.json" "$JH/app/"
    (cd "$JH/app" && PATH="$JH/node/bin:$PATH" npm ci --ignore-scripts --no-audit --no-fund)
fi
HF_VER="$(cd "$JH/app" && PATH="$JH/node/bin:$PATH" \
          node node_modules/hyperframes/bin/hyperframes.mjs --version 2>/dev/null \
          | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
[[ "$HF_VER" == "0.8.61" ]] || { log "ERROR: hyperframes reports $HF_VER"; exit 1; }

# ---------------------------------------------------------------------------
# 7. Chrome Headless Shell -> ~/.cache/hyperframes/ (the path hyperframes
#    itself searches; version is the one 0.8.61 pins internally).
# ---------------------------------------------------------------------------
CHS_BIN="$CHS_HOME/chrome-headless-shell-linux64/chrome-headless-shell"
if [[ ! -x "$CHS_BIN" || $FORCE -eq 1 ]]; then
    log "Installing Chrome Headless Shell $CHS_VER"
    rm -rf "$CHS_HOME"
    mkdir -p "$CHS_HOME"
    unzip -oq "$DL/chrome-headless-shell-linux64-$CHS_VER.zip" -d "$CHS_HOME"
    chmod +x "$CHS_BIN"
fi
"$CHS_BIN" --version | grep -q "$CHS_VER" \
    || { log "ERROR: chrome-headless-shell --version mismatch"; exit 1; }

# ---------------------------------------------------------------------------
# 8. Vendored GSAP: verify the committed file's digest (grading is offline).
# ---------------------------------------------------------------------------
got=$(sha256sum "$SCRIPT_DIR/vendor/gsap.min.js" | cut -d' ' -f1)
want=$(awk '$2=="gsap-3.14.2.min.js"{print $1}' "$SHA_FILE")
[[ "$got" == "$want" ]] || {
    log "ERROR: judge/vendor/gsap.min.js sha256 $got != pinned $want"; exit 1; }

# ---------------------------------------------------------------------------
# 9. env file + versions record.
# ---------------------------------------------------------------------------
cat > "$ENV_FILE" <<EOF
# written by judge/setup.sh — sourced by grade.sh / selftest.sh
export HF_JUDGE_HOME="$JH"
export PATH="$JH/node/bin:$JH/app/node_modules/.bin:\$PATH"
export HYPERFRAMES_BIN="$JH/app/node_modules/hyperframes/bin/hyperframes.mjs"
export HF_NODE="$JH/node/bin/node"
EOF

bash "$SCRIPT_DIR/versions.sh" > "$SCRIPT_DIR/VERSIONS.txt"
touch "$MARK"
log "toolchain installed: node $NODE_VER, hyperframes $HF_VER, chrome-headless-shell $CHS_VER"
log "(versions recorded in judge/VERSIONS.txt; run \`bash judge/versions.sh --check\`)"
