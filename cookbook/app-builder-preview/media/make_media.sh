#!/usr/bin/env bash
# Regenerate every media file for the app-builder-preview demo from judge
# outputs.
#   media/result.png   the judge's gate numbers for the known-good artifact
#                      (DOM counts vs spec expectations, build size vs the
#                      250 KiB budget, console errors vs zero)
#   media/loop.png     scripted fixing replay + self-test kill-rate bars
#   media/demo.mp4     step-through of the 6 flow screenshots the judge
#                      captured, then the two figures (from a lossless
#                      crf-0 master in media/master/, git-ignored)
#   media/MANIFEST.json  what each file shows, source data, sha256
# Pinned matplotlib wheels: judge/requirements.txt (installed with
# --require-hashes into a venv). ffmpeg: distro build, version recorded in
# MANIFEST.json. The judge toolchain (judge/setup.sh) must already be
# installed - make_media.sh re-runs it to be sure.
set -euo pipefail

DEMO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MEDIA="$DEMO/media"
VENV="${MEDIA_VENV:-$MEDIA/.venv}"

mkdir -p "$MEDIA/master"

# --- pinned python environment for plotting ------------------------------
if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c \
       "import matplotlib, numpy, PIL" >/dev/null 2>&1; then
    echo "media: creating venv, installing pinned wheels from judge/requirements.txt"
    rm -rf "$VENV"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --no-cache-dir --require-hashes \
        -r "$DEMO/judge/requirements.txt" >/dev/null
fi
PY="$VENV/bin/python"
echo "media: $(python3 -c 'import sys;print("python "+".".join(map(str,sys.version_info[:3])))'), matplotlib $($PY -c 'import matplotlib;print(matplotlib.__version__)'), ffmpeg $(ffmpeg -version | awk 'NR==1{print $3}' | tr -d ')')"

# --- judge toolchain ------------------------------------------------------
bash "$DEMO/judge/setup.sh" >/dev/null

# --- source data: judge outputs only -------------------------------------
# Regrades the good artifact (with --shots) and every scripted mutant; the
# replay order is the order a fixing agent would meet the failures in.
echo "media: grading the good artifact and every mutant (slow: real builds + real browser flows)"
python3 -I "$MEDIA/make_data.py"

# --- figures -------------------------------------------------------------
"$PY" "$MEDIA/make_figures.py"

# --- video: lossless master, then web encode -----------------------------
frames="$(mktemp -d)"
trap 'rm -rf "$frames"' EXIT
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
