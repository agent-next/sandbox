#!/usr/bin/env bash
# Generated clips, scratch and master stay in git-ignored media directories.
set -euo pipefail
MEDIA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for tool in python3 ffmpeg ffprobe; do
    command -v "$tool" >/dev/null || { echo "Missing $tool" >&2; exit 1; }
done
mkdir -p "$MEDIA/work" "$MEDIA/master" "$MEDIA/clips"
WORK="$(mktemp -d "$MEDIA/work/run.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
export TMPDIR="$WORK"
export PYTHONHASHSEED=0 SOURCE_DATE_EPOCH=1792022400
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
PY="$MEDIA/.venv/bin/python"
if [ ! -x "$PY" ]; then
    python3 -m venv "$MEDIA/.venv"
fi
"$PY" -m pip install --quiet --disable-pip-version-check -r "$MEDIA/requirements.txt"
export MUJOCO_GL=egl
PROBE='import mujoco; m=mujoco.MjModel.from_xml_string("<mujoco/>"); r=mujoco.Renderer(m, 64, 64); r.close()'
if ! "$PY" -c "$PROBE" > "$WORK/gl.log" 2>&1; then
    export MUJOCO_GL=osmesa
    "$PY" -c "$PROBE"
fi
echo "== exact judge CPU reference + retained GPU parity =="
"$PY" "$MEDIA/evidence.py"
echo "== MuJoCo 3D clips ($MUJOCO_GL), Pillow overlays, lossless master cut =="
"$PY" "$MEDIA/render.py"
echo "== H.264 web encode from crf 0 master =="
ffmpeg -y -v error -i "$MEDIA/master/demo.mp4" -an \
    -c:v libx264 -threads 2 -crf 18 -preset slow -pix_fmt yuv420p \
    -maxrate 2100k -bufsize 2100k \
    -movflags +faststart -map_metadata -1 "$MEDIA/demo.mp4"
"$PY" "$MEDIA/manifest.py"
"$PY" -m unittest discover -s "$MEDIA" -p test_media.py -v
ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate,pix_fmt,nb_frames \
    -show_entries format=duration,size -of default=noprint_wrappers=1 "$MEDIA/demo.mp4"
echo "make_media: done"
