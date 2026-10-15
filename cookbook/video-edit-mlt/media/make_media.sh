#!/usr/bin/env bash
set -euo pipefail
MEDIA="$(cd "$(dirname "$0")" && pwd)"
DEMO="$(dirname "$MEDIA")"
export PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
PY="$HOME/.local/video-edit-mlt/venv/bin/python"
export PATH="$HOME/.local/video-edit-mlt/Shotcut.app:$PATH"
cd "$DEMO"
mkdir -p media/data media/work media/master
if [ "${1:-}" != --reuse ]; then
    bash judge/setup.sh
    bash judge/grade.sh examples/good/edit.mlt --seed 1 --export media/data --json media/data/verdict.json
    bash judge/selftest.sh --json media/work/selftest-full.json
    "$PY" -B media/make_media.py summarize
fi
"$PY" -B media/make_media.py build
ffmpeg -y -v error -i media/master/lossless.mp4 \
    -c:v libx264 -crf 18 -preset slow -threads 2 -pix_fmt yuv420p \
    -movflags +faststart media/demo.mp4
python3 ../tools/video_gate.py media/demo.mp4 --json media/video_gate.json
python3 ../tools/result.py check media/result.json
"$PY" -B media/make_media.py manifest
