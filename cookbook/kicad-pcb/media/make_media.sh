#!/usr/bin/env bash
# media/make_media.sh — regenerate every media artifact from judge output.
#
# Steps: grade the good example + all mutants into media/data/*.json,
# render result.png / loop.png / video frames with media/render.py,
# then encode demo.mp4 (lossless master in media/master/, gitignored).
# Writes media/MANIFEST.json with a sha256 for every shipped file.

set -euo pipefail
cd "$(dirname "$0")/.."           # cookbook/kicad-pcb/

MEDIA=media
DATA=$MEDIA/data
MASTER=$MEDIA/master
mkdir -p "$DATA" "$MASTER/frames"

echo "== collecting judge data"
bash judge/grade.sh examples/good/555-blinker --json "$DATA/good.json"
python3 judge/mutants.py examples/good/555-blinker "$DATA/mutants"
for m in "$DATA/mutants"/*/; do
    n=$(basename "$m")
    bash judge/grade.sh "$m" --json "$DATA/$n.json" \
        >"$DATA/$n.log" 2>&1 || true     # mutants are expected to fail
done
rm -rf "$DATA/mutants"

echo "== rendering"
python3 "$MEDIA/render.py"

echo "== encoding demo.mp4"
LIST="$MASTER/frames/frames.txt"
: > "$LIST"
for f in "$MASTER"/frames/f*.png; do
    echo "file '$(basename "$f")'" >> "$LIST"
    echo "duration 5" >> "$LIST"          # 5 slides x ~5 s = ~25 s
done
# concat demuxer drops the last image unless repeated
last=$(basename "$(ls "$MASTER"/frames/f*.png | tail -1)")
echo "file '$last'" >> "$LIST"
ffmpeg -y -f concat -safe 0 -i "$LIST" -vf "fps=30,scale=1920:1080:flags=lanczos,format=yuv420p" \
    -c:v libx264 -crf 0 -preset medium "$MASTER/demo.mkv" \
    -loglevel error -hide_banner
ffmpeg -y -i "$MASTER/demo.mkv" -c:v libx264 -crf 18 -preset slow \
    -pix_fmt yuv420p -movflags +faststart -vf scale=1920:1080 \
    -r 30 "$MEDIA/demo.mp4" -loglevel error -hide_banner

echo "== manifest"
python3 - "$MEDIA" <<'EOF'
import hashlib, json, os, sys
media = sys.argv[1]
entries = []
desc = {
    "result.png": ("board geometry + per-gate judge verdict for the "
                   "known-good 555 blinker", "data/good.json"),
    "loop.png": ("self-test: failed-gate count for known-good and each "
                 "mutant, with the kill-rate bar", "data/*.json"),
    "demo.mp4": ("step-through of the judge loop: artifact, gate "
                 "results, mutant kills, verdict", "master/frames/"),
    "make_media.sh": ("this regeneration script", "-"),
    "render.py": ("figure/frame renderer (matplotlib)", "-"),
}
for name in sorted(desc):
    p = os.path.join(media, name)
    if not os.path.exists(p):
        continue
    d, src = desc[name]
    entries.append({
        "file": name,
        "description": d,
        "command": "bash media/make_media.sh",
        "source_data": src,
        "sha256": hashlib.sha256(open(p, "rb").read()).hexdigest(),
    })
json.dump(entries, open(os.path.join(media, "MANIFEST.json"), "w"),
          indent=2)
EOF
ls -la "$MEDIA"/result.png "$MEDIA"/loop.png "$MEDIA"/demo.mp4 \
    "$MEDIA"/MANIFEST.json
echo "media done"
