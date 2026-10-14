#!/usr/bin/env bash
# judge/setup.sh — pinned toolchain for the anatomy-machines judge.
#
# Installs into $HOME:
#   * ~/.anatomy-judge/venv           — Python venv, pip --require-hashes
#                                       against judge/requirements.txt
#   * ~/.cache/ms-playwright/…        — Chrome Headless Shell 148.0.7778.96
#                                       (Playwright "chromium-headless-shell"
#                                       rev 1223), downloaded by this script
#                                       and sha256-checked against
#                                       judge/browser-sha256.txt
#   * apt system libraries            — Debian bookworm packages for the
#                                       shell, via `playwright install-deps`
#                                       (apt verifies package signatures;
#                                       the package list is fixed by the
#                                       pinned Playwright version)
#
# Idempotent: a second run verifies the pins and exits without
# downloading.  Exit codes: 0 ok, 1 install/verification failure,
# 2 no network / apt lists not fetched.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
JUDGE_HOME="$HOME/.anatomy-judge"
VENV="$JUDGE_HOME/venv"
SHA_FILE="$SCRIPT_DIR/browser-sha256.txt"
INSTALL_MARK="$JUDGE_HOME/installed"

# Playwright 1.60.0 -> chromium-headless-shell rev 1223 (browsers.json).
SHELL_REV="1223"
SHELL_VER="148.0.7778.96"
SHELL_DIR_NAME="chromium_headless_shell-${SHELL_REV}"
SHELL_ZIP="chrome-headless-shell-linux64.zip"
# URL printed by `playwright install chromium --dry-run` (verified 2026-10-14).
SHELL_URL="https://cdn.playwright.dev/builds/cft/${SHELL_VER}/linux64/${SHELL_ZIP}"

export PLAYWRIGHT_BROWSERS_PATH="$HOME/.cache/ms-playwright"
SHELL_DIR="$PLAYWRIGHT_BROWSERS_PATH/$SHELL_DIR_NAME"

log() { echo "[setup] $*"; }

SUDO=""
if [[ "$(id -u)" -ne 0 ]]; then SUDO=sudo; fi

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

# --------------------------------------------------------------------------
# 0. Already installed?  Verify each pinned piece cheaply; a half-finished
#    run must not count as installed.
# --------------------------------------------------------------------------
if [[ $FORCE -eq 0 && -f "$INSTALL_MARK" \
      && -x "$VENV/bin/python" \
      && -f "$SHELL_DIR/INSTALLATION_COMPLETE" \
      && -x "$SHELL_DIR/chrome-headless-shell-linux64/chrome-headless-shell" ]]; then
    pw_ver="$("$VENV/bin/pip" show playwright 2>/dev/null | awk '/^Version:/{print $2}')"
    if [[ "$pw_ver" == "1.60.0" ]]; then
        log "toolchain already installed and pinned (playwright 1.60.0, headless shell ${SHELL_VER} r${SHELL_REV})"
        exit 0
    fi
fi
log "installing pinned judge toolchain into $JUDGE_HOME"

# --------------------------------------------------------------------------
# 1. apt lists — fail loudly if `apt-get update` did not actually fetch
#    them (empty lists are a known failure mode of fresh images).
# --------------------------------------------------------------------------
log "Fetching apt package lists..."
if ! $SUDO apt-get update -qq; then
    log "ERROR: apt-get update failed"
    exit 2
fi
# (capture, not `| grep -q` — under pipefail grep -q's early exit can
# SIGPIPE the producer and look like a failure)
policy="$(apt-cache policy unzip 2>/dev/null)"
if [[ "$policy" != *"Candidate: "* || "$policy" == *"Candidate: (none)"* ]]; then
    log "ERROR: apt lists are empty or unusable (no candidate for unzip)"
    exit 2
fi

# --------------------------------------------------------------------------
# 2. System packages.  python3-venv+unzip+curl for this script; the
#    browser's shared libraries via the pinned playwright's own dep list.
# --------------------------------------------------------------------------
log "Installing base packages (python3-venv, unzip, curl, ca-certificates)..."
$SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    python3-venv python3-pip unzip curl ca-certificates >/dev/null

mkdir -p "$JUDGE_HOME"
if [[ ! -x "$VENV/bin/python" ]]; then
    log "Creating venv at $VENV"
    python3 -m venv "$VENV"
fi

