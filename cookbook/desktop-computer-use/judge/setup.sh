#!/usr/bin/env bash
# Install pinned tools for the desktop-computer-use judge, idempotently,
# into the $HOME of the sandbox the judge runs in.
#
#   apt (sudo, once): Xvfb, fluxbox, xdotool, xclip, imagemagick,
#                      libreoffice-calc  -- the real desktop stack, installed
#                      from nothing on a machine the agent does not control.
#   pip  (--require-hashes): openpyxl 3.1.5 (+ et_xmlfile 2.0.0), the
#                      library the judge reads the saved workbook back with,
#                      sha256-pinned in judge/requirements.txt.
#   ffmpeg: distro build, version recorded in MANIFEST.json by make_media.sh.
#
# No "latest" tags, nothing published in the last two weeks: the apt packages
# are the Debian bookworm releases and the pip wheels are pinned by version
# with sha256 hashes.  Exits non-zero on any checksum mismatch or install
# failure.
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

APT_PKGS=(xvfb fluxbox xdotool xclip imagemagick libreoffice-calc)

echo "setup: installing desktop stack: ${APT_PKGS[*]}"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${APT_PKGS[@]}"

# --- pinned python deps, sha256-checked -----------------------------------
# Verify the committed hashes still match what PyPI serves: download each
# wheel to a temp dir and checksum it BEFORE pip installs.
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
pip download --no-cache-dir --require-hashes \
    -r "$JDIR/requirements.txt" -d "$work" >/dev/null 2>&1 || {
        echo "setup: pip download with pinned hashes failed (checksum mismatch?)" >&2
        exit 1
    }
echo "setup: sha256 pins verified against PyPI downloads"
pip install --no-cache-dir --require-hashes \
    -r "$JDIR/requirements.txt" >/dev/null

# --- versions --------------------------------------------------------------
pkgver() { dpkg-query -W -f='${Version}' "$1" 2>/dev/null || echo missing; }
{
    echo "# desktop-computer-use judge: versions installed by judge/setup.sh"
    echo "# ($(uname -sm))"
    echo "xvfb $(pkgver xvfb)"
    echo "fluxbox $(pkgver fluxbox)"
    echo "xdotool $(pkgver xdotool)"
    echo "xclip $(pkgver xclip)"
    echo "imagemagick $(pkgver imagemagick)"
    echo "libreoffice-calc $(pkgver libreoffice-calc)"
    echo "python3 $(python3 --version | awk '{print $2}')"
    echo "openpyxl $(python3 -c 'import openpyxl;print(openpyxl.__version__)')"
    echo "et_xmlfile $(python3 -c 'import et_xmlfile;print(et_xmlfile.__version__)')"
} > "$JDIR/VERSIONS.txt"
echo "setup: wrote $JDIR/VERSIONS.txt"
echo "setup: done"
