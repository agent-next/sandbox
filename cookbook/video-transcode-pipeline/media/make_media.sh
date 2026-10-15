#!/usr/bin/env bash
# Regenerate every media file for the video-transcode-pipeline demo from the
# judge's own output. Nothing here is hand-edited.
#
#   media/result.png    the judge's measured gates with their pass lines
#   media/loop.png      the agent loop + self-test kill-rate bars
#   media/demo.mp4      30 s, 1920x1080, H.264, from a lossless crf-0 master
#                       in media/master/ (git-ignored)
#   media/data/*.json   the judge verdicts the figures are drawn from
#   media/MANIFEST.json what each file shows, the command, source data, sha256
#
# The plotting environment is pinned in judge/requirements.txt and installed
# with --require-hashes into media/.venv. ffmpeg and whisper-cli come from
# judge/setup.sh (run it first).
set -euo pipefail

DEMO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MEDIA="$DEMO/media"
VENV="${MEDIA_VENV:-$MEDIA/.venv}"

command -v ffmpeg > /dev/null || { echo "media: run judge/setup.sh first" >&2; exit 1; }
[ -x "${WHISPER_CLI:-$HOME/.vtp-tools/whisper-cli}" ] || {
    echo "media: run judge/setup.sh first (whisper-cli missing)" >&2; exit 1; }

mkdir -p "$MEDIA/data" "$MEDIA/master"

if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c "import matplotlib" \
        > /dev/null 2>&1; then
    echo "media: creating venv, installing pinned wheels from judge/requirements.txt"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --no-cache-dir --require-hashes \
        -r "$DEMO/judge/requirements.txt" > /dev/null
fi
PY="$VENV/bin/python"
echo "media: python $("$PY" -c 'import sys;print(".".join(map(str,sys.version_info[:3])))'), \
matplotlib $("$PY" -c 'import matplotlib;print(matplotlib.__version__)'), \
ffmpeg $(ffmpeg -version | awk 'NR==1{print $3}' | tr -d ')')"

# --- source data: real judge verdicts only -------------------------------
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
"$PY" "$MEDIA/make_data.py" "$DEMO" "$work"

# --- figures -------------------------------------------------------------
"$PY" "$MEDIA/make_figures.py"

# --- video ---------------------------------------------------------------
"$PY" "$MEDIA/make_video.py" "$DEMO" "$MEDIA/master"

# --- manifest ------------------------------------------------------------
"$PY" "$MEDIA/make_manifest.py"

echo "media: done"
