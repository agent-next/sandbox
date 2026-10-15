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
#
# Every judge invocation below runs from the demo root with repo-relative
# artifact paths, so a regenerated verdict names its artifact the same way
# as the committed ones (DEMO-STANDARD.md: no host paths in committed data).
set -euo pipefail

MEDIA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "$MEDIA")"
VENV="${GLACIER_VENV:-$HOME/glacier-venv}"
PY="$VENV/bin/python"

die() { echo "make_media: $*" >&2; exit 1; }

command -v ffmpeg >/dev/null || die "ffmpeg missing (distro package)"
[ -x "$PY" ] || die "$PY missing -- run judge/setup.sh first"

cd "$DEMO"

# --- judge outputs (committed; regenerate identically if absent) ----------
if [ ! -f media/data/verdicts/good.json ]; then
    echo "== verdicts missing -> grading good + mutants =="
    mkdir -p media/data/verdicts
    bash judge/grade.sh examples/good \
        --json media/data/verdicts/good.json >/dev/null
    rm -rf media/data/mutants
    python3 -I judge/mutants.py examples/good media/data/mutants >/dev/null
    for m in media/data/mutants/*/; do
        name="$(basename "$m")"
        bash judge/grade.sh "$m" \
            --json "media/data/verdicts/$name.json" >/dev/null 2>&1 || true
    done
fi

if [ ! -f media/data/loop/iter5.json ]; then
    echo "== agent-loop artifacts missing -> building + grading =="
    python3 -I media/make_loop_artifacts.py examples/good \
        media/data/loop >/dev/null
    for i in 1 2 3 4 5; do
        bash judge/grade.sh "media/data/loop/iter$i" \
            --json "media/data/loop/iter$i.json" >/dev/null 2>&1 || true
    done
fi

if [ ! -f media/data/run/good/volumes.csv ]; then
    echo "== good run outputs missing -> running the artifact =="
    mkdir -p media/data/run/good
    "$PY" -I examples/good/model.py --out media/data/run/good \
        --seed 20261015 >/dev/null
fi

# --- figures -------------------------------------------------------------
echo "== result.png =="
"$PY" -I media/fig_result.py .
echo "== loop.png =="
"$PY" -I media/fig_loop.py .

# --- video: frames -> lossless master -> H.264 web encode ----------------
echo "== demo.mp4 =="
rm -rf "$MEDIA/frames" "$MEDIA/master"
mkdir -p "$MEDIA/frames" "$MEDIA/master"
"$PY" -I media/make_frames.py . "$MEDIA/frames"
ffmpeg -y -loglevel error -framerate 30 -i "$MEDIA/frames/f%04d.png" \
    -c:v libx264 -crf 0 -preset veryslow -pix_fmt yuv420p \
    "$MEDIA/master/demo-master.mp4"
ffmpeg -y -loglevel error -i "$MEDIA/master/demo-master.mp4" \
    -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p \
    -movflags +faststart "$MEDIA/demo.mp4"
rm -rf "$MEDIA/frames"

# --- MANIFEST ------------------------------------------------------------
echo "== MANIFEST.json =="
"$PY" -I media/make_manifest.py .

echo "make_media: done"
