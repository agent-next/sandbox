#!/usr/bin/env bash
# media/make_media.sh — regenerate every media artifact from judge output.
#
# Prerequisites (fails loudly if missing):
#   * media/data/ produced by media/make_data.sh (verdict JSONs for
#     good + 8 mutants, raw ERC/DRC JSONs, mutant project copies)
#   * kicad-cli (judge/setup.sh) for board/schematic renders
#   * ffmpeg + ffprobe on PATH for demo.mp4
#   * python3 >= 3.10; pip deps install into a pinned venv media/.venv
#     via --require-hashes -r judge/requirements.txt
#
# Outputs: result.png, loop.png, demo.mp4, MANIFEST.json.
# The lossless master and all intermediates land in media/master/
# (gitignored).

set -euo pipefail
cd "$(dirname "$0")/.."           # cookbook/kicad-pcb/

MEDIA=media
DATA=$MEDIA/data
MASTER=$MEDIA/master
VENV=$MEDIA/.venv
GOOD=examples/good/555-blinker

die() { echo "make_media: ERROR: $*" >&2; exit 1; }

# -- tool checks --------------------------------------------------------------
command -v ffmpeg  >/dev/null || die "ffmpeg not found on PATH"
command -v ffprobe >/dev/null || die "ffprobe not found on PATH"
python3 -c 'import sys; assert sys.version_info >= (3, 10)' \
    || die "need python3 >= 3.10"
if [[ -n "${KICAD_CLI:-}" ]]; then CLI="$KICAD_CLI"
elif command -v kicad-cli >/dev/null; then CLI="kicad-cli"
elif [[ -x "$HOME/.local/kicad-pcb-demo/bin/kicad-cli" ]]; then
    CLI="$HOME/.local/kicad-pcb-demo/bin/kicad-cli"
else die "kicad-cli not found; run judge/setup.sh first"; fi
export KICAD_CLI="$CLI"
echo "kicad-cli: $CLI ($("$CLI" --version))"
ffmpeg -version | head -1

# -- data checks ---------------------------------------------------------------
[[ -d "$DATA" ]] || die "media/data missing; run media/make_data.sh first"
need_json() {
    [[ -f "$DATA/$1" ]] || die "missing media/data/$1 — run media/make_data.sh"
}
need_json good.json
need_json good.erc.json
need_json good.drc.json
MUTANTS=""
for m in erc_unconnected_pin erc_power_short erc_off_grid \
         netlist_mismatch drc_unconnected drc_short \
         outline_open drill_no_tools; do
    need_json "$m.json"; need_json "$m.erc.json"; need_json "$m.drc.json"
    [[ -d "$DATA/mutants/$m" ]] \
        || die "missing media/data/mutants/$m — run media/make_data.sh"
    MUTANTS="$MUTANTS $m"
done
python3 - "$DATA/good.json" <<'PY'
import json, sys
v = json.load(open(sys.argv[1]))
assert v["overall_pass"], "good.json is not a pass — regenerate data"
PY

# -- pinned venv ---------------------------------------------------------------
if [[ ! -x "$VENV/bin/python" ]]; then
    python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q --require-hashes -r judge/requirements.txt
PYBIN="$VENV/bin/python"
"$PYBIN" -c 'import matplotlib, numpy, pymupdf' \
    || die "venv deps broken"

# -- render --------------------------------------------------------------------
mkdir -p "$MASTER/frames"
rm -f "$MASTER/frames"/f*.png
echo "== rendering figures + frames"
"$PYBIN" "$MEDIA/render.py"

NFRAMES=$(ls "$MASTER"/frames/f*.png | wc -l)
[[ "$NFRAMES" -ge 5 ]] || die "only $NFRAMES frames rendered"

# -- encode demo.mp4 -----------------------------------------------------------
echo "== encoding demo.mp4 ($NFRAMES frames)"
LIST="$MASTER/frames/frames.txt"
: > "$LIST"
# per-frame durations (s): intro, good verdict, mutants, summary
DUR=(4 5)
for ((i = 0; i < NFRAMES - 3; i++)); do DUR+=(4); done
DUR+=(5)
i=0
for f in "$MASTER"/frames/f*.png; do
    echo "file '$(basename "$f")'" >> "$LIST"
    echo "duration ${DUR[$i]}" >> "$LIST"
    i=$((i + 1))
