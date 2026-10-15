#!/usr/bin/env bash
# usd-validate-fix media: regenerate every media file from real judge output.
#
# Pipeline (all data written by judge/grade.sh / judge/mutants.py runs in
# THIS invocation -- nothing is hand-edited or invented):
#   1. run self-test + grade good + all mutants (into media/judge_runs/)
#   2. extract mesh data for good + broken assets
#   3. copy the verdicts to media/data/ for the figures and the video
#   4. render result.png, loop.png
#   5. render video frames -> lossless master (crf 0, git-ignored) -> web encode
#   6. write MANIFEST.json, result.json, STORYBOARD.md, REVIEW.json
#   7. run cookbook/tools/video_gate.py on demo.mp4 and FAIL the build unless
#      it prints passed: true
#
# media/judge_runs/, media/master/, media/frames/ and media/.venv/ are all
# git-ignored (see media/.gitignore): only the artefacts under media/data/
# and the committed files above are source-controlled.
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
DATA="$MEDIA_DIR/data"
VENV="$HOME/.usd-validate-fix-venv"
PY="$VENV/bin/python"
SEED="20261015"

[ -x "$VENV/bin/nvidia_usd_validate" ] || { echo "make_media: judge venv missing -- run 'bash judge/setup.sh' first" >&2; exit 1; }
command -v ffmpeg >/dev/null 2>&1 || { echo "make_media: ffmpeg missing" >&2; exit 1; }

# The figure/video scripts need matplotlib+numpy, which the judge venv
# does not carry (it holds only the pinned judge wheels).  They run from
# MPLPY, a separate git-ignored venv at media/.venv, built here when
# missing so `bash media/make_media.sh` works on a fresh host.  Judge
# tools that need pxr keep using $PY (the judge venv).
MPLPY="$MEDIA_DIR/.venv/bin/python"
if [ ! -x "$MPLPY" ] || ! "$MPLPY" -c 'import matplotlib, numpy' >/dev/null 2>&1; then
    echo "[media] creating plotting venv media/.venv (matplotlib+numpy, pinned)"
    python3 -m venv "$MEDIA_DIR/.venv"
    "$MEDIA_DIR/.venv/bin/pip" install --disable-pip-version-check --quiet \
        matplotlib==3.11.2 numpy==2.5.4
fi

echo "[media] matplotlib $("$MPLPY" -c 'import matplotlib; print(matplotlib.__version__)')"
echo "[media] ffmpeg $(ffmpeg -version | head -1 | awk '{print $3}')"

# --- 1. replay: self-test + good + mutants ---
echo "=== 1. replay: self-test + known-good + all mutants ==="
rm -rf "$REPLAY"
mkdir -p "$REPLAY/verdicts" "$REPLAY/mutants"

# self-test output for the kill rate loop.png / make_video.py read
bash "$JDIR/selftest.sh" > "$REPLAY/selftest_output.txt" 2>&1
sed -i "s|/tmp/tmp\.[A-Za-z0-9]*|<tmp>|g" "$REPLAY/selftest_output.txt"
tail -3 "$REPLAY/selftest_output.txt"

# known-good graded twice (determinism).  A failing grade exits non-zero and
# `set -e` stops the build here rather than producing a video of a fail.
bash "$JDIR/grade.sh" "$DEMO_DIR/examples/good/traffic_cone_fixed.usda" --seed "$SEED" --json "$REPLAY/verdicts/01_good.json" > /dev/null
bash "$JDIR/grade.sh" "$DEMO_DIR/examples/good/traffic_cone_fixed.usda" --seed "$SEED" --json "$REPLAY/verdicts/01_good_replica.json" > /dev/null
PYTHONDONTWRITEBYTECODE=1 "$PY" -I - "$REPLAY/verdicts/01_good.json" "$REPLAY/verdicts/01_good_replica.json" <<'PY' || exit 1
import json, sys
a = json.load(open(sys.argv[1])); a.pop("timing", None)
b = json.load(open(sys.argv[2])); b.pop("timing", None)
raise SystemExit(0 if a == b else 1)
PY

