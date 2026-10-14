#!/usr/bin/env bash
#
# make_media.sh -- rebuild every media artifact from the judge outputs
# in media/data/.  Run media/collect_data.sh first if media/data/ is
# missing (it re-runs the judge; ~15 min).
#
# Produces:  result.png  loop.png  demo.mp4  MANIFEST.json
#            media/master/demo.mp4  (lossless crf 0 master, git-ignored)
#
# Tools: python3 + pinned matplotlib (media/requirements.txt, installed
# into media/.venv), ffmpeg from the distro.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA="${HERE}/data"
VENV="${HERE}/.venv"
FRAMES="${HERE}/frames"
MASTER="${HERE}/master"

# ---------------------------------------------------------- inputs ----
# Every figure reads its numbers from these files; refuse to draw if any
# is missing -- an invented trace is worse than no figure.
REQUIRED="verdict-good.json uart-good.json uart-crc-poly.json \
size-good.txt firmware-good.map selftest.log loop.json"
for m in build-broken crc-init crc-no-xorout crc-poly crc-shift-dir \
         ring-count-drift ring-drop-newest ring-off-by-one \
         shell-bad-hex-accepted shell-unknown-ok startup-bad-sp \
         startup-no-reset uart-no-init uart-rx-inverted; do
    REQUIRED="${REQUIRED} verdict-${m}.json"
done
missing=0
for f in ${REQUIRED}; do
    if [ ! -s "${DATA}/${f}" ]; then
        echo "make_media: missing data file ${DATA}/${f}" >&2
        missing=1
    fi
done
if [ "${missing}" -ne 0 ]; then
    echo "make_media: run media/collect_data.sh first" >&2
    exit 3
fi
command -v ffmpeg >/dev/null 2>&1 || {
    echo "make_media: ffmpeg not found" >&2; exit 3; }
command -v ffprobe >/dev/null 2>&1 || {
    echo "make_media: ffprobe not found" >&2; exit 3; }

# ------------------------------------------------------- python env ---
if [ ! -x "${VENV}/bin/python" ]; then
    python3 -m venv "${VENV}"
    "${VENV}/bin/pip" install --quiet --upgrade pip
    "${VENV}/bin/pip" install --quiet -r "${HERE}/requirements.txt"
fi
PY="${VENV}/bin/python"
"${PY}" -c 'import matplotlib, sys; print("matplotlib", matplotlib.__version__)'
ffmpeg -version | head -1

# ----------------------------------------------------------- figures --
"${PY}" "${HERE}/fig_result.py"
"${PY}" "${HERE}/fig_loop.py"

# ------------------------------------------------------------- video --
rm -rf "${FRAMES}"
"${PY}" "${HERE}/video.py"
mkdir -p "${MASTER}"
ffmpeg -y -loglevel error -framerate 30 -i "${FRAMES}/%05d.png" \
    -c:v libx264 -crf 0 -pix_fmt yuv420p "${MASTER}/demo.mp4"
ffmpeg -y -loglevel error -i "${MASTER}/demo.mp4" \
    -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p \
    -movflags +faststart "${HERE}/demo.mp4"

SIZE=$(stat -c %s "${HERE}/demo.mp4")
if [ "${SIZE}" -ge 8388608 ]; then
    echo "make_media: demo.mp4 is ${SIZE} bytes (limit 8388608)" >&2
    exit 1
fi
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 \
      "${HERE}/demo.mp4")
echo "demo.mp4: ${SIZE} bytes, ${DUR}s"

# ---------------------------------------------------------- manifest --
"${PY}" "${HERE}/manifest.py"
echo "make_media: done"
