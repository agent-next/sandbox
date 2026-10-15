#!/usr/bin/env bash
# Render a cookbook demo video with Remotion, then gate it.
#
#   render.sh <props.json> <out.mp4>
#
# Pipeline: validate props -> stage clips into public/ -> npx remotion
# render (1920x1080, 30 fps, H.264, yuv420p, CRF 18) -> ffmpeg faststart
# remux -> re-encode at higher CRF if over 8 MiB -> video_gate.py.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS="$(cd "$HERE/.." && pwd)"
GATE="$TOOLS/video_gate.py"
MAX_BYTES=$((8 * 1024 * 1024))

if [ "$#" -ne 2 ]; then
  echo "usage: $0 <props.json> <out.mp4>" >&2
  exit 2
fi
PROPS="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
OUT="$(cd "$(dirname "$2")" && pwd)/$(basename "$2")"

log() { echo "[render.sh] $*" >&2; }

log "validating $PROPS"
python3 "$HERE/validate_props.py" "$PROPS"

if [ ! -d "$HERE/node_modules" ]; then
  log "installing dependencies (npm ci)"
  (cd "$HERE" && npm ci --no-audit --no-fund)
fi
log "ensuring headless browser"
(cd "$HERE" && npx remotion browser ensure >/dev/null 2>&1 || true)

log "staging assets"
python3 "$HERE/stage_props.py" "$PROPS" "$HERE/public" \
  "$HERE/public/staged/props.json"

RAW="$(mktemp --suffix=.mp4)"
trap 'rm -f "$RAW"' EXIT
log "rendering Demo -> raw"
(cd "$HERE" && npx remotion render src/index.ts Demo "$RAW" \
  --props=./public/staged/props.json \
  --codec=h264 --pixel-format=yuv420p --crf=18 --x264-preset=slow \
  --gl=swangle)

log "faststart remux -> $OUT"
ffmpeg -y -v error -i "$RAW" -c copy -movflags +faststart "$OUT"
SIZE=$(stat -c %s "$OUT")

for CRF in 20 23 26; do
  [ "$SIZE" -le "$MAX_BYTES" ] && break
  log "over 8 MiB ($((SIZE / 1024)) KiB); re-encoding at CRF $CRF"
  ffmpeg -y -v error -i "$RAW" -c:v libx264 -preset slow -crf "$CRF" \
    -pix_fmt yuv420p -movflags +faststart "$OUT"
  SIZE=$(stat -c %s "$OUT")
done
if [ "$SIZE" -gt "$MAX_BYTES" ]; then
  log "still >8 MiB after CRF ladder; giving up"
  exit 1
fi
log "size: $((SIZE / 1024)) KiB"

log "running video gate"
python3 "$GATE" "$OUT"
