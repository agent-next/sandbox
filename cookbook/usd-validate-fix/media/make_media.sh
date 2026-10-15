#!/usr/bin/env bash
# usd-validate-fix media: regenerate every media file from real judge output.
#
# Pipeline (all data written by judge/grade.sh / judge/mutants.py runs in
# THIS invocation — nothing is hand-edited or invented):
#   1. run self-test + grade good + all mutants (into media/judge_runs/)
#   2. extract mesh data for good + broken assets
#   3. render result.png, loop.png
#   4. render video frames -> lossless master (crf 0, gitignored) -> web encode
#   5. write MANIFEST.json, result.json, STORYBOARD.md, REVIEW.json
#   6. run video_gate on demo.mp4
#
# Fails loudly if any expected judge output is missing.

set -euo pipefail

MEDIA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(dirname "$MEDIA_DIR")"
JDIR="$DEMO_DIR/judge"
RUNS="$MEDIA_DIR/judge_runs"
REPLAY="$RUNS/replay"
MASTER="$MEDIA_DIR/master"
FRAMES="$MEDIA_DIR/frames"
VENV="$HOME/.usd-validate-fix-venv"
PY="$VENV/bin/python"
SEED="20261015"

[ -x "$VENV/bin/nvidia_usd_validate" ] || { echo "make_media: judge venv missing -- run 'bash judge/setup.sh' first" >&2; exit 1; }
command -v ffmpeg >/dev/null 2>&1 || { echo "make_media: ffmpeg missing" >&2; exit 1; }
"$PY" -c 'import matplotlib' >/dev/null 2>&1 || { echo "make_media: python3 lacks matplotlib" >&2; exit 1; }

echo "[media] matplotlib $("$PY" -c 'import matplotlib; print(matplotlib.__version__)')"
echo "[media] ffmpeg $(ffmpeg -version | head -1 | awk '{print $3}')"

# --- 1. replay: self-test + good + mutants ---
echo "=== 1. replay: self-test + known-good + all mutants ==="
mkdir -p "$REPLAY/verdicts" "$REPLAY/mutants"

# self-test output for loop.png kill rate
bash "$JDIR/selftest.sh" > "$REPLAY/selftest_output.txt" 2>&1
sed -i "s|/tmp/tmp\.[A-Za-z0-9]*|<tmp>|g" "$REPLAY/selftest_output.txt"

# known-good graded twice (determinism)
bash "$JDIR/grade.sh" "$DEMO_DIR/examples/good/traffic_cone_fixed.usda" --seed "$SEED" --json "$REPLAY/verdicts/01_good.json" > /dev/null
bash "$JDIR/grade.sh" "$DEMO_DIR/examples/good/traffic_cone_fixed.usda" --seed "$SEED" --json "$REPLAY/verdicts/01_good_replica.json" > /dev/null
python3 -I - "$REPLAY/verdicts/01_good.json" "$REPLAY/verdicts/01_good_replica.json" <<'PY' || exit 1
import json, sys
a = json.load(open(sys.argv[1])); a.pop("timing", None)
b = json.load(open(sys.argv[2])); b.pop("timing", None)
raise SystemExit(0 if a == b else 1)
PY

# broken asset (starting state)
bash "$JDIR/grade.sh" "$DEMO_DIR/task/traffic_cone_broken.usda" --json "$REPLAY/verdicts/00_broken.json" > /dev/null 2>&1 || true

# mutants
"$PY" -I "$JDIR/mutants.py" "$DEMO_DIR/examples/good/traffic_cone_fixed.usda" "$REPLAY/mutants" > /dev/null
for m in "$REPLAY"/mutants/*.usda; do
    name="$(basename "$m" .usda)"
    bash "$JDIR/grade.sh" "$m" --json "$REPLAY/verdicts/${name}.json" > /dev/null 2>&1 || true
done

# --- 2. extract mesh data ---
echo "=== 2. extract mesh data (good + broken) ==="
"$PY" -I "$MEDIA_DIR/extract_mesh.py" "$DEMO_DIR/examples/good/traffic_cone_fixed.usda" "$MEDIA_DIR/data/mesh_good.json"
"$PY" -I "$MEDIA_DIR/extract_mesh.py" "$DEMO_DIR/task/traffic_cone_broken.usda" "$MEDIA_DIR/data/mesh_broken.json"

# --- 3. copy verdicts to media/data/ for figures ---
echo "=== 3. copy verdicts to media/data/ ==="
for f in "$REPLAY"/verdicts/*.json; do
    name="$(basename "$f")"
    cp "$f" "$MEDIA_DIR/data/grade_${name}"
done
cp "$REPLAY/selftest_output.txt" "$MEDIA_DIR/data/selftest_output.txt"

# --- 4. figures ---
echo "=== 4. figures ==="
"$PY" -I "$MEDIA_DIR/fig_result.py"
"$PY" -I "$MEDIA_DIR/fig_loop.py"

# --- 5. video ---
echo "=== 5. video (frames -> lossless master -> web encode) ==="
"$PY" -I "$MEDIA_DIR/make_video.py"

# --- 6. manifest + result.json + storyboard + review ---
echo "=== 6. manifest + result.json + storyboard + review ==="
"$PY" -I "$MEDIA_DIR/make_manifest.py"
"$PY" -I "$MEDIA_DIR/make_result_json.py"
"$PY" -I "$MEDIA_DIR/make_storyboard.py"
"$PY" -I "$MEDIA_DIR/make_review.py"

# --- 7. video gate ---
echo "=== 7. video gate ==="
if ! command -v python3 >/dev/null; then
    echo "make_media: python3 missing" >&2; exit 1
fi
# Get video_gate.py from main if not present
if [ ! -f "$MEDIA_DIR/video_gate.py" ]; then
    echo "make_media: fetching video_gate.py from main..."
    git show origin/main:cookbook/tools/video_gate.py > "$MEDIA_DIR/video_gate.py" 2>/dev/null || \
        git show 6f5c53d4a4daef74ff58452db97f8ac1ca45be99:cookbook/tools/video_gate.py > "$MEDIA_DIR/video_gate.py"
fi
"$PY" "$MEDIA_DIR/video_gate.py" "$MEDIA_DIR/demo.mp4" --json "$MEDIA_DIR/video_gate_result.json"

echo "make_media: done -> $MEDIA_DIR/{result.png,loop.png,demo.mp4,MANIFEST.json,result.json,STORYBOARD.md,REVIEW.json}"
