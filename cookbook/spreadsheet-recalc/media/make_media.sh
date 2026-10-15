#!/usr/bin/env bash
# Regenerate every file in media/ from real judge outputs.
# Run from any directory. Scratch, caches and toolchains stay in media/.
#
# Requires: python3, ffmpeg; network access on the first run (pinned venvs,
# sha256-checked). The judge directory is copied and run from the copy so
# media regeneration cannot rewrite the committed VERSIONS.txt.
set -euo pipefail

MEDIA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "$MEDIA")"

for tool in python3 ffmpeg; do
    command -v "$tool" >/dev/null || { echo "make_media: missing $tool" >&2; exit 1; }
done

mkdir -p "$MEDIA/work" "$MEDIA/data" "$MEDIA/master" "$MEDIA/.tools"
WORK="$(mktemp -d "$MEDIA/work/run.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
export TMPDIR="$WORK"

# setup.sh writes VERSIONS.txt; use an unchanged copy of the entire judge so
# media regeneration cannot rewrite the committed toolchain receipt.
# The judge resolves examples/ relative to its own directory
# (judge/../examples/good), so replicate the demo layout in $WORK.
cp -R "$DEMO/judge" "$WORK/judge"
mkdir -p "$WORK/examples/good"
cp "$DEMO/examples/good/dcf_model.xlsx" "$WORK/examples/good/"
export HOME="$MEDIA/.tools"

echo "== pinned judge setup (copy) =="
bash "$WORK/judge/setup.sh"
JUDGE_PY="$HOME/.venvs/spreadsheet-recalc/bin/python"

echo "== real selftest =="
bash "$WORK/judge/selftest.sh" | tee "$WORK/selftest.txt"

echo "== grade known-good: same full-run path as run.py, seed 0 =="
GOOD="$WORK/examples/good/dcf_model.xlsx"
bash "$WORK/judge/grade.sh" "$GOOD" \
    --seed 0 --json "$WORK/grade.json" > /dev/null

echo "== collect compact evidence =="
"$JUDGE_PY" "$MEDIA/collect.py" "$WORK" "$MEDIA/data"

echo "== rendering venv (hash-pinned) =="
RENDER_PY="$MEDIA/.venv/bin/python"
if [ ! -x "$RENDER_PY" ] || ! "$RENDER_PY" -c "import matplotlib, numpy" 2>/dev/null; then
    python3 -m venv "$MEDIA/.venv"
    "$MEDIA/.venv/bin/pip" install --quiet --disable-pip-version-check \
        --require-hashes -r "$MEDIA/requirements.lock"
fi

echo "== figures and lossless master =="
export MPLBACKEND=Agg MPLCONFIGDIR="$HOME/matplotlib"
export PYTHONHASHSEED=0 SOURCE_DATE_EPOCH=1791936000
"$RENDER_PY" "$MEDIA/render.py" "$WORK/frames"

echo "== H.264 web encode from the crf 0 master =="
# render.py writes unique frames at 10 fps; duplicate to the standard's
# 30 fps output.
ffmpeg -y -v error -threads 2 -framerate 10 -i "$WORK/frames/f%04d.png" \
    -r 30 -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p \
    -movflags +faststart -map_metadata -1 -an "$MEDIA/demo.mp4"
ffmpeg -y -v error -threads 2 -framerate 10 -i "$WORK/frames/f%04d.png" \
    -r 30 -c:v libx264 -crf 0 -preset slow -pix_fmt yuv420p -movflags +faststart \
    -map_metadata -1 -an "$MEDIA/master/demo_master.mp4"

echo "== manifest =="
"$RENDER_PY" "$MEDIA/manifest.py"

ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate,pix_fmt \
    -show_entries format=duration,size -of default=noprint_wrappers=1 \
    "$MEDIA/demo.mp4"
echo "make_media: done"