done
last=$(basename "$(ls "$MASTER"/frames/f*.png | tail -1)")
echo "file '$last'" >> "$LIST"     # concat demuxer drops the last image

ffmpeg -y -f concat -safe 0 -i "$LIST" \
    -vf "fps=30,scale=1920:1080:flags=lanczos,format=yuv420p" \
    -c:v libx264 -crf 0 -preset medium "$MASTER/demo.mkv" \
    -loglevel error -hide_banner
ffmpeg -y -i "$MASTER/demo.mkv" \
    -c:v libx264 -crf 18 -preset slow \
    -pix_fmt yuv420p -movflags +faststart -r 30 \
    "$MEDIA/demo.mp4" -loglevel error -hide_banner

# verify the encode: 1920x1080, 30 fps, 20-60 s, < 8 MB
"$PYBIN" - "$MEDIA/demo.mp4" <<'PY'
import json, os, subprocess, sys
p = sys.argv[1]
pr = json.loads(subprocess.check_output([
    "ffprobe", "-v", "error", "-select_streams", "v:0",
    "-show_entries", "stream=width,height,r_frame_rate",
    "-show_entries", "format=duration", "-of", "json", p]))
st = pr["streams"][0]
w, h = st["width"], st["height"]
fps = eval(st["r_frame_rate"])
dur = float(pr["format"]["duration"])
size = os.path.getsize(p)
assert (w, h) == (1920, 1080), f"bad size {w}x{h}"
assert abs(fps - 30) < 0.01, f"bad fps {fps}"
assert 20 <= dur <= 60, f"bad duration {dur}s"
assert size < 8 * 1024 * 1024, f"too big: {size}"
print(f"demo.mp4: {w}x{h} {fps:.0f} fps {dur:.1f} s {size / 1e6:.2f} MB")
PY

# -- manifest ------------------------------------------------------------------
echo "== manifest"
"$PYBIN" - "$MEDIA" <<'PY'
import hashlib, json, os, sys
media = sys.argv[1]
data = os.path.join(media, "data")


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


src_data = {}
for root, _dirs, files in os.walk(data):
    for f in sorted(files):
        if f.endswith((".json", ".kicad_pcb", ".kicad_sch", ".kicad_pro")):
            p = os.path.join(root, f)
            src_data[os.path.relpath(p, media)] = sha(p)

entries = [
    ("result.png",
     "kicad-cli 3D render of the known-good board (left) and the "
     "per-gate judge verdict with measured values (right)",
     "data/good.json"),
    ("loop.png",
     "self-test kill matrix: known-good + 8 mutants x gates G1-G6, "
     "coloured from verdict JSONs; red cells show the measured value",
     "data/*.json verdicts"),
    ("demo.mp4",
     "step-through: real board render, good verdict, each mutant "
     "before/after with its ERC/DRC marker circled, kill matrix",
     "master/frames/ + data/*.json"),
    ("make_data.sh", "regenerates data/ from fresh judge runs", "-"),
    ("make_media.sh", "this regeneration script", "-"),
    ("render.py", "figure/frame renderer (matplotlib + PyMuPDF)", "-"),
    ("REVIEW.md", "manual pixel-level review record", "-"),
]
out = []
for name, desc, src in entries:
    p = os.path.join(media, name)
    if not os.path.exists(p):
        continue
    out.append({"file": name, "description": desc,
                "command": "bash media/make_data.sh && bash media/make_media.sh",
                "source_data": src, "sha256": sha(p)})
manifest = {"outputs": out,
            "source_data_sha256": src_data}
json.dump(manifest, open(os.path.join(media, "MANIFEST.json"), "w"),
          indent=2)
print(f"MANIFEST.json: {len(out)} outputs, {len(src_data)} data files")
PY

ls -la "$MEDIA"/result.png "$MEDIA"/loop.png "$MEDIA"/demo.mp4 \
    "$MEDIA"/MANIFEST.json
echo "media done"
