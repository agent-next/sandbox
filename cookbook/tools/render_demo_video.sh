#!/bin/bash
# Render a cookbook demo video from a props file with the HyperFrames template
# (cookbook/tools/hyperframes/), then gate the result.
#
#     cookbook/tools/render_demo_video.sh <props.json> <out.mp4>
#
# props.json is the template's props shape, documented in
# cookbook/tools/hyperframes/README.md; validate it on its own with
#     python3 cookbook/tools/hyperframes/validate_props.py <props.json>
#
# Clip and glb paths in the props are resolved relative to the props file's own
# directory, so a demo keeps its media beside its props.
#
# Steps, each logged: npm ci (if needed) + vendor the pinned browser libs,
# validate the props, assemble a scratch render project, hyperframes render at
# 1920x1080 / 30 fps, an ffmpeg remux to faststart at CRF 18, a size-driven
# re-encode when the result is over 8 MiB, then video_gate.py. Exits non-zero on
# any failure, and non-zero when the gate fails — a demo whose video fails the
# gate is not done (cookbook/DEMO-STANDARD.md, Media).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HF_DIR="$HERE/hyperframes"
GATE="$HERE/video_gate.py"

PROPS="${1:?usage: render_demo_video.sh <props.json> <out.mp4>}"
OUT="${2:?usage: render_demo_video.sh <props.json> <out.mp4>}"

PROPS="$(cd "$(dirname "$PROPS")" && pwd)/$(basename "$PROPS")"
PROPS_DIR="$(dirname "$PROPS")"
mkdir -p "$(dirname "$OUT")"
OUT="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"

MAX_BYTES=$((8 * 1024 * 1024))
FPS=30

step() { printf '\n=== %s\n' "$*" >&2; }

WORK="$(mktemp -d)"
cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT

# --- 0. tooling ------------------------------------------------------------
step "step 0/7  tooling"
for tool in node npm ffmpeg ffprobe python3; do
  command -v "$tool" >/dev/null || { echo "render_demo_video: $tool not on PATH" >&2; exit 1; }
done
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
if [ "$NODE_MAJOR" -lt 22 ]; then
  echo "render_demo_video: node >= 22 required, found $(node -v)" >&2
  exit 1
fi
echo "node $(node -v), ffmpeg $(ffmpeg -version | head -1 | cut -d' ' -f3)"

# --- 1. dependencies + vendored runtime libs -------------------------------
step "step 1/7  npm ci + vendor pinned browser libs"
if [ ! -d "$HF_DIR/node_modules/hyperframes" ]; then
  ( cd "$HF_DIR" && npm ci )
else
  echo "node_modules present, skipping npm ci"
fi
bash "$HF_DIR/scripts/vendor_deps.sh"

# --- 2. props -> template variables ----------------------------------------
# The template reads its whole input as ONE string variable, so the props have
# to be embedded in a JSON string. python's json.dumps does the escaping.
step "step 2/7  validate props + build the variables file"
python3 "$HF_DIR/validate_props.py" "$PROPS"

# --- 3. assemble a scratch render project ----------------------------------
# The template tree is committed and read-only to a render; the props' media is
# not part of it. Assemble both under $WORK so clip paths can stay relative and
# the repo tree is never written to.
step "step 3/7  assemble scratch render project"
cp -R "$HF_DIR/index.html" "$HF_DIR/compositions" "$HF_DIR/vendor" \
      "$HF_DIR/fonts" "$WORK/"
ln -s "$HF_DIR/node_modules" "$WORK/node_modules"
mkdir -p "$WORK/media"
# The sub-composition's authored src is a placeholder; every render overrides
# it per shot through the variables. Copy the placeholder too so a render never
# fails a missing-asset check on a path that is never actually read.
cp "$HF_DIR/media/clip.mp4" "$WORK/media/clip.mp4"

python3 - "$PROPS" "$WORK" "$PROPS_DIR" <<'PY'
import json, os, shutil, sys

props_path, work, props_dir = sys.argv[1], sys.argv[2], sys.argv[3]
props = json.load(open(props_path, encoding="utf-8"))

# Copy every referenced media file into the project's media/ dir and rewrite
# the props to the relative path the renderer will serve.
def stage(p):
    src = p if os.path.isabs(p) else os.path.join(props_dir, p)
    src = os.path.realpath(src)
    if not os.path.isfile(src):
        raise SystemExit(f"render_demo_video: media not found: {p} (looked at {src})")
    dst = os.path.join(work, "media", os.path.basename(src))
    shutil.copyfile(src, dst)
    return f"media/{os.path.basename(src)}"

for shot in props.get("shots", []):
    if shot["clip"] != "model":
        shot["clip"] = stage(shot["clip"])
if "model3d" in props:
    props["model3d"]["glb"] = stage(props["model3d"]["glb"])

with open(os.path.join(work, "props.resolved.json"), "w") as fh:
    json.dump({"propsJson": json.dumps(props)}, fh)
print("  staged media:", sorted(os.listdir(os.path.join(work, "media"))))
PY

# --- 4. render -------------------------------------------------------------
step "step 4/7  hyperframes render (1920x1080, ${FPS} fps)"
RAW="$WORK/render.mp4"
( cd "$WORK" && \
  node "$HF_DIR/node_modules/.bin/hyperframes" render . \
    -o "$RAW" \
    --fps "$FPS" \
    --variables-file "$WORK/props.resolved.json" )

if [ ! -s "$RAW" ]; then
  echo "render_demo_video: hyperframes produced no output" >&2
  exit 1
fi
echo "  raw render: $(stat -c %s "$RAW") bytes"

# --- 5. remux to faststart at CRF 18 ---------------------------------------
step "step 5/7  ffmpeg remux (H.264 yuv420p, faststart, CRF 18)"
ffmpeg -y -v error -i "$RAW" \
  -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p \
  -movflags +faststart -an \
  "$OUT"

# --- 6. size guard ---------------------------------------------------------
step "step 6/7  size guard (<= 8 MiB)"
SIZE=$(stat -c %s "$OUT")
echo "  CRF 18: $SIZE bytes"
CRF=18
while [ "$SIZE" -gt "$MAX_BYTES" ] && [ "$CRF" -lt 30 ]; do
  CRF=$((CRF + 3))
  echo "  over $MAX_BYTES bytes -> re-encoding at CRF $CRF"
  ffmpeg -y -v error -i "$RAW" \
    -c:v libx264 -crf "$CRF" -preset slow -pix_fmt yuv420p \
    -movflags +faststart -an \
    "$OUT"
  SIZE=$(stat -c %s "$OUT")
  echo "  CRF $CRF: $SIZE bytes"
done
if [ "$SIZE" -gt "$MAX_BYTES" ]; then
  echo "render_demo_video: still over 8 MiB at CRF $CRF" >&2
  exit 1
fi

# --- 7. gate ---------------------------------------------------------------
step "step 7/7  video_gate.py"
python3 "$GATE" "$OUT"
