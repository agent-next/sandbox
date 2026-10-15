#!/usr/bin/env bash
# Regenerate every media file for the solidcraft-cad demo from real tool output.
#   media/data/          SolidCraft renders (git-ignored) + judge verdicts (JSON)
#   media/result.png     delivered part + every judge pass rule vs its limit
#   media/loop.png       repair replay (gates passed per grade) + self-test kills
#   media/demo.mp4       the story as 1080p30 video, from a lossless crf-0
#                        master in media/master/ (git-ignored)
#   media/MANIFEST.json  what each file shows, its command and sha256
# Needs judge/setup.sh first (SolidCraft + the venv with pinned matplotlib).
# ffmpeg: distro build, version recorded in MANIFEST.json.
set -euo pipefail

DEMO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MEDIA="$DEMO/media"
PY="$HOME/.local/solidcraft-judge-venv/bin/python"
[ -x "$PY" ] || { echo "media: run judge/setup.sh first" >&2; exit 1; }
if ! command -v ffmpeg >/dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq ffmpeg
fi

work="$(mktemp -d)"
frames="$(mktemp -d)"
trap 'rm -rf "$work" "$frames"' EXIT
mkdir -p "$MEDIA/master"

"$PY" "$MEDIA/make_media.py" data "$work"
"$PY" "$MEDIA/make_media.py" figures
FRAMES_DIR="$frames" "$PY" "$MEDIA/make_media.py" frames
ffmpeg -y -loglevel error -framerate 30 -i "$frames/frame%05d.png" \
    -c:v libx264 -crf 0 -preset veryfast -pix_fmt yuv444p "$MEDIA/master/demo_master.mp4"
ffmpeg -y -loglevel error -i "$MEDIA/master/demo_master.mp4" \
    -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p -movflags +faststart "$MEDIA/demo.mp4"
"$PY" "$MEDIA/make_media.py" manifest

size=$(stat -c%s "$MEDIA/demo.mp4")
if [ "$size" -ge 8388608 ]; then
    echo "media: demo.mp4 is $size bytes >= 8 MB" >&2
    exit 1
fi
echo "media: demo.mp4 is $size bytes"
echo "media: done"
