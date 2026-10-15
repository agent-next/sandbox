#!/usr/bin/env bash
# Rebuild every media artifact from real judge output.
#
#   judge runs        judge/mutants.py + judge/grade.sh once per artifact
#                     (seven verdicts) and the judge-guard check, into
#                     media/data/*.json -- nothing hand-edited or invented
#   result.png        media/make_figures.py
#   loop.png          media/make_figures.py
#   frames/           media/make_video.py (git-ignored)
#   master/           lossless H.264 master (git-ignored)
#   demo.mp4          web encode: -crf 18 -preset slow -pix_fmt yuv420p
#                     -movflags +faststart
#   MANIFEST.json     media/manifest.py (sha256 of every shipped file)
#
# Requires: judge/setup.sh already run (tesseract, DejaVu, Pillow) and
# ffmpeg on PATH.  Pillow is the only Python dependency and it is the
# pinned, sha256-checked one judge/setup.sh installs, so the figures need
# no extra environment.
#
# Takes ~15 min: the grading runs are the same ones judge/selftest.sh does.
#
#   bash media/make_media.sh              # grade + render + encode
#   bash media/make_media.sh --render-only  # re-render from media/data/

set -euo pipefail

MEDIA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "$MEDIA")"
SEED="${SEED:-42}"
PY="${PYTHON:-python3}"

die() { echo "make_media: $*" >&2; exit 1; }

command -v ffmpeg >/dev/null || die "ffmpeg missing (distro package)"
"$PY" -c 'import PIL, sys; sys.exit(0 if PIL.__version__ == "11.3.0" else 1)' \
    || die "Pillow 11.3.0 not importable -- run judge/setup.sh first"
[ -f /usr/share/fonts/truetype/dejavu/DejaVuSans.ttf ] \
    || die "DejaVu fonts missing -- run judge/setup.sh first"

RENDER_ONLY=0
[ "${1:-}" = "--render-only" ] && RENDER_ONLY=1

# the verdict JSONs land here; git-ignored, rebuilt on every run
mkdir -p "$MEDIA/data" 

# -- 1. real judge runs ------------------------------------------------------
if [ "$RENDER_ONLY" -eq 0 ]; then
    echo "== grading the known-good artifact (seed $SEED) =="
    bash "$DEMO/judge/grade.sh" "$DEMO/examples/good" --seed "$SEED" \
        --json "$MEDIA/data/good.json" >/dev/null || \
        die "the known-good artifact failed the judge"

    echo "== building and grading the mutants (seed $SEED) =="
    python3 "$DEMO/judge/mutants.py" --src "$DEMO/examples/good" \
        --out "$DEMO/examples/bad" >/dev/null
    for m in "$DEMO"/examples/bad/*/; do
        name="$(basename "$m")"
        rc=0
        bash "$DEMO/judge/grade.sh" "$m" --seed "$SEED" \
            --json "$MEDIA/data/$name.json" >/dev/null || rc=$?
        [ "$rc" -ne 0 ] || die "mutant $name PASSED the judge"
        echo "   killed $name"
    done

    echo "== judge-guard mutant =="
    # the same weakening selftest.sh applies: a fixed ink threshold that
    # cannot see ink on the low-contrast pages must fail the good artifact
    guard_dir="$(mktemp -d)"
    cp "$DEMO/judge/check_gates.py" "$DEMO/judge/corrupt.py" \
       "$DEMO/judge/fixtures.py" "$guard_dir/"
    "$PY" - "$DEMO/judge/check_gates.py" "$guard_dir/check_gates_weak.py" <<'PY'
import sys
src = open(sys.argv[1]).read()
old = """    hist = im.histogram()
    mode = max(range(len(hist)), key=lambda v: hist[v])
    return max(0, mode - 40)"""
assert src.count(old) == 1, "ink-threshold anchor not found"
open(sys.argv[2], "w").write(src.replace(old, "    return 128"))
PY
    rc=0
    "$PY" "$guard_dir/check_gates_weak.py" "$DEMO/examples/good" --seed "$SEED" \
        --json "$guard_dir/weak.json" >/dev/null || rc=$?
    rm -rf "$guard_dir"
    [ "$rc" -ne 0 ] || die "the weakened judge accepted the good artifact"
    "$PY" - "$rc" "$MEDIA/data/judge_guard.json" <<'PY'
import json, sys
json.dump({"killed": sys.argv[1] != "0",
           "check_gates": "ink threshold re-hardcoded to 128"},
          open(sys.argv[2], "w"), indent=2)
PY
    echo "   judge-guard killed"
fi

for f in good m01-total-as-float m03-box-on-whitespace m03b-whole-page-box \
         m04-quarantine-everything m05-wrong-date-format \
         m06-accept-bad-date judge_guard; do
    [ -f "$MEDIA/data/$f.json" ] || die "missing media/data/$f.json"
done

# -- 2. figures --------------------------------------------------------------
echo "== figures =="
"$PY" "$MEDIA/make_figures.py"

# -- 3. video ----------------------------------------------------------------
echo "== video frames =="
"$PY" "$MEDIA/make_video.py"

LIST="$MEDIA/frames/list.txt"
[ -s "$LIST" ] || die "no video frames produced"

mkdir -p "$MEDIA/master"
echo "== lossless master (crf 0) =="
ffmpeg -y -loglevel error -f concat -safe 0 -i "$LIST" \
    -r 30 -c:v libx264 -crf 0 -preset slow -pix_fmt yuv420p \
    "$MEDIA/master/demo-master.mp4" || die "master encode failed"

echo "== web encode demo.mp4 =="
ffmpeg -y -loglevel error -i "$MEDIA/master/demo-master.mp4" \
    -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p \
    -movflags +faststart -an "$MEDIA/demo.mp4" || die "web encode failed"

# the standard's hard limits, checked rather than assumed
bytes=$(stat -c%s "$MEDIA/demo.mp4")
[ "$bytes" -lt 8388608 ] || die "demo.mp4 is $bytes bytes (limit 8 MB)"
probe=$(ffprobe -v error -select_streams v:0 \
        -show_entries stream=width,height,nb_frames,r_frame_rate \
        -of csv=p=0 "$MEDIA/demo.mp4")
echo "   demo.mp4: $probe, $bytes bytes"
echo "$probe" | grep -q '^1920,1080,' || die "demo.mp4 is not 1920x1080"

# -- 4. manifest -------------------------------------------------------------
echo "== MANIFEST.json =="
"$PY" "$MEDIA/manifest.py"

echo "make_media: done -> $MEDIA/{result.png,loop.png,demo.mp4,MANIFEST.json}"