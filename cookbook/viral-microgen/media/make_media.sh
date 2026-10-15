#!/usr/bin/env bash
# Regenerate every media file for the viral-microgen demo from judge output.
#
#   bash media/make_media.sh [--seed N]
#
# Needs the pinned judge venv (judge/setup.sh) plus matplotlib and ffmpeg.
# Writes result.png, loop.png, demo.mp4 and MANIFEST.json; the lossless video
# master goes to media/master/, which is git-ignored.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$HERE/.." && pwd)"
VENV="${VIRAL_VENV:-$HOME/.viral-microgen-venv}"
PY="$VENV/bin/python"
SEED="${VIRAL_SEED:-42}"
FPS=30

if [ ! -x "$PY" ]; then
    echo "make_media: $VENV is missing -- run judge/setup.sh first" >&2
    exit 2
fi
if ! command -v ffmpeg >/dev/null; then
    echo "make_media: ffmpeg is required" >&2
    exit 2
fi
"$PY" -c "import matplotlib" 2>/dev/null || {
    echo "make_media: installing matplotlib into $VENV" >&2
    "$PY" -m pip install --quiet matplotlib
}

mkdir -p "$HERE/data" "$HERE/master"

echo "make_media: recording the self-test result (seed $SEED)"
VIRAL_VENV="$VENV" "$PY" "$HERE/make_selftest_data.py" "$DEMO" \
    "$HERE/data/selftest.json" --seed "$SEED"

echo "make_media: figures"
VIRAL_VENV="$VENV" "$PY" "$HERE/make_figures.py" "$DEMO/examples/good" \
    "$HERE" --seed "$SEED"

echo "make_media: video master (lossless)"
VIRAL_VENV="$VENV" "$PY" "$HERE/make_video.py" "$DEMO/examples/good" \
    "$HERE/master/demo.mkv" --seed "$SEED" --fps "$FPS"

echo "make_media: web encode (H.264, crf 18)"
ffmpeg -y -loglevel error -i "$HERE/master/demo.mkv" \
    -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p \
    -movflags +faststart "$HERE/demo.mp4"

echo "make_media: manifest"
VIRAL_VENV="$VENV" "$PY" "$HERE/make_manifest.py" "$HERE" --seed "$SEED"

echo "make_media: done"
ls -la "$HERE/demo.mp4" "$HERE/result.png" "$HERE/loop.png"
