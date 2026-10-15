#!/usr/bin/env bash
# Regenerate every media file for the background-coding-agent demo from
# judge outputs.
#   media/result.png   oracle vs the 1e-9 pass line, measured summary,
#                      tests collected vs required minimums
#   media/loop.png     agent-loop replay (failing gate per iteration
#                      until pass) + self-test kill-rate bars
#   media/demo.mp4     captioned step-through of the same (from a
#                      lossless crf-0 master in media/master/, git-ignored)
#   media/MANIFEST.json  what each file shows, source data, sha256
# Pinned matplotlib wheels: media/requirements.txt (installed with
# --require-hashes into media/.venv). ffmpeg: distro build, version
# recorded in MANIFEST.json.
set -euo pipefail

DEMO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MEDIA="$DEMO/media"
VENV="${MEDIA_VENV:-$MEDIA/.venv}"

mkdir -p "$MEDIA/master" "$MEDIA/data"

# --- pinned python environment for plotting ------------------------------
if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c \
       "import matplotlib" >/dev/null 2>&1; then
    echo "media: creating venv, installing pinned wheels from media/requirements.txt"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --no-cache-dir --require-hashes \
        -r "$MEDIA/requirements.txt" >/dev/null
fi
PY="$VENV/bin/python"
echo "media: $(python3 --version | awk '{print "python "$2}'), matplotlib $("$PY" -c 'import matplotlib;print(matplotlib.__version__)'), ffmpeg $(ffmpeg -version | awk 'NR==1{print $3}' | tr -d ')')"

# --- source data: judge outputs only ------------------------------------
# The replay re-runs the judge on known-bad artifacts and the good one in
# the order a fixing agent would meet them (one per gate, in judge order);
# it is a scripted replay, not a recorded live trace.
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
python3 -I "$DEMO/judge/mutants.py" \
    "$DEMO/examples/good/delivery.patch" "$DEMO/examples/good/PR.md" \
    "$work/mutants" >/dev/null
replay_sequence="empty-patch touches-tests breaks-old-test json-missing-field lint-unused-import mean-sign-dropped pr-no-test-plan"
for m in $replay_sequence; do
    bash "$DEMO/judge/grade.sh" "$work/mutants/$m/delivery.patch" \
        --pr "$work/mutants/$m/PR.md" --json "$work/$m.json" >/dev/null || true
done
for m in "$work"/mutants/*/; do
    name="$(basename "$m")"
    [ -f "$work/$name.json" ] || bash "$DEMO/judge/grade.sh" \
        "$m/delivery.patch" --pr "$m/PR.md" \
        --json "$work/$name.json" >/dev/null || true
done
bash "$DEMO/judge/grade.sh" "$DEMO/examples/good/delivery.patch" \
    --pr "$DEMO/examples/good/PR.md" --json "$work/good.json" >/dev/null
echo "media: replay + self-test verdicts graded (7 mutants + 11 total + good)"

python3 -I "$MEDIA/make_data.py" "$DEMO" "$work"

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
rm -rf "$frames"

"$PY" "$MEDIA/make_manifest.py"

size=$(stat -c%s "$MEDIA/demo.mp4")
if [ "$size" -ge 5242880 ]; then
    echo "media: demo.mp4 is $size bytes >= 5 MB" >&2
    exit 1
fi
echo "media: demo.mp4 is $size bytes"
echo "media: done"
