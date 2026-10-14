#!/usr/bin/env bash
# judge/versions.sh — print the versions setup.sh installed, from the tools'
# own --version output and dpkg-query.  Writes judge/VERSIONS.txt.
#
# Usage: bash judge/versions.sh > judge/VERSIONS.txt
#        bash judge/versions.sh --check   # fail if judge/VERSIONS.txt is stale

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSIONS_TXT="$SCRIPT_DIR/VERSIONS.txt"

# Same OpenFOAM environment the judge itself uses (see check_gates.py).
OPENFOAM_PREFIX="${OPENFOAM_PREFIX:-/usr/share/openfoam}"
export FOAM_ETC="$OPENFOAM_PREFIX/etc"
export WM_PROJECT_DIR="$OPENFOAM_PREFIX"

# A pinned snapshot date, so the text is stable and the digest table is the
# actual authority on "what was installed".
cat <<'EOF'
# What judge/setup.sh actually installed — recorded by the tools' own
# --version output, not by hand.
#
# Reproduce:
#   bash judge/setup.sh && bash judge/versions.sh > judge/VERSIONS.txt
#
# Debian bookworm archive, main component, 2026-10-14.
# The 23 .deb sha256 digests that pin this install are in
# judge/package-sha256.txt (generated from `apt-get download --print-uris`,
# so they are the digests the mirror itself publishes for these versions).
# A later Debian point release that rebuilds any of these packages changes a
# digest and setup.sh fails loudly instead of silently installing something
# else.

EOF

echo '### OpenFOAM'
echo ''
for cmd in icoFoam blockMesh checkMesh postProcess; do
    echo "\$ $cmd -version"
    if command -v "$cmd" >/dev/null 2>&1; then
        # OpenFOAM v1912 prints its version banner on an unrecognised -version
        # and then exits 1; the banner is what we want, so swallow the rc.
        { "$cmd" -version 2>&1 || true; } \
            | sed -n '/^Using: OpenFOAM/p;/^Build:/p' | sed 's/^/    /'
    else
        echo "    MISSING"
    fi
    echo ''
done

echo '### dpkg versions (dpkg-query -W)'
echo ''
while read -r pkg; do
    [[ -n "$pkg" ]] || continue
    printf '%s=%s\n' "$pkg" "$(dpkg-query -W -f='${Version}' "$pkg" 2>/dev/null \
                                || echo MISSING)"
done <<EOF
openfoam
libopenfoam
openfoam-examples
openmpi-bin
openmpi-common
libopenmpi3
mpi-default-bin
libscotch-7.0
libptscotch-7.0
libboost-system1.74.0
libxnvctrl0
libhwloc15
libhwloc-plugins
libnl-route-3-200
libmunge2
libibverbs1
ibverbs-providers
libfabric1
libpsm2-2
libpsm-infinipath1
libucx0
libpmix2
librdmacm1
EOF

echo ''
echo '### Pinned .deb sha256 digests (judge/package-sha256.txt)'
echo ''
# Copy the digest table verbatim: VERSIONS.txt should be the one file that
# records everything installed (tool banners, dpkg versions and the exact
# .deb digests), so a reader never has to cross-reference.
grep -v '^\s*$' "$SCRIPT_DIR/package-sha256.txt" | sed 's/^/  /'
echo ''

echo '### Host toolchain (used only by media/make_media.sh)'
echo ''
echo "python3=$(python3 -c 'import platform; print(platform.python_version())')"
echo "ffmpeg=$(ffmpeg -version 2>/dev/null | head -1 | awk '{print $3}')"
echo "ffprobe=$(ffprobe -version 2>/dev/null | head -1 | awk '{print $3}')"

if [[ "${1:-}" == "--check" ]]; then
    # Confirm the recorded versions still describe this machine.  The digests
    # in package-sha256.txt are the real pin; this is a cheap regression guard
    # against someone editing VERSIONS.txt by hand.
    echo "versions.sh --check: verifying judge/VERSIONS.txt is current" >&2
    tmp="$(mktemp)"
    bash "$0" >"$tmp"
    if diff -u "$VERSIONS_TXT" "$tmp"; then
        rm -f "$tmp"
        echo "versions.sh: judge/VERSIONS.txt is current" >&2
    else
        rm -f "$tmp"
        echo "versions.sh: judge/VERSIONS.txt is STALE" >&2
        exit 1
    fi
fi
