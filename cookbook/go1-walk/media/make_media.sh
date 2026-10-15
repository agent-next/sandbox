#!/usr/bin/env bash
set -euo pipefail
MEDIA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p "$MEDIA/.tools" "$MEDIA/work" "$MEDIA/data" "$MEDIA/master"
for tool in python3 ffmpeg ffprobe; do
    command -v "$tool" >/dev/null || { echo "Missing $tool" >&2; exit 1; }
done
python3 -c 'import sys; assert sys.version_info[:2] == (3, 12), "media needs CPython 3.12"'
PY="$MEDIA/.tools/venv/bin/python"
if [ ! -x "$PY" ]; then python3 -m venv "$MEDIA/.tools/venv"; fi
"$PY" -m pip install --quiet --require-hashes -r "$MEDIA/requirements.lock"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
export PYTHONHASHSEED=0
echo "== independent grade, real self-test, exact trajectories =="
python3 "$MEDIA/collect.py"
export MUJOCO_GL=egl
PROBE='import mujoco; m=mujoco.MjModel.from_xml_string("<mujoco/>"); r=mujoco.Renderer(m,64,64); r.close()'
if ! "$PY" -c "$PROBE" > "$MEDIA/work/egl.log" 2>&1; then
    export MUJOCO_GL=osmesa
    "$PY" -c "$PROBE"
fi
echo "== MuJoCo 3D replay ($MUJOCO_GL), Pillow labels, lossless master =="
"$PY" "$MEDIA/render.py"
echo "== web encode from CRF 0 master =="
ffmpeg -y -v error -threads 2 -i "$MEDIA/master/demo.mp4" \
    -c:v libx264 -threads 2 -crf 18 -preset slow -pix_fmt yuv420p \
    -movflags +faststart -map_metadata -1 -an "$MEDIA/demo.mp4"
# Inspect decoded web frames, not only the uncompressed render inputs.
for moment in 0 1 4 11 25; do
    ffmpeg -y -v error -threads 2 -ss "$moment" -i "$MEDIA/demo.mp4" \
        -frames:v 1 -threads 2 "$MEDIA/work/review-${moment}s.png"
done
"$PY" "$MEDIA/manifest.py"
"$PY" -m unittest discover -s "$MEDIA" -p test_media.py -v
ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate,pix_fmt \
    -show_entries format=duration,size -of default=noprint_wrappers=1 "$MEDIA/demo.mp4"
echo "make_media: done"
