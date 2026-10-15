#!/usr/bin/env bash
set -euo pipefail
MEDIA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$MEDIA/../../.." && pwd)"
PY="${SIM_TUNER_MEDIA_PYTHON:-$MEDIA/.tools/bin/python}"
if [ ! -x "$PY" ]; then
    python3 -m venv "$MEDIA/.tools"
    "$PY" -m pip install --require-hashes -r "$MEDIA/../judge/requirements.lock"
    "$PY" -m pip install -r "$MEDIA/requirements.txt"
fi
mkdir -p "$MEDIA/data" "$MEDIA/master" "$MEDIA/.frames"
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export MUJOCO_GL=egl
PROBE='import mujoco; m=mujoco.MjModel.from_xml_string("<mujoco/>"); r=mujoco.Renderer(m,64,64); r.close()'
if ! "$PY" -c "$PROBE" 2>/dev/null; then
    export MUJOCO_GL=osmesa
    "$PY" -c "$PROBE"
fi
"$PY" "$MEDIA/collect.py"
"$PY" "$MEDIA/render.py"
ffmpeg -y -v error -i "$MEDIA/master/demo.mp4" \
    -c:v libx264 -threads 2 -crf 18 -preset slow -pix_fmt yuv420p \
    -movflags +faststart -map_metadata -1 -an "$MEDIA/demo.mp4"
python3 "$ROOT/cookbook/tools/video_gate.py" "$MEDIA/demo.mp4" --json "$MEDIA/video-gate.json"
"$PY" -c 'import os,sys; assert os.path.getsize(sys.argv[1]) < 8_000_000, "web video must be under 8 MB"' "$MEDIA/demo.mp4"
ffmpeg -y -v error -i "$MEDIA/demo.mp4" -vf fps=1 "$MEDIA/.frames/review-%02d.png"
"$PY" "$MEDIA/manifest.py"
ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate,pix_fmt \
    -show_entries format=duration,size -of default=noprint_wrappers=1 "$MEDIA/demo.mp4"
