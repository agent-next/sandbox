#!/usr/bin/env bash
# Install pinned tools for the ctf-flag-hunt judge, idempotently.
# gcc 12.2.0 (Debian bookworm gcc-12) via a sha256-checked .deb download.
# Judge engine: Python >= 3.10, stdlib only (no pip installs needed).
set -euo pipefail

GCC_PKG_VERSION="12.2.0-14+deb12u1"
GCC_VERSION="12.2.0"
GCC_URL="https://deb.debian.org/debian/pool/main/g/gcc-12/gcc-12_12.2.0-14+deb12u1_amd64.deb"
GCC_SHA256="b46f33cc2ec245e435e043807038cecf4b201ef004800e9dfc1455240360e49d"

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

installed() {
    dpkg-query -W -f='${Version}' gcc-12 2>/dev/null || true
}

if [ "$(installed)" = "$GCC_PKG_VERSION" ]; then
    echo "setup: gcc-12 $GCC_PKG_VERSION already installed (skipping download)"
else
    echo "setup: downloading gcc-12 $GCC_PKG_VERSION from Debian pool"
    tmpdir="$(mktemp -d)"
    trap 'rm -rf "$tmpdir"' EXIT
    curl -fsSL -o "$tmpdir/gcc-12.deb" "$GCC_URL"
    echo "$GCC_SHA256  $tmpdir/gcc-12.deb" | sha256sum -c - || {
        echo "setup: sha256 mismatch on gcc-12.deb" >&2
        exit 1
    }
    # apt resolves the runtime dependencies the .deb declares.
    sudo apt-get update -qq
    sudo apt-get install -y -qq "$tmpdir/gcc-12.deb"
    actual="$(installed)"
    if [ "$actual" != "$GCC_PKG_VERSION" ]; then
        echo "setup: installed gcc-12 '$actual' != '$GCC_PKG_VERSION'" >&2
        exit 1
    fi
fi

python3 - <<'EOF' || { echo "setup: python3 >= 3.10 required" >&2; exit 1; }
import sys
assert sys.version_info >= (3, 10), sys.version
EOF

echo "setup: tool versions"
gcc-12 --version | sed -n '1p'
dpkg-query -W -f='gcc-12 debian package: ${Version}\n' gcc-12 2>/dev/null || true
python3 --version
{
    echo "# ctf-flag-hunt judge: versions installed by judge/setup.sh"
    echo "# ($(uname -sm))"
    echo "gcc-12 $(gcc-12 -dumpfullversion)"
    echo "gcc-12 debian package: $(dpkg-query -W -f='${Version}' gcc-12 2>/dev/null || echo 'n/a')"
    echo "python3 $(python3 --version | awk '{print $2}')"
} > "$JDIR/VERSIONS.txt"
echo "setup: wrote $JDIR/VERSIONS.txt"
echo "setup: done"
