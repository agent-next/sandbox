#!/usr/bin/env bash
# Run from any directory. All scratch, caches and toolchains stay in media/.
#
# The video is built in four stages, each from real output of the previous:
#   1. the judge runs (selftest, grade, collect) -> media/data/
#   2. media/render.py renders the two stills from graded states
#   3. media/clips.py records the moving 3D clips + clips/numbers.json
#   4. Remotion (media/video/) composes those clips into frames ->
#      ffmpeg encodes a lossless master, then the crf 18 web master.
# ffmpeg only ever encodes; it never composes, captions or transitions.
set -euo pipefail
MEDIA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "$MEDIA")"
VIDEO="$MEDIA/video"
for tool in python3 ffmpeg ffprobe node npm; do
    command -v "$tool" >/dev/null || { echo "Missing $tool" >&2; exit 1; }
done
mkdir -p "$MEDIA/work" "$MEDIA/data" "$MEDIA/master" "$MEDIA/.tools" "$VIDEO/public"
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

# A headless GL context for MuJoCo's offscreen renderer. EGL if the driver
# has it, otherwise the pinned OSMesa closure in .tools/lib (see
# GL_TOOLING.md); neither path draws on any display.
export MUJOCO_GL=egl
PROBE='import mujoco; m=mujoco.MjModel.from_xml_string("<mujoco/>"); r=mujoco.Renderer(m, 64, 64); r.close()'
if ! "$PY" -c "$PROBE" > "$WORK/gl.log" 2>&1; then
    if ls "$MEDIA/.tools/lib"/libOSMesa.so* >/dev/null 2>&1; then
        export MUJOCO_GL=osmesa
        export LD_LIBRARY_PATH="$MEDIA/.tools/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
        export PYOPENGL_PLATFORM=osmesa
    else
        echo "== fetching the pinned OSMesa closure (one-time, into .tools/lib) =="
        "$PY" "$MEDIA/gl_tooling.py" --dest "$MEDIA/.tools"
        export MUJOCO_GL=osmesa
        export LD_LIBRARY_PATH="$MEDIA/.tools/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
        export PYOPENGL_PLATFORM=osmesa
    fi
    "$PY" -c "$PROBE"   # fail the build if GL is still unusable
fi
echo "== MuJoCo 3D stills from graded states ($MUJOCO_GL) =="
"$PY" "$MEDIA/render.py"

echo "== recording the motion clips ($MUJOCO_GL) =="
"$PY" "$MEDIA/clips.py"
rm -f "$VIDEO/public"/*.mp4
cp "$MEDIA/clips/"*.mp4 "$MEDIA/clips/numbers.json" "$VIDEO/public/"

echo "== Remotion $(node -p "require('$VIDEO/node_modules/remotion/package.json').version") =="
(cd "$VIDEO" && npm ci --no-audit --no-fund >/dev/null)
FRAMES="$MEDIA/work/frames"
mkdir -p "$FRAMES"
(cd "$VIDEO" && npx --no-install remotion render src/index.ts Demo "$FRAMES/elem-%06d.png" \
    --sequence --every-frame --log=error --concurrency=4)
# One frame per composition frame, numbered 1..960 -> named exactly here.
(cd "$VIDEO" && ls "$FRAMES"/elem-*.png | wc -l | xargs -I{} echo "{} rendered frames")
N="$(ls "$FRAMES"/elem-*.png | wc -l)"
test "$N" -eq 960 || { echo "expected 960 frames, got $N" >&2; exit 1; }

echo "== lossless crf 0 master =="
# crf 0 is already lossless for x264; yuv444p keeps the renderer's full
# chroma, so the web encode's only loss is the final crf 18 pass.
ffmpeg -y -v error -threads 2 -r 30 -i "$FRAMES/elem-%06d.png" \
    -c:v libx264 -threads 2 -crf 0 -preset ultrafast -pix_fmt yuv444p \
    -movflags +faststart -map_metadata -1 -an "$MEDIA/master/demo.mp4"
echo "== H.264 web encode from crf 0 master =="
ffmpeg -y -v error -threads 2 -i "$MEDIA/master/demo.mp4" \
    -c:v libx264 -threads 2 -crf 18 -preset slow -pix_fmt yuv420p \
    -movflags +faststart -map_metadata -1 -an "$MEDIA/demo.mp4"
"$PY" "$MEDIA/manifest.py"
"$PY" -m unittest discover -s "$MEDIA" -p test_media.py -v
ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate,pix_fmt \
    -show_entries format=duration,size -of default=noprint_wrappers=1 "$MEDIA/demo.mp4"
echo "== video gate =="
python3 /home/user/w/cookbook/tools/video_gate.py "$MEDIA/demo.mp4"
echo "make_media: done"
