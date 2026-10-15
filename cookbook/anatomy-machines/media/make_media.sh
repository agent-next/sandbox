#!/usr/bin/env bash
# media/make_media.sh — regenerate every shipped file in media/.
#
# Inputs: media/data/ produced by media/collect_data.sh (real judge
# verdicts + selftest log — rerun it if data/ is missing), the judge
# toolchain from judge/setup.sh (headless Chrome + SwiftShader renders
# the scene, Playwright screenshots #stageView at 1920x1080), ffmpeg.
#
# Produces:  result.png  assembled.png  loop.png  demo.mp4  MANIFEST.json
#            media/master/{exploded.png,master.mp4,frames/}  (git-ignored)
#
# Every demo.mp4 frame and every showcase still is a real screenshot of
# the figure — nothing synthesized or interpolated.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA="${HERE}/data"
JVENV="$HOME/.anatomy-judge/venv"
VENV="${HERE}/.venv"

# ---------------------------------------------------------- inputs ----
missing=0
for f in verdict-good.json selftest.log \
         verdict-blank_canvas.json verdict-missing_parts.json \
         verdict-console_error.json verdict-static_camera.json \
         verdict-wrong_labels.json verdict-no_interaction.json \
         verdict-tiny_capture.json; do
    if [ ! -s "${DATA}/${f}" ]; then
        echo "make_media: missing data file ${DATA}/${f}" >&2
        missing=1
    fi
done
if [ "${missing}" -ne 0 ]; then
    echo "make_media: run media/collect_data.sh first" >&2
    exit 3
fi
if [[ ! -x "$JVENV/bin/python" ]]; then
    echo "make_media: $JVENV/bin/python missing — run judge/setup.sh first" >&2
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

# ---------------------------------------------- real renders + video --
PLAYWRIGHT_BROWSERS_PATH="$HOME/.cache/ms-playwright" \
    "$JVENV/bin/python" "$HERE/render_media.py" "$HERE"

# ----------------------------------------------------------- figures --
"$PY" "${HERE}/fig_result.py"
"$PY" "${HERE}/fig_loop.py"

# ------------------------------------------------------------- checks --
SIZE=$(stat -c %s "${HERE}/demo.mp4")
if [ "${SIZE}" -ge 8388608 ]; then
    echo "make_media: demo.mp4 is ${SIZE} bytes (limit 8388608)" >&2
    exit 1
fi
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 \
      "${HERE}/demo.mp4")
echo "make_media: demo.mp4 ${SIZE} bytes, ${DUR}s"

# ---------------------------------------------------------- manifest --
"$PY" "${HERE}/manifest.py"
echo "make_media: done — files in ${HERE}"
