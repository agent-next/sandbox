#!/usr/bin/env bash
#
# make_media.sh -- rebuild every media artifact from real runs.
#
# Pipeline: record the real run as asciicast footage (media/clips/*.cast,
# git-ignored), replay the storyboard's windows to 30 fps motion clips,
# read this run's numbers, render the composition headless with the pinned
# HyperFrames, and encode demo.mp4 with ffmpeg (encode only -- every pixel
# of the visuals is either the recorded footage or the HTML composition).
#
# Produces:  result.png  loop.png  demo.mp4  MANIFEST.json
#            media/master/demo.mp4  (lossless crf 0 master, git-ignored)
#            media/clips/*.cast + *.mp4  (git-ignored)
#
# Run media/collect_data.sh first if media/data/ is missing (it re-runs
# the judge; ~15 min).  The recording stages need the demo's own tools
# (judge/setup.sh: pinned Arm toolchain + QEMU) and asciinema.
#
# Tools: python3 + pinned matplotlib (media/requirements.txt, installed
# into media/.venv), Node >= 22 + npm ci for HyperFrames, ffmpeg from the
# distro.

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
command -v node >/dev/null 2>&1 || {
    echo "make_media: node not found (>= 22 needed for HyperFrames)" >&2; exit 3; }

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
# 1. footage: the real run, one asciicast per phase (boot/build/grade/
#    selftest), recorded under `asciinema rec` by media/record.py.
CASTS="boot.cast build.cast grade.cast selftest.cast"
REC=0
for c in ${CASTS}; do
    if [ ! -s "${HERE}/clips/${c}" ]; then REC=1; fi
done
if [ "${REC}" -eq 1 ]; then
    command -v asciinema >/dev/null 2>&1 || {
        echo "make_media: asciinema not found (pip install --user asciinema)" >&2
        exit 3; }
    TC_DIR="${HOME}/.firmware-qemu-tools/arm-gnu-toolchain-13.3.rel1-x86_64-arm-none-eabi"
    if [ ! -x "${TC_DIR}/bin/arm-none-eabi-gcc" ] \
        && ! command -v arm-none-eabi-gcc >/dev/null 2>&1; then
        echo "make_media: Arm toolchain missing; run judge/setup.sh" >&2
        exit 3
    fi
    command -v qemu-system-arm >/dev/null 2>&1 || {
        echo "make_media: qemu-system-arm missing; run judge/setup.sh" >&2
        exit 3; }
    mkdir -p "${HERE}/clips"
    # boot needs the ELF the judge builds; build it with the pinned prefix.
    ELF="${DEMO}/examples/good/build/firmware.elf"
    if [ ! -x "${ELF}" ]; then
        if [ -d "${DEMO}/examples/good/.toolchain" ]; then
            CROSS="${DEMO}/examples/good/.toolchain/bin/arm-none-eabi-"
        else
            CROSS="${TC_DIR}/bin/arm-none-eabi-"
        fi
        ( cd "${DEMO}/examples/good" && make clean >/dev/null \
            && make "CROSS=${CROSS}" build/firmware.elf >/dev/null )
    fi
    for c in ${CASTS}; do
        phase="${c%.cast}"
        echo "make_media: recording ${phase} (real run)..."
        asciinema rec --overwrite --cols 120 --rows 50 \
            --command "python3 ${HERE}/record.py ${phase} ${HERE}/clips/${c}" \
            "${HERE}/clips/${c}" > /dev/null
    done
else
    echo "make_media: reusing existing casts in media/clips/"
fi

# 2. clips: the storyboard's windows of the casts, replayed at 30 fps.
"${PY}" "${HERE}/collect-media-deps.sh" 2>/dev/null || \
    bash "${HERE}/collect-media-deps.sh"
python3 "${HERE}/clips.py"

# 3. numbers: every HUD value from this run's judge output and casts.
#    hud_numbers.py, not numbers.py: a module called `numbers` on the
#    script path shadows the stdlib one and numpy fails to import.
python3 "${HERE}/hud_numbers.py"

# 4. render: HyperFrames headless (pinned in media/video/package.json,
#    node_modules not committed -> npm ci first).
( cd "${HERE}/video" \
    && [ -d node_modules ] || npm ci --no-audit --no-fund \
    && ./node_modules/.bin/hyperframes render . \
        --variables-file numbers.json \
        --output "${HERE}/master/demo.mp4" --quiet )

# 5. encode: ffmpeg re-encodes the rendered master to the web encode.
mkdir -p "${MASTER}"
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
