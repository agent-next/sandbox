#!/bin/bash
# Generate the lavfi motion clips the examples are cut from. Nothing here is
# committed; the props files reference the paths this writes.
#
#     bash cookbook/tools/hyperframes/scripts/make_clips.sh <out-dir>
#
# Default out-dir is ./media/clips. Each clip is 8 s of real, deterministic
# motion, upscaled to 1920x1080 and encoded H.264 CRF 18 — the same recipe the
# bake-off spec names, so both branches of the experiment show the same footage.
set -euo pipefail

OUT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/media/clips}"
mkdir -p "$OUT"

# name=lavfi-source  (each 640x360 at 30 fps, except testsrc2 which is native)
declare -a CLIPS=(
  "mandelbrot=mandelbrot=s=640x360:r=30"
  "life=life=s=640x360:r=30:mold=10:ratio=0.1:death_color=#0B3D2E:life_color=#2EC4B6"
  "testsrc2=testsrc2=s=1920x1080:r=30"
  "cellauto=cellauto=s=640x360:r=30:rule=110"
)

for entry in "${CLIPS[@]}"; do
  name="${entry%%=*}"
  src="${entry#*=}"
  out="$OUT/$name.mp4"
  echo "  $name.mp4  <- $src"
  ffmpeg -y -v error \
    -f lavfi -i "$src" \
    -t 8 \
    -vf "scale=1920:1080:flags=lanczos,setsar=1" \
    -r 30 -pix_fmt yuv420p -c:v libx264 -crf 18 \
    "$out"
done

echo "clips in $OUT:"
ls -la "$OUT"
