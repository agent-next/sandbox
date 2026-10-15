#!/bin/bash
# Setup for the 3dprint-gcode demo: pinned OrcaSlicer + Klipper into $HOME.
# Idempotent. Every download is sha256/SHA-checked.
#
# Tool order tried for the slicer, per the demo brief:
#   1. OrcaSlicer CLI  -- works: v2.3.0 AppImage (glibc-compatible build) runs
#      headless on Debian 12 after --appimage-extract.  (v2.4.x AppImages are
#      built on Ubuntu 24.04 / glibc 2.38 and cannot run on bookworm.)
#   2. Bambu Studio CLI -- not needed (OrcaSlicer works).
#   3. PrusaSlicer CLI  -- not needed.
set -euo pipefail

TOOLS="$HOME/tools"
ORCA_DIR="$TOOLS/orca"
KLIPPER_DIR="$TOOLS/klipper"
mkdir -p "$TOOLS"

# --- pinned downloads -------------------------------------------------------
ORCA_VERSION="2.3.0"
ORCA_TAG="v2.3.0"
ORCA_APPIMAGE="OrcaSlicer_Linux_AppImage_V${ORCA_VERSION}.AppImage"
ORCA_URL="https://github.com/OrcaSlicer/OrcaSlicer/releases/download/${ORCA_TAG}/${ORCA_APPIMAGE}"
ORCA_SHA256="73079d88ec36f0615db7919d00aa26fe301e348ba6e051862a7cfc4040150c03"

# Klipper: pinned commit (2026-09-18), fetched as a tarball and sha256-checked.
KLIPPER_COMMIT="ce7002bedf37e938bb483572949f3703ac6476cb"
KLIPPER_TAR="klipper-${KLIPPER_COMMIT}.tar.gz"
KLIPPER_URL="https://github.com/Klipper3d/klipper/archive/${KLIPPER_COMMIT}.tar.gz"
KLIPPER_SHA256="da1c6223d90652cda6e826e3cf896cf97d6e11aa13aa4c8feb5232dac068f70b"

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

# --- apt prerequisites ------------------------------------------------------
# OrcaSlicer GUI runtime libs (needed even for CLI slicing), AVR toolchain to
# build the Klipper MCU data dictionary (atmega2560 target, exactly as the
# Klipper test suite does), and git/curl for fetches.
echo "== apt-get update =="
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
    curl ca-certificates python3 python3-pip make gcc \
    gcc-avr avr-libc \
    libglib2.0-0 libopengl0 libglu1-mesa libegl1 libgl1 \
    libwebkit2gtk-4.0-37

# --- Python deps for klippy (pinned, hash-checked) ----------------------------
python3 -m pip install --user --require-hashes -r "$(cd "$(dirname "$0")" && pwd)/requirements.txt"

# --- OrcaSlicer --------------------------------------------------------------
if [ ! -x "$ORCA_DIR/bin/orca-slicer" ]; then
    tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
    fetch "$ORCA_URL" "$ORCA_SHA256" "$tmp/$ORCA_APPIMAGE"
    chmod +x "$tmp/$ORCA_APPIMAGE"
    (cd "$tmp" && "./$ORCA_APPIMAGE" --appimage-extract >/dev/null)
    rm -rf "$ORCA_DIR"
    mv "$tmp/squashfs-root" "$ORCA_DIR"
    rm -rf "$tmp"; trap - EXIT
fi
echo "orca-slicer: $(APPDIR="$ORCA_DIR" "$ORCA_DIR/bin/orca-slicer" --help 2>/dev/null | sed -n '2p' | tr -d ':')"

# --- Klipper -----------------------------------------------------------------
if [ ! -f "$KLIPPER_DIR/out/klipper.dict" ]; then
    tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
    fetch "$KLIPPER_URL" "$KLIPPER_SHA256" "$tmp/$KLIPPER_TAR"
    rm -rf "$KLIPPER_DIR"
    mkdir -p "$KLIPPER_DIR"
    tar -xzf "$tmp/$KLIPPER_TAR" -C "$KLIPPER_DIR" --strip-components=1
    rm -rf "$tmp"; trap - EXIT
    # Build the MCU data dictionary exactly like Klipper's CI: copy the
    # pinned test config, olddefconfig, make.
    (cd "$KLIPPER_DIR" && \
     cp test/configs/atmega2560.config .config && \
     make olddefconfig >/dev/null && \
     make -j"$(nproc)" >/dev/null)
fi
echo "klipper dict: $KLIPPER_DIR/out/klipper.dict"

# --- versions record ----------------------------------------------------------
{
    echo "orca-slicer: $ORCA_VERSION (AppImage $ORCA_APPIMAGE, sha256: $ORCA_SHA256)"
    echo "klipper: $KLIPPER_COMMIT (github tarball, sha256: $KLIPPER_SHA256)"
    echo "python3: $(python3 --version 2>&1 | awk '{print $2}')"
    echo "klippy dict target: atmega2560"
    grep -E '^[a-zA-Z]' "$(cd "$(dirname "$0")" && pwd)/requirements.txt" | \
        sed 's/ .*//' | sort -u | sed 's/^/pip: /'
} > "$(cd "$(dirname "$0")" && pwd)/VERSIONS.txt"

echo "setup complete"
