#!/usr/bin/env bash
# Regenerate every media file for the backtest-equity demo from judge outputs.
#
#   media/data/*.json    the judge's own blind reference series, the
#                        known-bad mutant verdicts, the replay
#   media/result.png     equity vs the reference oracle + drawdown/position
#   media/loop.png       agent-loop deviation per attempt + kill rates
#   media/demo.mp4       the same, animated (lossless crf 0 master in
#                        media/master/, git-ignored, then crf 18 web encode)
#   media/MANIFEST.json  what each file shows, source data, sha256
#
# Pinned wheels: judge/requirements.txt, installed with --require-hashes
# into media/.venv.  ffmpeg: the sandbox's distro build (version recorded in
# MANIFEST.json).
set -euo pipefail

DEMO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MEDIA="$DEMO/media"
VENV="${MEDIA_VENV:-$MEDIA/.venv}"

mkdir -p "$MEDIA/master" "$MEDIA/data"

# --- pinned python environment for plotting ------------------------------
if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c \
       "import matplotlib, numpy" >/dev/null 2>&1; then
    echo "media: creating venv, installing pinned wheels from judge/requirements.txt"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --no-cache-dir --require-hashes \
        -r "$DEMO/judge/requirements.txt" >/dev/null
fi
PY="$VENV/bin/python"
echo "media: $(python3 --version | awk '{print "python "$2}'), matplotlib $("$PY" -c 'import matplotlib;print(matplotlib.__version__)'), ffmpeg $(ffmpeg -version | awk 'NR==1{print $3}')"

# --- source data: judge outputs only -------------------------------------
# Grade the good artifact and every known-bad mutant into a scratch dir,
# then let make_data.py read those verdicts; nothing is hand-written.
work="$(mktemp -d)"
trap 'rm -rf "$work" "$frames"' EXIT
frames="$(mktemp -d)"

SEED=42
bash "$DEMO/judge/grade.sh" "$DEMO/examples/good" --seed "$SEED" \
    --json "$work/good.json" >/dev/null
python3 "$DEMO/judge/mutants.py" "$work/mutants" >/dev/null
while read -r name; do
    [ -n "$name" ] || continue
    bash "$DEMO/judge/grade.sh" "$work/mutants/$name" --seed "$SEED" \
        --json "$work/$name.json" >/dev/null || true
done < <(ls "$work/mutants")
echo "media: graded the good artifact and $(ls "$work/mutants" | wc -l) mutants"

export PYTHONDONTWRITEBYTECODE=1
"$PY" "$MEDIA/make_data.py" "$DEMO" "$work"

# --- figures -------------------------------------------------------------
"$PY" "$MEDIA/make_figures.py"

# --- video: lossless master, then the web encode -------------------------
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
