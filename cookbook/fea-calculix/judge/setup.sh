#!/bin/bash
# Setup for the fea-calculix demo: pinned CalculiX + gmsh into $HOME/tools.
# Idempotent. Every download is sha256-checked.
set -euo pipefail

INSTALL_DIR="$HOME/tools"
mkdir -p "$INSTALL_DIR/bin"
export PATH="$INSTALL_DIR/bin:$PATH"

# --- pinned downloads (exact files, sha256-checked) ------------------------
# calculix-ccx and its two non-base library dependencies, pinned by URL to
# the Debian bookworm pool (deb.debian.org) and installed from the local
# .deb files so apt can never resolve a different version.
DEB_URL="http://deb.debian.org/debian/pool/main"
CCX_DEB="calculix-ccx_2.20-1_amd64.deb"
CCX_SHA256="a448239f3caf5a324f9589a636e595e3e676153489f75843e509decb6809f346"
SPOOLES_DEB="libspooles2.2_2.2-14_amd64.deb"
SPOOLES_SHA256="51faa6a5aad9aba20beadffba5d4d9e28fa7a5ef426a1d4fa16c825fd80034a0"
ARPACK_DEB="libarpack2_3.8.0-3_amd64.deb"
ARPACK_SHA256="949773b357e8f4c74fbc585f2fbee452adb2931c3d36a5baf8eae49f7d45bede"

GMSH_VERSION="4.10.0"
GMSH_TAR="gmsh-${GMSH_VERSION}-Linux64.tgz"
GMSH_URL="https://gmsh.info/bin/Linux/${GMSH_TAR}"
GMSH_SHA256="6c7d748e941a6823eeb930fd91a3d46236f752afe2629fe43f61deae562eda95"

fetch() {  # fetch <url> <sha256> <dest>
    local url="$1" want="$2" dest="$3"
    if [ -f "$dest" ] && echo "$want  $dest" | sha256sum -c --status -; then
        echo "== cached $dest (sha256 ok) =="
    else
        echo "== downloading $url =="
        curl -fsSL -o "$dest" "$url"
    fi
    echo "$want  $dest" | sha256sum -c -
}

# --- apt prerequisites -----------------------------------------------------
# Only packages whose versions the pinned .debs do not depend on (base libs,
# gmsh's GL/X libs). apt lists in this image may be stale: refresh, but do
# not let apt pick the CalculiX version.
echo "== apt-get update =="
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
    libglu1-mesa libxinerama1 python3 curl ca-certificates

# --- CalculiX (pinned .deb files) ------------------------------------------
ccx_banner() {  # ccx -v prints a banner (scratch dir; ccx litters job files)
    (cd "$(mktemp -d)" && "$INSTALL_DIR/bin/ccx" -v 2>&1 || true) | grep -m1 "Version"
}
if ! ccx_banner | grep -q "2.20"; then
    tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
    fetch "$DEB_URL/c/calculix-ccx/$CCX_DEB"      "$CCX_SHA256"      "$tmp/$CCX_DEB"
    fetch "$DEB_URL/s/spooles/$SPOOLES_DEB"       "$SPOOLES_SHA256"  "$tmp/$SPOOLES_DEB"
    fetch "$DEB_URL/a/arpack/$ARPACK_DEB"         "$ARPACK_SHA256"   "$tmp/$ARPACK_DEB"
    # apt resolves the remaining (base) dependencies from the fresh lists;
    # the three pinned packages themselves are installed from the local files.
    sudo apt-get install -y --no-install-recommends \
        "$tmp/$CCX_DEB" "$tmp/$SPOOLES_DEB" "$tmp/$ARPACK_DEB"
    cp /usr/bin/ccx "$INSTALL_DIR/bin/ccx"
    rm -rf "$tmp"; trap - EXIT
fi
echo "ccx: $(ccx_banner)"

# --- gmsh -------------------------------------------------------------------
if ! "$INSTALL_DIR/bin/gmsh" --version 2>/dev/null | grep -q "^${GMSH_VERSION}"; then
    tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
    fetch "$GMSH_URL" "$GMSH_SHA256" "$tmp/$GMSH_TAR"
    tar -xzf "$tmp/$GMSH_TAR" -C "$tmp"
    cp "$tmp/gmsh-${GMSH_VERSION}-Linux64/bin/gmsh" "$INSTALL_DIR/bin/gmsh"
    rm -rf "$tmp"; trap - EXIT
fi
echo "gmsh: $("$INSTALL_DIR/bin/gmsh" --version)"

# --- versions record --------------------------------------------------------
if [ -d "$(dirname "$0")" ]; then
    {
        echo "calculix-ccx: 2.20-1 (Debian bookworm .deb, sha256: $CCX_SHA256)"
        echo "libspooles2.2: 2.2-14 (Debian bookworm .deb, sha256: $SPOOLES_SHA256)"
        echo "libarpack2: 3.8.0-3 (Debian bookworm .deb, sha256: $ARPACK_SHA256)"
        echo "gmsh: $GMSH_VERSION (official tarball, sha256: $GMSH_SHA256)"
        echo "python3: $(python3 --version 2>&1 | awk '{print $2}')"
    } > "$(cd "$(dirname "$0")" && pwd)/VERSIONS.txt"
fi
echo "setup complete -> $INSTALL_DIR/bin"
