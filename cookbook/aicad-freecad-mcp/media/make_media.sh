#!/usr/bin/env bash
# Rebuild every media artifact for the aicad-freecad-mcp demo.
#
#   data/*.json     committed judge verdicts (grade.sh --json) -- inputs,
#                   never regenerated here; see RECEIPT.md for the commands
#   result.png      real mesh renders + the judge's gate ledger
#   loop.png        known-good + mutant x gate matrix, kill rate
#   demo.mp4        frames rendered from the real meshes -> H.264 web encode
#
# Requires: judge/setup.sh run once for the mesh inputs (examples/good/), a
# distro ffmpeg on PATH, and libosmesa6 for pyrender's software GL backend.
# Python deps are pinned in media/requirements.txt and installed into
# media/.venv (git-ignored), on top of judge/requirements.txt.
set -euo pipefail

MEDIA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "$MEDIA")"
PY="$MEDIA/.venv/bin/python"

TURN_SECONDS="${TURN_SECONDS:-4}"      # turntable per part (3 parts)
PAN_SECONDS="${PAN_SECONDS:-4}"        # held on each pan window of a figure
CHAPTER_SECONDS="${CHAPTER_SECONDS:-1}"  # light chapter card between sections
END_SECONDS="${END_SECONDS:-6}"        # static end card

die() { echo "make_media: $*" >&2; exit 1; }

command -v ffmpeg >/dev/null || die "ffmpeg missing (apt install ffmpeg)"

if [ ! -x "$PY" ]; then
    echo "== create media/.venv with pinned deps =="
    python3 -m venv "$MEDIA/.venv"
    "$PY" -m pip install -q --upgrade pip
    # only the render/figure stack: the media tools read the judge's
    # verdict JSONs and constants, they never import cadquery/OCP
    "$PY" -m pip install -q -r "$MEDIA/requirements.txt"
fi

for part in bushing plate bracket; do
    [ -f "$DEMO/examples/good/$part/$part.stl" ] \
        || die "examples/good/$part/$part.stl missing -- run judge/setup.sh"
done
for v in good_bushing good_plate good_bracket; do
    [ -f "$MEDIA/data/$v.json" ] || die "media/data/$v.json missing"
done

echo "== result.png =="
"$PY" "$MEDIA/tools/fig_result.py"
echo "== loop.png =="
"$PY" "$MEDIA/tools/fig_loop.py"

echo "== frames (real mesh renders, cards, end card) =="
"$PY" "$MEDIA/tools/make_frames.py" \
    --turn-seconds "$TURN_SECONDS" --pan-seconds "$PAN_SECONDS" \
    --chapter-seconds "$CHAPTER_SECONDS" --end-seconds "$END_SECONDS"

MASTER="$MEDIA/master"
frames="$MASTER/frames"
count=$(find "$frames" -name 'frame_*.png' | wc -l)
[ "$count" -gt 0 ] || die "no frames were written"

echo "== lossless master ($count frames) =="
# The master is the full-rate lossless sequence; it is git-ignored. It is
# cut with the same -g as the web encode so the two share keyframes.
ffmpeg -y -loglevel error -framerate 30 -i "$frames/frame_%05d.png" \
    -c:v libx264 -crf 0 -preset veryfast -pix_fmt yuv420p -g 30 \
    "$MASTER/demo-master.mp4"

echo "== web encode =="
ffmpeg -y -loglevel error -i "$MASTER/demo-master.mp4" \
    -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p -g 30 \
    -movflags +faststart "$MEDIA/demo.mp4"

ls -l "$MEDIA/result.png" "$MEDIA/loop.png" "$MEDIA/demo.mp4"

echo "== check the video against the standard =="
# cookbook/tools/video_gate.py is on main, not on every branch; fetch it
# if this tree does not have it yet
GATE="$DEMO/../tools/video_gate.py"
if [ ! -f "$GATE" ]; then
    git -C "$DEMO/../.." show origin/main:cookbook/tools/video_gate.py \
        > "$GATE" 2>/dev/null || die "cannot find cookbook/tools/video_gate.py"
fi
python3 "$GATE" "$MEDIA/demo.mp4"
