#!/usr/bin/env bash
# Regenerate the terminal-task-bench media from real judge runs.
#
# Every figure and number here comes from the judge itself: two grade.sh
# runs (the known-good agent and the adversarial verifier-rewrite agent)
# plus a selftest.sh run for the kill rate.  Nothing is hand-entered.
#
#   media/make_media.sh
#
# Needs: bash, python3, ffmpeg.  matplotlib/numpy/pillow are installed into
# media/.venv at pinned versions on first run (git-ignored).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$HERE/.." && pwd)"
DATA="$HERE/data"

MATPLOTLIB_VERSION="3.8.4"
NUMPY_VERSION="1.26.4"
PILLOW_VERSION="10.3.0"

command -v ffmpeg >/dev/null || { echo "make_media: ffmpeg not found" >&2; exit 1; }

venv="$HERE/.venv"
if [ ! -x "$venv/bin/python" ]; then
    echo "make_media: creating venv with pinned packages"
    python3 -m venv "$venv"
    "$venv/bin/pip" install --no-cache-dir -q \
        "matplotlib==$MATPLOTLIB_VERSION" \
        "numpy==$NUMPY_VERSION" \
        "pillow==$PILLOW_VERSION"
fi

mkdir -p "$DATA"

# --- real judge runs ------------------------------------------------------
echo "make_media: grade.sh examples/good -> data/grade_good.json"
bash "$DEMO/judge/grade.sh" "$DEMO/examples/good" \
    --json "$DATA/grade_good.json" --quiet >/dev/null

echo "make_media: build the adversarial agent and grade it"
cheat="$(mktemp -d)"
trap 'rm -rf "$cheat"' EXIT
python3 -I "$HERE/build_cheat.py" "$cheat"
# grade.sh exits non-zero here on purpose: the cheat must be killed.
bash "$DEMO/judge/grade.sh" "$cheat" \
    --json "$DATA/grade_cheat.json" --quiet >/dev/null 2>&1 || true
[ -s "$DATA/grade_cheat.json" ] || {
    echo "make_media: the cheat run wrote no verdict" >&2; exit 1; }

echo "make_media: selftest.sh -> data/selftest.log (for the kill rate)"
bash "$DEMO/judge/selftest.sh" > "$DATA/selftest.log" 2>&1 || {
    echo "make_media: selftest.sh failed" >&2; exit 1; }

# --- figures --------------------------------------------------------------
echo "make_media: figures and frames"
"$venv/bin/python" "$HERE/make_media.py"

# --- video ----------------------------------------------------------------
mkdir -p "$HERE/master"
ffmpeg -y -hide_banner -loglevel error \
    -f concat -safe 0 -i "$HERE/master/concat.txt" \
    -vf "fps=30,scale=1920:1080" \
    -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p \
    -movflags +faststart "$HERE/demo.mp4"
ffmpeg -y -hide_banner -loglevel error \
    -f concat -safe 0 -i "$HERE/master/concat.txt" \
    -vf "fps=30,scale=1920:1080" \
    -c:v libx264 -preset ultrafast -crf 0 -pix_fmt yuv420p \
    "$HERE/master/demo_master.mkv"

# --- manifest -------------------------------------------------------------
"$venv/bin/python" - "$HERE" <<'PY'
import hashlib, json, os, sys
here = sys.argv[1]
def sha(p):
    with open(p, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()
# what each committed media file shows, the command that made it, the
# data it reads and its sha256 (DEMO-STANDARD.md, Media)
entries = {
    "result.png": {
        "shows": "tasks solved per agent arm (G1 pass line) and verifier "
                 "wall time against the G4 budget; known-good 10/10 PASS, "
                 "negative control 0/10, adversarial 0/10 FAIL",
        "command": "media/make_media.sh",
        "source": "data/grade_good.json, data/grade_cheat.json",
    },
    "loop.png": {
        "shows": "self-test kill rate (12/12 mutants, known-good passing) "
                 "and the gate outcome of every arm",
        "command": "media/make_media.sh",
        "source": "data/selftest.log, data/grade_good.json, "
                  "data/grade_cheat.json",
    },
    "demo.mp4": {
        "shows": "24 s captioned step-through: the ten tasks, the pass "
                 "line, the verifier-rewrite cheat being killed, the kill "
                 "rate, and the all-gates-pass verdict",
        "command": "media/make_media.sh",
        "source": "media/master/ (frames from make_frames.py)",
    },
}
man = {}
for name, meta in entries.items():
    p = os.path.join(here, name)
    man[name] = dict(meta, sha256=sha(p), size=os.path.getsize(p))
with open(os.path.join(here, "MANIFEST.json"), "w") as fh:
    json.dump(man, fh, indent=2, sort_keys=True)
    fh.write("\n")
print("make_media: wrote MANIFEST.json")
PY

echo "make_media: done"
ls -la "$HERE/result.png" "$HERE/loop.png" "$HERE/demo.mp4"
