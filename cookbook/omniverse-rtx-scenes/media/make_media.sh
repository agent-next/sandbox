#!/usr/bin/env bash
# media/make_media.sh — regenerate EVERY shipped media file from one
# run.py output directory.  Nothing here is hand-edited afterwards; run it
# again with the same <run_dir> and you get the same bytes (ffmpeg x264 is
# deterministic for a fixed version + preset + thread count).
#
# Usage:
#   bash media/make_media.sh <run_dir>      # e.g. out/run-20261016T...
#
# Produces (in this directory):
#   result.png     the judge figure (hero frame + G1/G2/G3 bars + timings)
#   loop.png       mutant kill matrix + per-scene IoU
#   demo.mp4       web encode (<= 8 MB, crf 18+, yuv420p, faststart)
#   master/master.mp4   lossless CRF-0 master (gitignored)
#   MANIFEST.json  sha256 + provenance for each shipped file
#
# Requires: python3 (numpy, matplotlib, Pillow), ffmpeg + ffprobe on PATH.
# The run dir must contain frames/, hero.png, <scene>.mp4, verdict.json,
# run-receipt.json, run.log, selftest.txt — i.e. it is a real run.py --out
# directory, not a stub.

set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <run_dir>" >&2
    exit 2
fi
RUN_DIR="$(cd "$1" && pwd)"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

for f in verdict.json run-receipt.json run.log hero.png; do
    if [[ ! -f "$RUN_DIR/$f" ]]; then
        echo "make_media: $RUN_DIR/$f missing — pass a real run.py --out dir" >&2
        exit 2
    fi
done
for s in warehouse physics arm; do
    if [[ ! -f "$RUN_DIR/$s.mp4" ]]; then
        echo "make_media: $RUN_DIR/$s.mp4 missing (the render clips)" >&2
        exit 2
    fi
done
command -v ffmpeg >/dev/null || { echo "make_media: ffmpeg not on PATH" >&2; exit 2; }
command -v ffprobe >/dev/null || { echo "make_media: ffprobe not on PATH" >&2; exit 2; }

echo "== figures"
python3 "$HERE/make_figures.py" "$RUN_DIR"

echo "== video"
python3 "$HERE/make_video.py" "$RUN_DIR"

echo "== gate"
GATE_RC=0
python3 "$(cd "$HERE/../.." && pwd)/tools/video_gate.py" "$HERE/demo.mp4" \
    || GATE_RC=$?

echo "== manifest"
python3 "$HERE/make_manifest.py"

if [[ $GATE_RC -ne 0 ]]; then
    echo "make_media: video GATE FAILED — demo not shippable (see above)" >&2
    exit "$GATE_RC"
fi
echo "make_media: done (result.png, loop.png, demo.mp4, MANIFEST.json)"
