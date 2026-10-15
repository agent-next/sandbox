#!/usr/bin/env bash
# media/make_media.sh — regenerate every media artifact from the real
# judge outputs (cookbook/DEMO-STANDARD.md, Media). Nothing is hand-edited:
#
#   1. runs the real judge pipeline (setup -> selftest -> grade, seed 42)
#      and captures its real logs/verdicts into media/data/;
#   2. collects the judged geometry with usd-core (collect_meshes.py);
#   3. renders result.png, loop.png, the lossless master and demo.mp4
#      per media/STORYBOARD.md (render_media.py);
#   4. writes media/MANIFEST.json (sha256 of every produced file);
#   5. checks the encode with cookbook/tools/video_gate.py.
#
# Media build scratch stays under media/work/ (git-ignored). The judge
# itself is untouched: everything runs against the committed judge/ in
# place, exactly as a user would run it.
#
# Usage: bash media/make_media.sh [--keep-data]   (from the demo dir)
#   --keep-data  reuse the existing media/data (skip the ~35 min judge run;
#                for re-rendering only)

set -euo pipefail

MEDIA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$MEDIA/.." && pwd)"
JUDGE_PY="$HOME/.venvs/cad2usd-judge/bin/python"

for tool in python3 ffmpeg ffprobe; do
    command -v "$tool" >/dev/null || { echo "make_media: missing $tool" >&2; exit 1; }
done
[[ -x "$JUDGE_PY" ]] || {
    echo "make_media: judge venv missing — run judge/setup.sh first" >&2; exit 1; }

KEEP_DATA=0
[[ "${1:-}" == "--keep-data" ]] && KEEP_DATA=1

DATA="$MEDIA/data"
WORK="$MEDIA/work"
mkdir -p "$DATA/verdicts" "$WORK" "$MEDIA/master"

if [[ $KEEP_DATA -eq 0 ]]; then
    echo "== make_media: real judge run (setup + selftest + grade) =="
    (cd "$DEMO" && bash judge/setup.sh) > "$WORK/setup.log" 2>&1
    echo "setup: done ($(grep -c 'done' "$WORK/setup.log" >/dev/null && echo ok))"
    SEED=42
    T0=$(date +%s)
    (cd "$DEMO" && bash judge/selftest.sh) > "$DATA/selftest.log" 2>&1
    echo "selftest: done ($(( $(date +%s) - T0 )) s)"
    (cd "$DEMO" && bash judge/grade.sh examples/good --seed $SEED \
        --json "$DATA/verdict-good.json") > "$DATA/grade-good.log" 2>&1
    echo "grade: done"
    # seconds of real judge work shown sped up in the video (selftest wall time)
    python3 - <<PY
