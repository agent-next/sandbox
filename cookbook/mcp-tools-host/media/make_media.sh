#!/usr/bin/env bash
# media/make_media.sh — regenerate every media file from real judge output.
#
# Pipeline (all data written by judge/grade.sh / judge/mutants.py runs in
# THIS invocation — nothing is hand-edited or invented):
#   1. grade the known-good server (seed 20261015) -> judge_runs/good.json
#   2. generate + grade every single-edit mutant -> judge_runs/<name>.json
#   3. render result.png (tool checks vs the judge oracle, 1e-9 pass
#      line), loop.png (gates passed per iteration + kill-rate bars),
#      and demo.mp4 (30 s step-through, from a lossless -crf 0 master
#      in media/master/, git-ignored)
#   4. write MANIFEST.json (sha256 of every shipped file)
#
# Needs ffmpeg on PATH and the pinned media venv (built below from
# media/requirements.txt, hash-pinned, CPython 3.12 linux x86_64).

set -euo pipefail

MEDIA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(dirname "$MEDIA_DIR")"
JUDGE="$DEMO_DIR/judge"
RUNS="$MEDIA_DIR/judge_runs"
VENV="$HOME/.venvs/mcp-tools-media"
SEED="${MEDIA_SEED:-20261015}"

command -v ffmpeg >/dev/null 2>&1 || { echo "make_media: ffmpeg missing" >&2; exit 1; }

if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" -c "
import matplotlib, sys
sys.exit(0 if matplotlib.__version__ == '3.8.4' else 1)" 2>/dev/null; then
    echo "make_media: building pinned media venv $VENV"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --require-hashes --only-binary=:all: \
        -r "$MEDIA_DIR/requirements.txt"
fi

echo "=== 1. grade the known-good server (seed $SEED) ==="
rm -rf "$RUNS"; mkdir -p "$RUNS"
bash "$JUDGE/grade.sh" "$DEMO_DIR/examples/good/server.py" \
    --seed "$SEED" --json "$RUNS/good.json" >/dev/null

echo "=== 2. generate and grade every mutant ==="
MUT="$(mktemp -d)"
trap 'rm -rf "$MUT"' EXIT
"$VENV/bin/python" "$JUDGE/mutants.py" --out "$MUT" >/dev/null
for m in "$MUT"/*/server.py; do
    name="$(basename "$(dirname "$m")")"
    bash "$JUDGE/grade.sh" "$m" --seed "$SEED" \
        --json "$RUNS/$name.json" >/dev/null 2>&1 || true
done
n="$(ls "$RUNS" | wc -l)"
echo "make_media: $((n - 1)) mutant verdicts + good"

echo "=== 3+4. render figures, video, manifest ==="
"$VENV/bin/python" "$MEDIA_DIR/render.py"
ls -la "$MEDIA_DIR"/result.png "$MEDIA_DIR"/loop.png \
    "$MEDIA_DIR"/demo.mp4 "$MEDIA_DIR"/MANIFEST.json
