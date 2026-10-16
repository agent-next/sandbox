#!/usr/bin/env bash
# Regenerate every media file for the spice-filter demo from judge outputs.
#   media/result.png   Bode magnitude vs the spec mask, pass lines drawn
#   media/loop.png     agent-loop replay (failing gate per iteration until
#                      pass) + self-test kill-rate bars
#   media/clips/*.mp4  real 30 fps motion clips (PIL frames -> ffmpeg);
#                      gitignored — the Remotion project composes them
#   media/demo.mp4     Remotion cut of the clips + animated HUD overlays,
#                      from a lossless crf-0 master in media/master/
#   media/frames/      extracted check frames (committed, < 250 KB each)
#   media/MANIFEST.json  what each file shows, source data, sha256
# Pinned matplotlib wheels: judge/requirements.txt (installed with
# --require-hashes into a venv). ffmpeg: distro build. Renderer: Remotion
# 4.0.530 pinned exact in media/video/package-lock.json (Node >= 22,
# npm ci). Numbers on screen trace to media/data/*.json, which
# make_data.py writes from this run's own judge outputs.
set -euo pipefail

DEMO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MEDIA="$DEMO/media"
VENV="${MEDIA_VENV:-$MEDIA/.venv}"

mkdir -p "$MEDIA/master" "$MEDIA/data" "$MEDIA/clips" "$MEDIA/frames" \
    "$MEDIA/video/public/clips"

# --- pinned python environment for plotting/frame drawing -----------------
if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c \
       "import matplotlib, contourpy, numpy, PIL" >/dev/null 2>&1; then
    echo "media: creating venv, installing pinned wheels from judge/requirements.txt"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --no-cache-dir --require-hashes \
        -r "$DEMO/judge/requirements.txt" >/dev/null
fi
PY="$VENV/bin/python"
echo "media: $(python3 --version | awk '{print "python "$2}'), matplotlib $("$PY" -c 'import matplotlib;print(matplotlib.__version__)'), ffmpeg $(ffmpeg -version | awk 'NR==1{print $3}' | tr -d ')'), $(node --version | awk '{print "node "$1}')"

# --- source data: judge outputs only ------------------------------------
# The replay re-runs the judge on known-bad artifacts and the good one in
# the order a fixing agent would meet them (bad -> partly fixed -> good);
# it is a scripted replay, not a recorded live trace. The same block also
# captures the real terminal transcript shown in the term.mp4 clip.
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
python3 -I "$DEMO/judge/mutants.py" \
    "$DEMO/examples/good/lpf4sk.cir" "$work/mutants" >/dev/null
for m in r-decade-up off-series unrecognised-topology; do
    bash "$DEMO/judge/grade.sh" "$work/mutants/$m.cir" \
        --json "$work/$m.json" >/dev/null || true
done
{
    echo "$ bash judge/selftest.sh"
    (cd "$DEMO" && bash judge/selftest.sh)
    echo
    echo "$ bash judge/grade.sh examples/good/lpf4sk.cir --json good.json"
    (cd "$DEMO" && bash judge/grade.sh examples/good/lpf4sk.cir \
        --json "$work/good.json")
    echo
    echo "$ python3 -c 'import json; print(json.load(open(\"good.json\"))[\"passed\"])'"
    (cd "$work" && python3 -c \
        'import json; print(json.load(open("good.json"))["passed"])')
} > "$work/runlog.txt" 2>&1
echo "media: replay verdicts graded + terminal transcript captured (runlog.txt)"

"$PY" "$MEDIA/make_data.py" "$DEMO" "$work"

# --- figures -------------------------------------------------------------
"$PY" "$MEDIA/make_figures.py"

# --- motion clips: real sim output drawn frame-by-frame --------------------
echo "media: rendering 1080p30 motion clips (scope / bode / term / mc)"
"$PY" "$MEDIA/make_clips.py"
cp -f "$MEDIA"/clips/*.mp4 "$MEDIA/video/public/clips/"

# --- compose + render: Remotion headless -----------------------------------
echo "media: Remotion render (pinned $(cd "$MEDIA/video" && node -p 'require("./package.json").dependencies.remotion'))"
(cd "$MEDIA/video" \
    && npm ci --no-audit --no-fund \
    && npx remotion browser ensure \
    && rm -rf out/frames \
    && npx remotion render src/index.ts Demo out/frames --sequence \
        --props ../data/video_props.json)
# Remotion 4 refuses h264 CRF 0; the PNG sequence IS the lossless render
# and ffmpeg encodes it to the crf-0 master the standard asks for.
ffmpeg -y -loglevel error -framerate 30 \
    -i "$MEDIA/video/out/frames/element-%04d.png" \
    -c:v libx264 -crf 0 -preset veryfast -pix_fmt yuv444p \
    "$MEDIA/master/demo_master.mp4"

# --- web encode (ffmpeg encodes only; it draws nothing) --------------------
# CRF 18 with a VBV bound: the all-moving footage otherwise lands ~12 MB
# at CRF 18 alone; -maxrate/-bufsize caps the stream under the 8 MiB gate.
ffmpeg -y -loglevel error -i "$MEDIA/master/demo_master.mp4" \
    -c:v libx264 -crf 18 -maxrate 1.5M -bufsize 3M -preset slow \
    -pix_fmt yuv420p -movflags +faststart \
    "$MEDIA/demo.mp4"

# --- committed check frames ------------------------------------------------
dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 \
    "$MEDIA/demo.mp4")
for spec in "1.0:t01s" \
            "$(python3 -c "print(f'{$dur*0.25+0.2:.2f}')"):p25" \
            "$(python3 -c "print(f'{$dur*0.60:.2f}')"):p60" \
            "35.2:proof"; do
    t="${spec%%:*}"; name="${spec##*:}"
    ffmpeg -y -loglevel error -ss "$t" -i "$MEDIA/demo.mp4" \
        -frames:v 1 -q:v 4 "$MEDIA/frames/$name.jpg"
done

"$PY" "$MEDIA/make_manifest.py"

size=$(stat -c%s "$MEDIA/demo.mp4")
if [ "$size" -ge 8388608 ]; then
    echo "media: demo.mp4 is $size bytes >= 8 MB" >&2
    exit 1
fi
echo "media: demo.mp4 is $size bytes"
echo "media: done"