# broken asset (the starting state -- a failing grade is expected here)
bash "$JDIR/grade.sh" "$DEMO_DIR/task/traffic_cone_broken.usda" --json "$REPLAY/verdicts/00_broken.json" > /dev/null 2>&1 || true

# mutants: each must be killed by a judge gate, so a non-zero exit with a
# verdict JSON is the expected outcome
"$PY" -I "$JDIR/mutants.py" "$DEMO_DIR/examples/good/traffic_cone_fixed.usda" "$REPLAY/mutants" > /dev/null
for m in "$REPLAY"/mutants/*.usda; do
    name="$(basename "$m" .usda)"
    bash "$JDIR/grade.sh" "$m" --json "$REPLAY/verdicts/${name}.json" > /dev/null 2>&1 || true
done

# --- 2. extract mesh data ---
echo "=== 2. extract mesh data (good + broken) ==="
"$PY" -I "$MEDIA_DIR/extract_mesh.py" "$DEMO_DIR/examples/good/traffic_cone_fixed.usda" "$DATA/mesh_good.json"
"$PY" -I "$MEDIA_DIR/extract_mesh.py" "$DEMO_DIR/task/traffic_cone_broken.usda" "$DATA/mesh_broken.json"

# --- 3. copy verdicts to media/data/ for figures ---
# The figures and make_video.py read media/data/grade_<name>.json, so the
# replay's numbered prefixes (00_/01_) are dropped here: grade_01_good.json
# becomes grade_good.json.
echo "=== 3. copy verdicts to media/data/ ==="
rm -f "$DATA"/grade_*.json
for f in "$REPLAY"/verdicts/*.json; do
    base="$(basename "$f" .json)"
    name="${base#00_}"; name="${name#01_}"
    cp "$f" "$DATA/grade_${name}.json"
done
cp "$REPLAY/selftest_output.txt" "$DATA/selftest_output.txt"
ls "$DATA"

# --- 4. figures ---
echo "=== 4. figures ==="
"$MPLPY" -I "$MEDIA_DIR/fig_result.py"
"$MPLPY" -I "$MEDIA_DIR/fig_loop.py"

# --- 5. video ---
echo "=== 5. video (frames -> lossless master -> web encode) ==="
"$MPLPY" -I "$MEDIA_DIR/make_video.py"

# --- 6. manifest + result.json + storyboard + review ---
echo "=== 6. manifest + result.json + storyboard + review ==="
"$PY" -I "$MEDIA_DIR/make_manifest.py"
"$PY" -I "$MEDIA_DIR/make_result_json.py"
"$PY" -I "$MEDIA_DIR/make_storyboard.py"
"$PY" -I "$MEDIA_DIR/make_review.py"

# --- 7. video gate: the standard's check must pass ---
echo "=== 7. video gate (cookbook/tools/video_gate.py) ==="
GATE_TOOL="$DEMO_DIR/../tools/video_gate.py"
[ -f "$GATE_TOOL" ] || { echo "make_media: $GATE_TOOL missing" >&2; exit 1; }
cp "$GATE_TOOL" "$RUNS/video_gate.py"
"$PY" -I "$RUNS/video_gate.py" "$MEDIA_DIR/demo.mp4" --json "$MEDIA_DIR/video_gate_result.json" \
    || { echo "make_media: video_gate FAILED (see above)" >&2; exit 1; }
GATE_OK="$(python3 -I -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1]))["passed"]))' \
    "$MEDIA_DIR/video_gate_result.json")"
[ "$GATE_OK" = "true" ] || { echo "make_media: video_gate passed=$GATE_OK, not true" >&2; exit 1; }
echo "make_media: video gate passed: true"

echo "make_media: done -> $MEDIA_DIR/{result.png,loop.png,demo.mp4,MANIFEST.json,result.json,STORYBOARD.md,REVIEW.json}"
