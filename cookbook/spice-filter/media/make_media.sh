#!/usr/bin/env bash
# Regenerate every media file for the spice-filter demo from judge outputs.
#   media/result.png   Bode magnitude vs the spec mask, pass lines drawn
#   media/loop.png     agent-loop replay (failing gate per iteration until
#                      pass) + self-test kill-rate bars
#   media/demo.mp4     the same figures animated (from a lossless crf-0
#                      master in media/master/, git-ignored)
#   media/MANIFEST.json  what each file shows, source data, sha256
# Pinned matplotlib wheels: judge/requirements.txt (installed with
# --require-hashes into a venv). ffmpeg: distro build, version recorded in
# MANIFEST.json.
set -euo pipefail

DEMO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MEDIA="$DEMO/media"
VENV="${MEDIA_VENV:-$MEDIA/.venv}"

mkdir -p "$MEDIA/master" "$MEDIA/data"

# --- pinned python environment for plotting ------------------------------
if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c \
       "import matplotlib, contourpy, numpy" >/dev/null 2>&1; then
    echo "media: creating venv, installing pinned wheels from judge/requirements.txt"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --no-cache-dir --require-hashes \
        -r "$DEMO/judge/requirements.txt" >/dev/null
fi
PY="$VENV/bin/python"
echo "media: $(python3 --version | awk '{print "python "$2}'), matplotlib $("$PY" -c 'import matplotlib;print(matplotlib.__version__)'), ffmpeg $(ffmpeg -version | awk 'NR==1{print $3}' | tr -d ')')"

# --- source data: judge outputs only ------------------------------------
# The replay re-runs the judge on known-bad artifacts and the good one in
# the order a fixing agent would meet them (bad -> partly fixed -> good);
# it is a scripted replay, not a recorded live trace.
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
python3 -I "$DEMO/judge/mutants.py" \
    "$DEMO/examples/good/lpf4sk.cir" "$work/mutants" >/dev/null
for m in r-decade-up off-series unrecognised-topology; do
    bash "$DEMO/judge/grade.sh" "$work/mutants/$m.cir" \
        --json "$work/$m.json" >/dev/null || true
done
bash "$DEMO/judge/grade.sh" "$DEMO/examples/good/lpf4sk.cir" \
    --json "$work/good.json" >/dev/null
echo "media: replay verdicts graded (r-decade-up -> off-series -> unrecognised-topology -> good)"

"$PY" "$MEDIA/make_data.py" "$DEMO" "$work"

# --- figures -------------------------------------------------------------
"$PY" "$MEDIA/make_figures.py"

# --- video: lossless master, then web encode -----------------------------
frames="$(mktemp -d)"
trap 'rm -rf "$work" "$frames"' EXIT
echo "media: rendering 1080p30 frames (lossless master -> crf 18 web encode)"
FRAMES_DIR="$frames" "$PY" "$MEDIA/make_video.py"
ffmpeg -y -loglevel error -framerate 30 -i "$frames/frame%05d.png" \
    -c:v libx264 -crf 0 -preset veryfast -pix_fmt yuv444p \
    "$MEDIA/master/demo_master.mp4"
ffmpeg -y -loglevel error -i "$MEDIA/master/demo_master.mp4" \
    -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p -movflags +faststart \
    "$MEDIA/demo.mp4"

"$PY" "$MEDIA/make_manifest.py"

size=$(stat -c%s "$MEDIA/demo.mp4")
if [ "$size" -ge 8388608 ]; then
    echo "media: demo.mp4 is $size bytes >= 8 MB" >&2
    exit 1
fi
echo "media: demo.mp4 is $size bytes"
echo "media: done"
