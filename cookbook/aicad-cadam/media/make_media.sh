#!/usr/bin/env bash
# media/make_media.sh — regenerate every aicad-cadam media file from the
# judge's real outputs (media/data/, written by media/rerun_judge.sh).
#
# Needs on PATH: ffmpeg (Debian bookworm 5.1.x), libosmesa6, DejaVu fonts,
# and the pinned wheels of media/requirements.txt installed into
# $HOME/.venvs/aicad-media (PyOpenGL 3.1.0 from the hash-checked sdist —
# see the header of media/requirements.txt).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="${AICAD_MEDIA_PY:-$HOME/.venvs/aicad-media/bin/python}"
export PYOPENGL_PLATFORM=osmesa

echo "=== figures (result.png, loop.png) ==="
"$PY" "$HERE/make_figures.py"

echo "=== frames (media/frames/, git-ignored) ==="
"$PY" "$HERE/make_frames.py"

echo "=== encode: lossless master, then the web demo.mp4 ==="
mkdir -p "$HERE/master"
ffmpeg -y -framerate 30 -i "$HERE/frames/f%05d.png" \
    -c:v libx264 -crf 0 -preset veryfast -pix_fmt yuv420p \
    "$HERE/master/demo_master.mp4" -loglevel error
ffmpeg -y -i "$HERE/master/demo_master.mp4" \
    -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p -movflags +faststart \
    "$HERE/demo.mp4" -loglevel error
ls -la "$HERE/demo.mp4"

echo "=== video gate (cookbook/tools/video_gate.py on main) ==="
GATE="$(git rev-parse --show-toplevel)/cookbook/tools/video_gate.py"
if [ -f "$GATE" ]; then
    python3 "$GATE" "$HERE/demo.mp4" || true
else
    echo "video_gate.py not on this branch — run it from main:"
    echo "  git show origin/main:cookbook/tools/video_gate.py > /tmp/video_gate.py"
    echo "  python3 /tmp/video_gate.py $HERE/demo.mp4"
fi