log "Installing pinned python packages (pip --require-hashes)..."
"$VENV/bin/pip" install --quiet --require-hashes -r "$SCRIPT_DIR/requirements.txt"

# Browser shared libraries — the dep list baked into playwright 1.60.0.
log "Installing headless-shell system libraries (playwright install-deps)..."
$SUDO "$VENV/bin/playwright" install-deps chromium >/dev/null

# --------------------------------------------------------------------------
# 3. Chrome Headless Shell: download, sha256-check, extract into the
#    playwright browsers path with its INSTALLATION_COMPLETE marker so
#    playwright treats it as installed and never re-downloads it.
# --------------------------------------------------------------------------
want="$(awk -v f="$SHELL_ZIP" '$2 == f {print $1}' "$SHA_FILE")"
[[ -n "$want" ]] || { log "ERROR: $SHELL_ZIP not in $SHA_FILE"; exit 1; }

if [[ -f "$SHELL_DIR/INSTALLATION_COMPLETE" \
      && -x "$SHELL_DIR/chrome-headless-shell-linux64/chrome-headless-shell" ]]; then
    log "headless shell ${SHELL_VER} (r${SHELL_REV}) already present"
else
    DL="$(mktemp -d "${TMPDIR:-/tmp}/anat-dl.XXXXXX")"
    trap 'rm -rf "$DL"' EXIT
    log "Downloading $SHELL_URL"
    curl -sfL -o "$DL/$SHELL_ZIP" "$SHELL_URL" || {
        log "ERROR: could not download the headless shell"; exit 2; }

    got="$(sha256sum "$DL/$SHELL_ZIP" | cut -d' ' -f1)"
    if [[ "$got" != "$want" ]]; then
        log "ERROR: sha256 mismatch for $SHELL_ZIP"
        log "       expected $want"
        log "       got      $got"
        exit 1
    fi
    log "sha256 OK: $SHELL_ZIP"

    rm -rf "$SHELL_DIR"
    mkdir -p "$SHELL_DIR"
    unzip -q "$DL/$SHELL_ZIP" -d "$SHELL_DIR"
    chmod +x "$SHELL_DIR/chrome-headless-shell-linux64/chrome-headless-shell"
    touch "$SHELL_DIR/INSTALLATION_COMPLETE"
    rm -rf "$DL"; trap - EXIT
fi

# --------------------------------------------------------------------------
# 4. Smoke test: launch the shell headless and create a real WebGL context
#    under SwiftShader — this is the whole toolchain, exercised.
# --------------------------------------------------------------------------
log "Smoke test: headless launch + WebGL context under SwiftShader..."
"$VENV/bin/python" - <<'PY'
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = pw.chromium.launch(args=["--enable-unsafe-swiftshader", "--disable-gpu"])
    page = b.new_page()
    ok = page.evaluate(
        "() => !!document.createElement('canvas').getContext('webgl')")
    print(f"[setup]   chromium {b.version}, webgl={ok}")
    b.close()
    if not ok:
        raise SystemExit("[setup] ERROR: no WebGL context under SwiftShader")
PY

# --------------------------------------------------------------------------
# 5. Record what is actually installed.
# --------------------------------------------------------------------------
{
    echo "# judge toolchain as installed by judge/setup.sh"
    echo "date: $(date -Iseconds)"
    echo "os: $(. /etc/os-release && echo "$PRETTY_NAME")"
    echo "kernel: $(uname -r)"
    echo "python: $(python3 --version 2>&1)"
    echo "pip-venv: $("$VENV/bin/python" --version 2>&1)"
    "$VENV/bin/pip" list --format=freeze | sed 's/^/pip: /'
    echo "browser: chrome-headless-shell ${SHELL_VER} (playwright chromium-headless-shell r${SHELL_REV})"
    echo "browser-zip-sha256: $want"
    echo "playwright-browsers-path: $PLAYWRIGHT_BROWSERS_PATH"
    echo "fps-floor: gate 5 requires >= 10 FPS under SwiftShader on 2 vCPU"
} > "$SCRIPT_DIR/VERSIONS.txt"

cat > "$INSTALL_MARK" <<EOF
playwright=1.60.0
chromium_headless_shell=${SHELL_VER}-r${SHELL_REV}
installed_at=$(date -Iseconds)
EOF

log "done — versions recorded in judge/VERSIONS.txt"
