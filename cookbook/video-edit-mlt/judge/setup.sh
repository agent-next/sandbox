#!/usr/bin/env bash
set -euo pipefail
JDIR="$(cd "$(dirname "$0")" && pwd)"
PREFIX="$HOME/.local/video-edit-mlt"
SHA=c4befab2240964389df6139f00aae0b92949f398fd98083b922f3aabd8b7a844
URL=https://github.com/mltframework/shotcut/releases/download/v26.8.1/shotcut-linux-x86_64-26.8.1.txz
export QT_QPA_PLATFORM=offscreen
export PYTHONDONTWRITEBYTECODE=1
[[ "$(uname -m)" = x86_64 ]]
python3 -c 'import sys; assert sys.version_info[:2] == (3,12), "CPython 3.12 required"'
mkdir -p "$PREFIX"
# Keep the checked archive and verify the installed tree, not just a marker.
if ! (cd "$PREFIX" && sha256sum -c tool.sha256 >/dev/null 2>&1); then
    curl -fL --retry 3 "$URL" -o "$PREFIX/shotcut.txz"
    echo "$SHA  $PREFIX/shotcut.txz" | sha256sum -c -
    tar xJf "$PREFIX/shotcut.txz" -C "$PREFIX"
    (cd "$PREFIX"; find Shotcut.app -type f -print0 | sort -z | xargs -0 sha256sum > tool.sha256)
fi
echo "$SHA  $PREFIX/shotcut.txz" | sha256sum -c -
if ! ldconfig -p | grep libEGL.so.1 >/dev/null || ! ldconfig -p | grep libOpenGL.so.0 >/dev/null; then
    sudo apt-get update
    find /var/lib/apt/lists -maxdepth 1 -name '*Packages*' | grep -q . || {
        echo 'setup: apt update fetched no package lists' >&2; exit 1;
    }
    sudo apt-get install -y libegl1=1.6.0-1 libopengl0=1.6.0-1
fi
"$PREFIX/Shotcut.app/melt" -query filters > "$PREFIX/filters.txt" 2>&1
grep -q qtext "$PREFIX/filters.txt" || { echo 'setup: Qt filters unavailable' >&2; exit 1; }
VENV="$PREFIX/venv"
if [ ! -x "$VENV/bin/python" ]; then
    python3 -m venv "$VENV" || {
        sudo apt-get update
        sudo apt-get install -y python3-venv
        python3 -m venv "$VENV"
    }
fi
REQ="$(sha256sum "$JDIR/requirements.txt" | cut -d' ' -f1)"
if [ "$(cat "$VENV/.requirements.sha256" 2>/dev/null || true)" != "$REQ" ] ||
   ! "$VENV/bin/python" -I -c 'import numpy,PIL; assert numpy.__version__=="2.2.6" and PIL.__version__=="11.3.0"'; then
    "$VENV/bin/pip" install --require-hashes -r "$JDIR/requirements.txt"
    echo "$REQ" > "$VENV/.requirements.sha256"
fi
export VIDEO_EDIT_FFMPEG="$PREFIX/Shotcut.app/ffmpeg"
ASSETS="$JDIR/../assets"
SOURCE_SHA="$(sha256sum "$JDIR/gen_sources.py" "$JDIR/edl.py" "$JDIR/../spec.json" | sha256sum | cut -d' ' -f1)"
if [ "$(cat "$ASSETS/.generator.sha256" 2>/dev/null || true)" != "$SOURCE_SHA" ] ||
   ! (cd "$ASSETS" && sha256sum -c assets.sha256 >/dev/null 2>&1); then
    python3 "$JDIR/gen_sources.py"
    (cd "$ASSETS"; sha256sum clip_*.mp4 *.wav logo.png > assets.sha256)
    echo "$SOURCE_SHA" > "$ASSETS/.generator.sha256"
else
    python3 "$JDIR/gen_sources.py" --verify
fi
{
    "$PREFIX/Shotcut.app/melt" -query 2>&1 | grep -m1 -E 'melt|MLT' || true
    "$VIDEO_EDIT_FFMPEG" -version | sed -n '1p'
    "$PREFIX/Shotcut.app/ffprobe" -version | sed -n '1p'
    "$VENV/bin/python" -c 'import sys,numpy,PIL; print("Python",sys.version.split()[0]); print("numpy",numpy.__version__); print("Pillow",PIL.__version__)'
    dpkg-query -W -f='${Package} ${Version}\n' libegl1 libopengl0
    echo "Shotcut 26.8.1 sha256 $SHA"
} | tee "$JDIR/VERSIONS.txt"
echo 'setup: OK'
