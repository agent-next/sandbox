#!/usr/bin/env bash
# Install pinned tools for the spice-filter judge, idempotently.
# ngspice 39.3+ds-1 (Debian bookworm) via a sha256-checked .deb download.
# Judge engine: Python >= 3.10, stdlib only.  Media pipeline (matplotlib
# wheels for the pinned versions below) is installed by media/make_media.sh
# from judge/requirements.txt, not here.
set -euo pipefail

NGSPICE_VERSION="39.3+ds-1"
NGSPICE_URL="https://deb.debian.org/debian/pool/main/n/ngspice/ngspice_39.3+ds-1_amd64.deb"
NGSPICE_SHA256="710bc58f7a708c0813e33e19c115dc076a3749c18bbe1379cd9dba24c42d32f9"

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

installed() {
    dpkg-query -W -f='${Version}' ngspice 2>/dev/null || true
}

if [ "$(installed)" = "$NGSPICE_VERSION" ]; then
    echo "setup: ngspice $NGSPICE_VERSION already installed (skipping download)"
else
    echo "setup: downloading ngspice $NGSPICE_VERSION from Debian pool"
    tmpdir="$(mktemp -d)"
    trap 'rm -rf "$tmpdir"' EXIT
    curl -fsSL -o "$tmpdir/ngspice.deb" "$NGSPICE_URL"
    echo "$NGSPICE_SHA256  $tmpdir/ngspice.deb" | sha256sum -c - || {
        echo "setup: sha256 mismatch on ngspice.deb" >&2
        exit 1
    }
    # apt resolves the runtime dependencies the .deb declares.
    sudo apt-get update -qq
    sudo apt-get install -y -qq "$tmpdir/ngspice.deb"
    actual="$(installed)"
    if [ "$actual" != "$NGSPICE_VERSION" ]; then
        echo "setup: installed ngspice version '$actual' != '$NGSPICE_VERSION'" >&2
        exit 1
    fi
fi

python3 - <<'EOF' || { echo "setup: python3 >= 3.10 required" >&2; exit 1; }
import sys
assert sys.version_info >= (3, 10), sys.version
EOF

echo "setup: tool versions"
ngspice -v 2>&1 | sed -n '2p'   # "** ngspice-39 : ..."
dpkg-query -W -f='ngspice debian package: ${Version}\n' ngspice
python3 --version
{
    echo "# spice-filter judge: versions installed by judge/setup.sh"
    echo "# ($(uname -sm))"
    echo "ngspice $(ngspice -v 2>&1 | sed -n '2p' | tr -d '*' | awk '{print $1}')"
    echo "ngspice debian package: $(dpkg-query -W -f='${Version}' ngspice)"
    echo "python3 $(python3 --version | awk '{print $2}')"
} > "$JDIR/VERSIONS.txt"
echo "setup: wrote $JDIR/VERSIONS.txt"
echo "setup: done"
