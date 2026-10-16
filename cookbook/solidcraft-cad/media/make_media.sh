#!/usr/bin/env bash
# Regenerate every media file for the solidcraft-cad demo from real tool output.
#   media/data/          SolidCraft renders + judge verdicts (JSON)
#   media/result.png     delivered part + every judge pass rule vs its limit
#   media/loop.png       the independent agent's 12 designs re-graded + self-test kills
#   media/clips/         the moving 3D footage the demo.mp4 is cut from (git-ignored)
#   media/frames/         four stills from the finished video: one per act
#   media/demo.mp4       the story as 1080p30 video: clips -> HyperFrames -> encode
#   media/MANIFEST.json  what each file shows, its command and sha256
#
# The video is composed, not typeset: media/video/shots/*.html render the real
# geometry (the STEP SolidCraft produced, exported to glb) as moving footage,
# media/video/index.html composes those clips and adds the overlays, and ffmpeg
# only encodes. HyperFrames does all the drawing.
#
# Needs judge/setup.sh first (SolidCraft + the venv with the pinned OCP) and
# media/video's npm dependencies (npm --prefix media/video ci). The pinned
# HyperFrames is 0.8.99 (package-lock.json); it publishes >= 14 days before this
# video was cut, and it needs Node >= 22 and a headless Chrome it can drive.
# ffmpeg: distro build, version recorded in MANIFEST.json.
set -euo pipefail

DEMO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MEDIA="$DEMO/media"
VIDEO="$MEDIA/video"
CLIPS="$MEDIA/clips"
HF="$VIDEO/node_modules/.bin/hyperframes"
PY="$HOME/.local/solidcraft-judge-venv/bin/python"
WORK="${TMPDIR:-/tmp}/solidcraft-media"

[ -x "$PY" ] || { echo "media: run judge/setup.sh first" >&2; exit 1; }
if ! command -v ffmpeg >/dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq ffmpeg
fi
if ! command -v node >/dev/null; then
    echo "media: node not on PATH (install Node >= 22)" >&2
    exit 1
fi
node_major="$(node -p 'process.versions.node.split(".")[0]')"
if [ "$node_major" -lt 22 ]; then
    echo "media: Node >= 22 required (got $(node --version))" >&2
    exit 1
fi
# The renderer must come from the pinned install, never from an npx download.
if [ ! -x "$HF" ]; then
    echo "media: $HF missing; run: npm --prefix media/video ci" >&2
    exit 1
fi

mkdir -p "$CLIPS" "$WORK"
# SolidCraft is not on PATH after judge/setup.sh (README says so).
export PATH="$HOME/.local/solidcraft-0.10.1-linux-x86_64/bin:$PATH"

# 1. the geometry the video shows: the graded design and its real build stages
#    and parametric rebuilds, run by SolidCraft exactly as the judge runs them
#    and meshed by OpenCascade into the .glb the shots load.
"$PY" "$VIDEO/export_glb.py"

# 2. the numbers on screen, straight from this run's judge output. The stamped
#    selftest log is what the "Nx speed" run clip replays, so it is written here
#    if it is missing (a run of judge/selftest.sh, ~4-13 min depending on host).
SELFTEST="$MEDIA/data/selftest.stamped.log"
if [ ! -f "$SELFTEST" ]; then
    echo "media: stamping judge/selftest.sh into $SELFTEST"
    start="$(date +%s.%N)"
    bash "$DEMO/judge/selftest.sh" > >(
        while IFS= read -r line; do
            printf '%s\t%s\n' \
                "$($PY -c 'import sys;print(round(float(sys.argv[1])-float(sys.argv[2]),2))' \
                        "$(date +%s.%N)" "$start")" "$line"
        done > "$SELFTEST"
    )
fi
"$PY" "$VIDEO/build_overlay_data.py"
"$PY" "$VIDEO/build_overlay_data.py" --check

# 3. the moving footage: one HyperFrames render per shot. This is the slow
#    step (software GPU, one Chrome per shot); each clip is written to
#    media/clips/, which is git-ignored.
for shot in f1_turn f2_stages f3_plate f4_explode f5_section f6_run f7_sweep; do
    (
        cd "$VIDEO"
        "$HF" render -c "shots/${shot}.html" -o "$CLIPS/${shot}.mp4" \
            --no-browser-gpu --crf 16 --quiet
    )
done

# 4. compose: HyperFrames layers the overlays over those clips and renders the
#    timeline, still the only component that draws anything.
(
    cd "$VIDEO"
    "$HF" render -o "$CLIPS/demo_composed.mp4" --no-browser-gpu --crf 16 --quiet
)

# 5. encode: H.264 yuv420p, CRF 18, +faststart. ffmpeg builds no visuals here.
ffmpeg -y -loglevel error -i "$CLIPS/demo_composed.mp4" \
    -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p -movflags +faststart \
    -an "$MEDIA/demo.mp4"

# 6. figures + manifest, unchanged from before.
"$PY" "$MEDIA/make_media.py" figures
"$PY" "$MEDIA/make_media.py" manifest

# 7. the four stills in media/frames/: one from each act of the story, taken
#    from the finished demo.mp4 so they show the composited result. Times are
#    seconds into the video: the hook, input->output, the escalating run, and
#    the settled proof badge (after the HUD has finished counting up).
#    ffmpeg only decodes and scales here.
for frame in "01_hook 1.0" "02_input_to_output 9.75" "03_escalate_run 23.4" \
             "04_proof 36.2"; do
    set -- $frame
    ffmpeg -y -loglevel error -ss "$2" -i "$MEDIA/demo.mp4" -frames:v 1 \
        -vf "scale=1280:-2" -q:v 3 "$MEDIA/frames/$1.jpg"
done

size=$(stat -c%s "$MEDIA/demo.mp4")
if [ "$size" -ge 8388608 ]; then
    echo "media: demo.mp4 is $size bytes >= 8 MB" >&2
    exit 1
fi
for jpg in "$MEDIA"/frames/*.jpg; do
    jsize=$(stat -c%s "$jpg")
    if [ "$jsize" -ge 262144 ]; then
        echo "media: $jpg is $jsize bytes >= 250 KB" >&2
        exit 1
    fi
done
echo "media: demo.mp4 is $size bytes"
echo "media: done"
