#!/bin/sh
# Regenerate every media file from real judge outputs. See DEMO-STANDARD.md.
#
#   media/make_media.sh ARTIFACTS_DIR
#
# ARTIFACTS_DIR is what `run.py --artifacts DIR` wrote: verdict.json (the
# judge's verdict for the known-good runner) and selftest.log (the mutant
# kill list and kill rate). Nothing here is hand-edited or illustrative:
# every plotted number is read from those two files and judge/policy.json.
#
# Needs python3 + matplotlib (figures) and ffmpeg (video). Both are
# generation-time tools; the demo's judge and run.py are stdlib-only.
#
# Outputs: result.png, loop.png, demo.mp4, MANIFEST.json (all git-tracked),
# and master/ (the lossless frame sequence, gitignored).

set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
ARTIFACTS=${1:-}
if [ -z "$ARTIFACTS" ] || [ ! -f "$ARTIFACTS/verdict.json" ]; then
    echo "usage: media/make_media.sh ARTIFACTS_DIR   (run.py --artifacts DIR)" >&2
    echo "  need ARTIFACTS_DIR/verdict.json and ARTIFACTS_DIR/selftest.log" >&2
    exit 2
fi
if [ ! -f "$ARTIFACTS/selftest.log" ]; then
    echo "make_media.sh: $ARTIFACTS/selftest.log missing" >&2
    exit 2
fi
for tool in python3 ffmpeg; do
    command -v "$tool" >/dev/null 2>&1 || {
        echo "make_media.sh: $tool not found" >&2; exit 3; }
done

echo "make_media.sh: drawing result.png and loop.png"
python3 "$HERE/figures.py" "$ARTIFACTS" stills

echo "make_media.sh: rendering lossless frames into media/master/"
rm -rf "$HERE/master"
python3 "$HERE/figures.py" "$ARTIFACTS" frames

echo "make_media.sh: encoding demo.mp4 (H.264, web)"
ffmpeg -y -loglevel error -framerate 30 -i "$HERE/master/frame_%06d.png" \
    -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p -movflags +faststart \
    -vf scale=1920:1080 "$HERE/demo.mp4"

echo "make_media.sh: writing MANIFEST.json"
python3 "$HERE/figures.py" "$ARTIFACTS" manifest

echo "make_media.sh: ok"
ls -l "$HERE/result.png" "$HERE/loop.png" "$HERE/demo.mp4" \
    "$HERE/MANIFEST.json"
