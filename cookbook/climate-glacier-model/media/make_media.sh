#!/usr/bin/env bash
# Rebuild every media artifact for cookbook/climate-glacier-model from the
# real judge outputs.  Nothing here is hand-edited; run it and diff.
#
#   data/verdicts/*.json   committed judge outputs: the good artifact and
#                          one per mutant (grade.sh --seed 20261015)
#   data/loop/iter*/       committed artifacts + verdicts for the agent loop
#   data/run/good/         the good artifact's own outputs (volumes.csv ...)
#   result.png loop.png    matplotlib figures
#   demo.mp4               frames -> lossless master -> H.264 web encode
#   MANIFEST.json          sha256 + provenance for each file
#
# Requires: judge/setup.sh already run (the venv under $HOME holds numpy +
# matplotlib) and ffmpeg on PATH.  No pinned deps beyond those.
set -euo pipefail

MEDIA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "$MEDIA")"
VENV="${GLACIER_VENV:-$HOME/glacier-venv}"
PY="$VENV/bin/python"

die() { echo "make_media: $*" >&2; exit 1; }

command -v ffmpeg >/dev/null || die "ffmpeg missing (distro package)"
[ -x "$PY" ] || die "$PY missing -- run judge/setup.sh first"

# --- judge outputs (regenerate if absent; they are committed) ------------
if [ ! -f "$MEDIA/data/verdicts/good.json" ]; then
    echo "== verdicts missing -> grading good + mutants =="
    mkdir -p "$MEDIA/data/verdicts"
    bash "$DEMO/judge/grade.sh" "$DEMO/examples/good" \
        --json "$MEDIA/data/verdicts/good.json" >/dev/null
    rm -rf "$MEDIA/data/mutants"
    python3 -I "$DEMO/judge/mutants.py" "$DEMO/examples/good" \
        "$MEDIA/data/mutants" >/dev/null
    for m in "$MEDIA"/data/mutants/*/; do
        name="$(basename "$m")"
        bash "$DEMO/judge/grade.sh" "$m" \
            --json "$MEDIA/data/verdicts/$name.json" >/dev/null 2>&1 || true
    done
fi

if [ ! -f "$MEDIA/data/loop/iter5.json" ]; then
    echo "== agent-loop artifacts missing -> building + grading =="
    python3 -I "$MEDIA/make_loop_artifacts.py" "$DEMO/examples/good" \
        "$MEDIA/data/loop" >/dev/null
    for i in 1 2 3 4 5; do
        bash "$DEMO/judge/grade.sh" "$MEDIA/data/loop/iter$i" \
            --json "$MEDIA/data/loop/iter$i.json" >/dev/null 2>&1 || true
    done
fi

if [ ! -f "$MEDIA/data/run/good/volumes.csv" ]; then
    echo "== good run outputs missing -> running the artifact =="
    mkdir -p "$MEDIA/data/run/good"
    "$PY" -I "$DEMO/examples/good/model.py" --out "$MEDIA/data/run/good" \
        --seed 20261015 >/dev/null
fi

# --- figures -------------------------------------------------------------
echo "== result.png =="
"$PY" -I "$MEDIA/fig_result.py" "$DEMO"
echo "== loop.png =="
"$PY" -I "$MEDIA/fig_loop.py" "$DEMO"

# --- video: frames -> lossless master -> H.264 web encode ----------------
echo "== demo.mp4 =="
rm -rf "$MEDIA/frames" "$MEDIA/master"
mkdir -p "$MEDIA/frames" "$MEDIA/master"
"$PY" -I "$MEDIA/make_frames.py" "$DEMO" "$MEDIA/frames"
ffmpeg -y -loglevel error -framerate 30 -i "$MEDIA/frames/f%04d.png" \
    -c:v libx264 -crf 0 -preset veryslow -pix_fmt yuv420p \
    "$MEDIA/master/demo-master.mp4"
ffmpeg -y -loglevel error -i "$MEDIA/master/demo-master.mp4" \
    -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p \
    -movflags +faststart "$MEDIA/demo.mp4"
rm -rf "$MEDIA/frames"

# --- MANIFEST ------------------------------------------------------------
echo "== MANIFEST.json =="
"$PY" -I "$MEDIA/make_manifest.py" "$DEMO"

echo "make_media: done"