import json, re
log = open("$DATA/selftest.log").read()
m = re.search(r"selftest: PASS \((\d+) s\)", log)
secs = int(m.group(1)) if m else 0
json.dump({"seconds": secs}, open("$DATA/selftest_seconds.json", "w"))
print(f"judge seconds captured: {secs}")
PY

    # real mutant verdicts for the kill matrix (graded in the selftest);
    # regenerate them here so the matrix shows gate-level verdicts
    MWORK="$WORK/mutants"
    rm -rf "$MWORK"
    "$JUDGE_PY" -I "$DEMO/judge/mutants.py" "$DEMO/examples/good" "$MWORK" \
        > "$DATA/mutants.log" 2>&1
    for d in "$MWORK"/*/; do
        name=$(basename "$d")
        case "$name" in
            garbage_convert|cheat_copy_outputs) rec="" ;;
            *) rec="--no-reconvert" ;;
        esac
        (cd "$DEMO" && bash judge/grade.sh "$d" --seed $SEED $rec \
            --json "$DATA/verdicts/$name.json") \
            > "$WORK/grade-$name.log" 2>&1 || true
        echo "mutant $name graded: $(python3 -c "
import json
try:
    d = json.load(open('$DATA/verdicts/$name.json'))
    bad = [k for k, v in d['gates'].items() if isinstance(v, dict) and v.get('passed') is False]
    print('killed by ' + (', '.join(bad) if bad else 'NOTHING'))
except Exception as e:
    print('no verdict:', e)")"
    done
fi

echo "== make_media: refresh loop.json gates_failed from the verdicts =="
python3 - <<PY
import json, os
data = os.path.abspath("$DATA")
loop = json.load(open(os.path.join(data, "loop.json")))
for step in loop["steps"]:
    p = os.path.join(data, step["verdict"])
    v = json.load(open(p))
    bad = sorted(k for k, g in v["gates"].items()
                 if isinstance(g, dict) and g.get("passed") is False)
    step["gates_failed"] = bad
json.dump(loop, open(os.path.join(data, "loop.json"), "w"), indent=2)
print("loop.json gates_failed refreshed from real verdicts")
PY

echo "== make_media: collect judged geometry =="
cp "$DATA/verdict-good.json" "$WORK/verdict-copy.json"
(cd "$DEMO" && "$JUDGE_PY" -I "$MEDIA/collect_meshes.py" \
    "$DATA/verdict-good.json" "$DATA/meshes.npz" examples/good)

# the real pinned sources for the input->output slot headers
bash "$DEMO/judge/fetch_sources.sh" "$DATA" >/dev/null

echo "== make_media: render stills + frames + master =="
(cd "$MEDIA" && "$JUDGE_PY" -I render_media.py "$DATA" "$MEDIA")

echo "== make_media: web encode from the crf 0 master =="
ffmpeg -y -v error -threads 2 -i "$MEDIA/master/demo.mp4" \
    -c:v libx264 -threads 2 -crf 18 -preset slow -pix_fmt yuv420p \
    -movflags +faststart -map_metadata -1 -an "$MEDIA/demo.mp4"

echo "== make_media: manifest =="
python3 - <<PY
import hashlib, json, os
media = os.path.abspath("$MEDIA")
static = {
    "demo.mp4": ("Storyboard video: hook on the finished 3D render, "
                 "input->output splits, Nx-speed real judge terminal run, "
                 "verdict + kill-matrix proof, end card",
                 "ffmpeg web encode of master/demo.mp4 (see STORYBOARD.md)",
                 "media/data/{verdict-good.json,meshes.npz,selftest.log,"
                 "grade-good.log,verdicts/*.json} + media/data/sources/"),
    "result.png": ("Hero still: the three judged parts rendered from their "
                   "judged .usda meshes, with the judge pass lines drawn on",
                   "render_media.py make_result_png",
                   "media/data/meshes.npz + media/data/verdict-good.json"),
    "loop.png": ("Agent loop replay + self-test kill-rate bar",
                 "render_media.py make_loop_png",
                 "media/data/loop.json + media/data/verdicts/*.json"),
}
files = {}
for name, (what, command, source) in static.items():
    p = os.path.join(media, name)
    h = hashlib.sha256(open(p, "rb").read()).hexdigest()
    files[name] = {"what": what, "command": command,
                   "source_data": source,
                   "sha256": h, "bytes": os.path.getsize(p)}
json.dump({"demo": "cookbook/cad-to-usd",
           "command": "bash cookbook/cad-to-usd/media/make_media.sh",
           "seed": 42,
           "note": "every number on screen comes from judge output files "
                   "regenerated by make_media.sh (seed 42)",
           "files": files},
          open(os.path.join(media, "MANIFEST.json"), "w"), indent=2)
print(json.dumps(files, indent=2))
PY

echo "== make_media: video gate =="
GATE="${VIDEO_GATE:-$DEMO/../tools/video_gate.py}"
if [[ ! -f "$GATE" ]]; then
    echo "video_gate.py not found at $GATE (on main: cookbook/tools/)" >&2
    exit 1
fi
python3 "$GATE" "$MEDIA/demo.mp4"
echo "make_media: done"
