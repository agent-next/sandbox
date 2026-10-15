#!/usr/bin/env bash
# judge/setup.sh — pin git 1:2.39.5-0+deb12u3 (Debian bookworm) with
# sha256-checked .deb downloads, idempotently.  Python (>= 3.10, stdlib only)
# is required by the judge math and checked but not installed here.
#
# The demo only needs `git` and `python3`; the sha256 table in
# judge/package-sha256.txt pins the exact .debs so a later Debian point
# release that rebuilds the package fails loudly here instead of silently
# changing the tool under the judge.
#
# Usage:
#   bash judge/setup.sh            # install if the pin does not match
#   bash judge/setup.sh --force    # reinstall even if it appears to match
#
# Exit codes: 0 ok, 1 install/verification failure, 2 no network/sources.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION_FILE="$HOME/.bisect_git_version"
SHA_FILE="$SCRIPT_DIR/package-sha256.txt"

GIT_DEB_VERSION="1:2.39.5-0+deb12u3"

log() { echo "[setup] $*"; }

record_versions() {
    bash "$SCRIPT_DIR/versions.sh" > "$SCRIPT_DIR/VERSIONS.txt"
}

SUDO=""
if [[ "$(id -u)" -ne 0 ]]; then SUDO=sudo; fi

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

installed_git() {
    dpkg-query -W -f='${Version}' git 2>/dev/null || true
}

need_install() {
    [[ $FORCE -eq 1 ]] && return 0
    [[ "$(installed_git)" == "$GIT_DEB_VERSION" ]] && return 1
    return 0
}

# --- Python (required, checked, not installed) -----------------------------
if ! command -v python3 >/dev/null 2>&1; then
    log "ERROR: python3 not found (>= 3.10 required for the judge math)"
    exit 1
fi
PYV="$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')"
if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    log "ERROR: python3 is $PYV, need >= 3.10"
    exit 1
fi
log "python3 $PYV (stdlib only, no packages to install)"

if ! need_install; then
    log "git $GIT_DEB_VERSION already installed"
    git --version
    record_versions
    exit 0
fi

# --- 1. Package lists (fail early if they did not come down) ----------------
log "Fetching apt package lists..."
if ! apt_update_out=$($SUDO apt-get update -qq 2>&1); then
    echo "$apt_update_out" | tail -3
    log "ERROR: apt-get update failed"
    exit 2
fi

if [[ "$(apt-cache policy git)" != *"$GIT_DEB_VERSION"* ]]; then
    log "ERROR: git $GIT_DEB_VERSION not in apt lists"
    log "       (package lists are missing, stale, or the version moved;"
    log "        judge/package-sha256.txt pins the digests this demo needs)"
    exit 2
fi

# --- 2. Download the pinned .debs and sha256-verify them --------------------
log "Downloading pinned git $GIT_DEB_VERSION..."
DL="$(mktemp -d "${TMPDIR:-/tmp}/bisect-git-dl.XXXXXX")"
trap 'rm -rf "$DL"' EXIT
cd "$DL"

if ! apt-get download git="$GIT_DEB_VERSION" git-man="$GIT_DEB_VERSION" >/dev/null 2>&1; then
    log "ERROR: could not download the pinned set"
    log "       (a Debian point release may have superseded a pinned version)"
    exit 1
fi

if [[ ! -f "$SHA_FILE" ]]; then
    log "ERROR: missing $SHA_FILE"
    exit 1
fi
while read -r want fname; do
    [[ "$want" == \#* || -z "$want" ]] && continue
    if [[ ! -f "$fname" ]]; then
        log "ERROR: $fname not downloaded"
        exit 1
    fi
    got=$(sha256sum "$fname" | cut -d' ' -f1)
    if [[ "$got" != "$want" ]]; then
        log "ERROR: sha256 mismatch for $fname"
        log "       expected $want"
        log "       got      $got"
        exit 1
    fi
done < "$SHA_FILE"
log "sha256 OK: 2 packages match judge/package-sha256.txt"

# --- 3. Install (apt resolves the runtime dependencies) ---------------------
log "Installing..."
$SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y ./*.deb >/dev/null

# --- 4. Verify what is actually on the system -------------------------------
v="$(installed_git)"
[[ "$v" == "$GIT_DEB_VERSION" ]] || {
    log "ERROR: git version $v != $GIT_DEB_VERSION"; exit 1; }
[[ "$(git --version)" == "git version 2.39.5" ]] || {
    log "ERROR: git --version does not report 2.39.5"; exit 1; }

echo "$GIT_DEB_VERSION" > "$VERSION_FILE"
record_versions
log "git $GIT_DEB_VERSION installed and verified (sha256-pinned)"
