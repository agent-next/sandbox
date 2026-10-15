#!/usr/bin/env bash
# Run from any directory. All scratch, caches and toolchains stay in media/.
set -euo pipefail
MEDIA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "$MEDIA")"
for tool in python3 ffmpeg ffprobe; do
    command -v "$tool" >/dev/null || { echo "Missing $tool" >&2; exit 1; }
done
mkdir -p "$MEDIA/work" "$MEDIA/data" "$MEDIA/master" "$MEDIA/.tools"
WORK="$(mktemp -d "$MEDIA/work/run.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
export TMPDIR="$WORK"
# setup.sh writes VERSIONS.txt; use an unchanged copy of the entire judge so
# media regeneration cannot rewrite the committed toolchain receipt.
cp -R "$DEMO/judge" "$WORK/judge"
mkdir -p "$WORK/examples/good"
cp "$DEMO/examples/good/sim.py" "$WORK/examples/good/"
export HOME="$MEDIA/.tools"
export PYTHONHASHSEED=0 SOURCE_DATE_EPOCH=1791936000
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
echo "== pinned CPU judge setup =="
bash "$WORK/judge/setup.sh"
echo "== real selftest =="
bash "$WORK/judge/selftest.sh" | tee "$MEDIA/data/selftest.txt"
echo "== grade: same full-run path as run.py, seed 0 =="
PY="$HOME/.venvs/sim-engine-arena/bin/python"
"$PY" "$MEDIA/collect.py" "$WORK" "$MEDIA/data" > "$WORK/collect.log"
grep 'Actual graded' "$WORK/collect.log"
"$PY" -m pip install --quiet --disable-pip-version-check -r "$MEDIA/requirements.txt"
# Record the final shared toolchain, including Pillow, on every build.
"$PY" -c 'import sys, mujoco, numpy; print("## python %s, mujoco %s, numpy %s" % (sys.version.split()[0], mujoco.__version__, numpy.__version__))' > "$MEDIA/data/versions.txt"
"$PY" -m pip list --format=freeze >> "$MEDIA/data/versions.txt"
export MUJOCO_GL=egl
PROBE='import mujoco; m=mujoco.MjModel.from_xml_string("<mujoco/>"); r=mujoco.Renderer(m, 64, 64); r.close()'
if ! "$PY" -c "$PROBE" > "$WORK/gl.log" 2>&1; then
    export MUJOCO_GL=osmesa
    "$PY" -c "$PROBE"
fi
echo "== MuJoCo 3D frames ($MUJOCO_GL), Pillow labels and lossless master =="
"$PY" "$MEDIA/render.py"
echo "== H.264 web encode from crf 0 master =="
ffmpeg -y -v error -threads 2 -i "$MEDIA/master/demo.mp4" \
    -c:v libx264 -threads 2 -crf 18 -preset slow -pix_fmt yuv420p \
    -movflags +faststart -map_metadata -1 -an "$MEDIA/demo.mp4"
"$PY" "$MEDIA/manifest.py"
"$PY" -m unittest discover -s "$MEDIA" -p test_media.py -v
ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate,pix_fmt \
    -show_entries format=duration,size -of default=noprint_wrappers=1 "$MEDIA/demo.mp4"
echo "make_media: done"
