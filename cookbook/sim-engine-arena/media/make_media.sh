#!/usr/bin/env bash
# Run from any directory. All scratch, caches and toolchains stay in media/.
set -euo pipefail
MEDIA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "$MEDIA")"
for tool in python3 ffmpeg ffprobe; do
    command -v "$tool" >/dev/null || { echo "Missing $tool" >&2; exit 1; }
done
mkdir -p "$MEDIA/work" "$MEDIA/data" "$MEDIA/master" "$MEDIA/.tools"
WORK="$(mktemp -d "$MEDIA/work/run.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
export TMPDIR="$WORK"
# setup.sh writes VERSIONS.txt; use an unchanged copy of the entire judge so
# media regeneration cannot rewrite the committed toolchain receipt.
cp -R "$DEMO/judge" "$WORK/judge"
mkdir -p "$WORK/examples/good"
cp "$DEMO/examples/good/sim.py" "$WORK/examples/good/"
export HOME="$MEDIA/.tools"
export MPLBACKEND=Agg MPLCONFIGDIR="$HOME/matplotlib"
export PYTHONHASHSEED=0 SOURCE_DATE_EPOCH=1791936000
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
echo "== pinned CPU judge setup =="
bash "$WORK/judge/setup.sh"
cp "$WORK/judge/VERSIONS.txt" "$MEDIA/data/versions.txt"
echo "== real selftest =="
bash "$WORK/judge/selftest.sh" | tee "$MEDIA/data/selftest.txt"
echo "== grade: same full-run path as run.py, seed 0 =="
bash "$WORK/judge/grade.sh" "$DEMO/examples/good/sim.py" \
    --seed 0 --json "$WORK/grade.json" > /dev/null
# The judge deletes its private trajectories. Re-run the SAME good artifact,
# then assert every CSV-derived oracle metric equals the full grade above.
mkdir "$WORK/trajectories"
cp "$DEMO/examples/good/sim.py" "$DEMO/judge/spec.json" "$WORK/trajectories/"
(cd "$WORK/trajectories" && "$HOME/.venvs/sim-engine-arena/bin/python" sim.py)
python3 "$MEDIA/collect.py" "$WORK" "$MEDIA/data"

PY="$MEDIA/.venv/bin/python"
if [ ! -x "$PY" ]; then
    python3 -m venv "$MEDIA/.venv"
fi
"$PY" -m pip install --quiet --disable-pip-version-check -r "$MEDIA/requirements.txt"
echo "== figures and lossless master =="
"$PY" "$MEDIA/render.py"
echo "== H.264 web encode from crf 0 master =="
ffmpeg -y -v error -threads 2 -i "$MEDIA/master/demo.mp4" \
    -c:v libx264 -threads 2 -crf 18 -preset slow -pix_fmt yuv420p \
    -movflags +faststart -map_metadata -1 -an "$MEDIA/demo.mp4"
"$PY" "$MEDIA/manifest.py"
ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate,pix_fmt \
    -show_entries format=duration,size -of default=noprint_wrappers=1 "$MEDIA/demo.mp4"
echo "make_media: done"
