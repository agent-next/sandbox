#!/usr/bin/env bash
# Runs inside the sandbox (root, node:22-bookworm). Writes /w/out/* and /w/status (step name, "done" or "failed:<step>").
set -uo pipefail
SHA="$1"; shift; TARGETS="$*"; REPO="https://github.com/img2threejs/img2threejs-showcase.git"
W=/w; OUT=$W/out; mkdir -p "$OUT"
step() { echo "$1" > $W/status; echo "[$(date -u +%H:%M:%SZ)] step $1: start" >> $OUT/steps.log; }
ok() { echo "[$(date -u +%H:%M:%SZ)] step $1: ok" >> $OUT/steps.log; }
die() { echo "failed:$1" > $W/status; echo "[$(date -u +%H:%M:%SZ)] step $1: FAILED" >> $OUT/steps.log; exit 1; }

{ nproc; free -g | sed -n 2p; node --version; } > $OUT/env.txt
step clone
(cd $W && git init -q sc && cd sc && git remote add o $REPO && git fetch -q --depth 1 o "$SHA" \
  && git checkout -q FETCH_HEAD && git rev-parse HEAD > $OUT/sha.txt) || die clone; ok clone
cd $W/sc
step npm-ci;  npm ci --no-audit --no-fund > $OUT/npm-ci.log 2>&1 || die npm-ci; ok npm-ci
step build;   { time npm run build; } > $OUT/build.log 2>&1 || die build; ok build
du -sh dist >> $OUT/env.txt
grep -oP "^    id: '\K[^']+" src/demos/registry.ts > $OUT/ids.txt
ls -d src/demos/*/ | xargs -n1 basename > $OUT/dirs.txt
cp $W/controls/*.html dist/
step preview
(setsid nohup npx vite preview --host 127.0.0.1 --port 4173 > $OUT/preview.log 2>&1 &)
for i in $(seq 30); do curl -sf -o /dev/null http://127.0.0.1:4173/ && break; sleep 1; done
curl -sf -o /dev/null http://127.0.0.1:4173/ctl-pos.html || die preview; ok preview
step browser
(cd $W/r && npm init -y >/dev/null && npm i -s playwright@1.48.2 >/dev/null 2>&1 \
  && npx playwright install --with-deps chromium > $OUT/pw-install.log 2>&1 \
  && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ffmpeg >/dev/null 2>&1) || die browser; ok browser
step render
(cd $W/r && node render_all.cjs http://127.0.0.1:4173 $OUT ctl-pos.html ctl-neg.html $TARGETS > $OUT/render.log 2>&1) || die render; ok render
step encode
for f in $OUT/*.webm; do
  ffmpeg -loglevel error -y -i "$f" -c:v libx264 -crf 18 -pix_fmt yuv420p "${f%.webm}.mp4" && rm "$f"
done
rmdir $OUT/video-raw 2>/dev/null; ok encode
echo done > $W/status
