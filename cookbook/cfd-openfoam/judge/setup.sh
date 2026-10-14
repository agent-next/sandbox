#!/usr/bin/env bash
# judge/setup.sh — install pinned OpenFOAM v1912 (Debian bookworm packages).
# Idempotent. Every downloaded .deb is sha256-checked against the digest
# table in judge/package-sha256.txt before installation, so a later Debian
# point release that rebuilds any package fails loudly here instead of
# silently changing the solver under the judge.
#
# Usage:
#   bash judge/setup.sh                 # install
#   bash judge/setup.sh --force         # reinstall even if already present
#
# Exit codes: 0 ok, 1 install/verification failure, 2 no network/sources.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSION_FILE="$HOME/.openfoam_version"
INSTALL_MARK="$HOME/.openfoam_installed"
SHA_FILE="$SCRIPT_DIR/package-sha256.txt"

OPENFOAM_VERSION="1912.200626-1+b1"          # openfoam, libopenfoam
EXAMPLES_VERSION="1912.200626-1"             # openfoam-examples (no binNMU)
OF_PREFIX="${OF_PREFIX:-/usr/share/openfoam}"  # where the deb installs to

log() { echo "[setup] $*"; }

SUDO=""
if [[ "$(id -u)" -ne 0 ]]; then SUDO=sudo; fi

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

need_install() {
    [[ $FORCE -eq 1 ]] && return 0
    [[ -f "$VERSION_FILE" && -f "$INSTALL_MARK" ]] &&
        grep -q "^openfoam=$OPENFOAM_VERSION$" "$VERSION_FILE" &&
        grep -q "^openfoam-examples=$EXAMPLES_VERSION$" "$VERSION_FILE" &&
        command -v icoFoam >/dev/null 2>&1
}

if ! need_install; then
    # Verify what is actually on the system still matches the pins: an
    # interrupted run, a manual apt upgrade or a different image can leave a
    # half-matching state behind.
    current() { dpkg-query -W -f='${Version}' "$1" 2>/dev/null || true; }
    if [[ "$(current openfoam)" != "$OPENFOAM_VERSION" ||
          "$(current libopenfoam)" != "$OPENFOAM_VERSION" ||
          "$(current openfoam-examples)" != "$EXAMPLES_VERSION" ||
          ! -x "$(command -v icoFoam 2>/dev/null)" ]]; then
        log "installed OpenFOAM does not match the pins; reinstalling"
    else
        log "OpenFOAM $OPENFOAM_VERSION already installed"
        exit 0
    fi
fi

# --------------------------------------------------------------------------
# 1. Package lists.  Fail early if the lists did not actually come down
#    (empty apt lists are a known failure mode of fresh sandbox images).
# --------------------------------------------------------------------------
log "Fetching apt package lists..."
if ! apt_update_out=$($SUDO apt-get update -qq 2>&1); then
    echo "$apt_update_out" | tail -3
    log "ERROR: apt-get update failed"
    exit 2
fi

if [[ "$(apt-cache policy openfoam)" != *"$OPENFOAM_VERSION"* ]]; then
    log "ERROR: openfoam $OPENFOAM_VERSION not in apt lists"
    log "       (package lists are missing, stale, or the version moved;"
    log "        judge/package-sha256.txt pins the digests this demo needs)"
    exit 2
fi

# The full package-version pair set is read from package-sha256.txt filenames
# so the pin set and the file live in one place.
log "Downloading pinned packages (${OPENFOAM_VERSION} + dependencies)..."
DL="$(mktemp -d "${TMPDIR:-/tmp}/of-dl.XXXXXX")"
trap 'rm -rf "$DL"' EXIT
cd "$DL"

# package=version pairs for apt-get download, from the pinned sha table.
PKGSPECS=()
while read -r sha fname; do
    [[ "$sha" == \#* || -z "$sha" ]] && continue
    # filename:  <name>_<version>_<arch>.deb  (version may contain '+')
    name="${fname%%_*}"
    ver="${fname#*_}"; ver="${ver%_*}"
    PKGSPECS+=("${name}=${ver}")
done < "$SHA_FILE"

if ! apt-get download "${PKGSPECS[@]}" >/dev/null 2>&1; then
    # A binary-NMU successor (e.g. +b2) would keep the name but break the
    # digest; refuse rather than fall back, because the whole point is that
    # the solver under the judge must not change.
    log "ERROR: could not download the pinned set above"
    log "       (a Debian point release may have superseded a pinned version)"
    exit 1
fi

# --------------------------------------------------------------------------
# 2. sha256-verify every downloaded .deb against the pinned table.
# --------------------------------------------------------------------------
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

N=$(ls ./*.deb | wc -l)
log "sha256 OK: $N packages match judge/package-sha256.txt"

# --------------------------------------------------------------------------
# 3. Install (apt resolves the remaining dependencies from the transitive
#    closure already recorded in the file).
# --------------------------------------------------------------------------
log "Installing (${N} packages)..."
$SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y ./*.deb >/dev/null

# --------------------------------------------------------------------------
# 4. Verify what is actually on the system.
# --------------------------------------------------------------------------
for pair in "openfoam:$OPENFOAM_VERSION" \
            "libopenfoam:$OPENFOAM_VERSION" \
            "openfoam-examples:$EXAMPLES_VERSION"; do
    pkg="${pair%%:*}"; want="${pair#*:}"
    v=$(dpkg-query -W -f='${Version}' "$pkg")
    [[ "$v" == "$want" ]] || {
        log "ERROR: $pkg version $v != $want"; exit 1; }
done

for cmd in blockMesh icoFoam checkMesh postProcess; do
    command -v "$cmd" >/dev/null 2>&1 || {
        log "ERROR: $cmd missing"; exit 1; }
    # Also confirm the binary itself reports the pinned build.  (`-version`
    # is not a real option in v1912: the banner is printed, then it exits 1
    # with "Invalid option" — capture into a variable so pipefail cannot see
    # the SIGPIPE from an early-exiting grep.)
    ver_out="$(FOAM_ETC="$OF_PREFIX/etc" WM_PROJECT_DIR="$OF_PREFIX" \
        "$cmd" -version 2>&1 || true)"
    [[ "$ver_out" == *"OpenFOAM- (1912)"* ]] || {
        log "ERROR: $cmd does not report OpenFOAM 1912"; exit 1; }
done

# Record the pinned set, for humans and for `versions.sh --check`.
cat > "$VERSION_FILE" <<EOF
# pinned by judge/package-sha256.txt (sha256 per .deb)
openfoam=$OPENFOAM_VERSION
libopenfoam=$OPENFOAM_VERSION
openfoam-examples=$EXAMPLES_VERSION
installed_at=$(date -Iseconds)
EOF
bash "$SCRIPT_DIR/versions.sh" > "$SCRIPT_DIR/VERSIONS.txt"

log "OpenFOAM $OPENFOAM_VERSION installed and verified"
log "(versions recorded in judge/VERSIONS.txt; run \`bash judge/versions.sh --check\`)"
