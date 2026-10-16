#!/usr/bin/env bash
# Regenerate every media file for the solidcraft-cad demo from real tool output.
#   media/data/          SolidCraft renders (git-ignored) + judge verdicts (JSON)
#   media/result.png     delivered part + every judge pass rule vs its limit
#   media/loop.png       the independent agent's 12 designs re-graded + self-test kills
#   media/clips/         the 3D footage the demo.mp4 is cut from (git-ignored)
#   media/demo.mp4       the story as 1080p30 video: clips -> HyperFrames -> encode
#   media/MANIFEST.json  what each file shows, its command and sha256
#
# The video is composed, not typeset: media/video/shots/*.html render the real
# geometry (the STEP SolidCraft produced, exported to glb) as moving footage,
# media/video/index.html composes those clips and adds the overlays, and
# ffmpeg only encodes. HyperFrames does all the drawing.
#
# Needs judge/setup.sh first (SolidCraft + the venv with the pinned OCP) and
# media/video's npm dependencies (npm --prefix media/video ci).
# ffmpeg: distro build, version recorded in MANIFEST.json.
set -euo pipefail

DEMO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MEDIA="$DEMO/media"
VIDEO="$MEDIA/video"
CLIPS="$MEDIA/clips"
PY="$HOME/.local/solidcraft-judge-venv/bin/python"
[ -x "$PY" ] || { echo "media: run judge/setup.sh first" >&2; exit 1; }
if ! command -v ffmpeg >/dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq ffmpeg
fi
if ! command -v npx >/dev/null; then
    echo "media: node/npx not on PATH (install Node >= 22)" >&2
    exit 1
fi

mkdir -p "$CLIPS"
work="$(mktemp -d)"

# 1. the geometry the video shows: exports of the STEP files this run wrote.
#    Thickness 6 mm is the graded build; stage11/15/16 are make_media.py's
#    build-stage snapshots of the same design script.
"$PY" "$VIDEO/export_glb.py" "$MEDIA/data/renders/part.step" "$VIDEO/assets/part.glb"
for n in 11 15 16; do
    "$PY" "$VIDEO/export_glb.py" "$MEDIA/data/renders/stage${n}.step" "$VIDEO/assets/stage${n}.glb"
done
for t in 6.0 6.5 7.0 7.5 8.0; do
    "$PY" "$VIDEO/export_glb.py" "$MEDIA/data/renders/sweep_${t}.step" "$VIDEO/assets/sweep${t}.glb"
done

# 2. the numbers on screen, straight from this run's judge output.
"$PY" "$VIDEO/build_overlay_data.py"

# 3. the moving footage: one HyperFrames render per shot. This is the slow
#    step (software GPU, one Chrome per shot); each clip is written to
#    media/clips/, which is git-ignored.
for shot in f1_turn f2_stages f3_plate f4_explode f5_section f6_run f7_sweep; do
    (
        cd "$VIDEO"
        npx hyperframes render -c "shots/${shot}.html" -o "$CLIPS/${shot}.mp4" \
            --no-browser-gpu --crf 16
    )
done

# 4. compose: HyperFrames layers the overlays over those clips and renders the
#    timeline, still the only component that draws anything.
(
    cd "$VIDEO"
    npx hyperframes render -o "$CLIPS/demo_composed.mp4" --no-browser-gpu --crf 16
)

# 5. encode: H.264 yuv420p, CRF 18, +faststart. ffmpeg builds no visuals here.
ffmpeg -y -loglevel error -i "$CLIPS/demo_composed.mp4" \
    -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p -movflags +faststart \
    -an "$MEDIA/demo.mp4"

# 6. figures + manifest, unchanged from before.
"$PY" "$MEDIA/make_media.py" figures
"$PY" "$MEDIA/make_media.py" manifest

size=$(stat -c%s "$MEDIA/demo.mp4")
if [ "$size" -ge 8388608 ]; then
    echo "media: demo.mp4 is $size bytes >= 8 MB" >&2
    exit 1
fi
echo "media: demo.mp4 is $size bytes"
echo "media: done"
