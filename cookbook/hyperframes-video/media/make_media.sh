#!/usr/bin/env bash
# media/make_media.sh — regenerate every committed media file from the
# composition source via the pinned judge toolchain (judge/setup.sh).
#
#   demo.mp4    web encode of the HyperFrames render (h264 crf 18, < 8 MB)
#   result.png  poster frame (beat 1, self-typing editor + toast)
#   strip.png   6-frame strip across all beats
#   MANIFEST.json  sha256 + provenance for each committed file
#
# The composition source is never post-edited: demo.mp4 is a straight
# transcode of the hyperframes render.  The lossless-ish master stays in
# media/master/ (gitignored).
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "$DIR")"
MASTER="$DIR/master"
mkdir -p "$MASTER"

ENV_FILE="$HOME/.hyperframes-judge/env.sh"
if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE"
fi
command -v ffmpeg >/dev/null || { echo "ffmpeg missing — run judge/setup.sh" >&2; exit 1; }

# --- render the composition (scratch copy + vendored gsap) -----------------
WORK="$(mktemp -d /tmp/hf-media.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT
cp -a "$DEMO/examples/good/composition" "$WORK/comp"
cp "$DEMO/judge/vendor/gsap.min.js" "$WORK/comp/"

HF_BIN="${HYPERFRAMES_BIN:-$(command -v hyperframes)}"
HF_NODE="${HF_NODE:-node}"
echo "[media] rendering examples/good -> master/output.mp4"
"$HF_NODE" "$HF_BIN" render "$WORK/comp" -o "$MASTER/output.mp4" -f 30 -w 2

# --- web encode -------------------------------------------------------------
echo "[media] encoding demo.mp4 (h264 crf 18, faststart)"
ffmpeg -v error -y -i "$MASTER/output.mp4" \
    -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p -movflags +faststart \
    -an "$DIR/demo.mp4"
SIZE=$(stat -c %s "$DIR/demo.mp4")
echo "[media] demo.mp4 = $((SIZE / 1024)) KiB"
if [[ $SIZE -gt 8000000 ]]; then
    echo "[media] over 8 MB — re-encoding at crf 23" >&2
    ffmpeg -v error -y -i "$MASTER/output.mp4" \
        -c:v libx264 -crf 23 -preset slow -pix_fmt yuv420p -movflags +faststart \
        -an "$DIR/demo.mp4"
fi

# --- poster + frame strip -----------------------------------------------------
ffmpeg -v error -y -ss 6.9 -i "$DIR/demo.mp4" -frames:v 1 "$DIR/result.png"
ffmpeg -v error -y -i "$DIR/demo.mp4" -vf \
    "select='eq(n\,45)+eq(n\,159)+eq(n\,285)+eq(n\,419)+eq(n\,537)+eq(n\,578)',scale=640:360,tile=3x2" \
    -frames:v 1 "$DIR/strip.png"

# --- manifest -----------------------------------------------------------------
python3 - "$DIR" <<'PY'
import hashlib, json, os, sys
media = sys.argv[1]
meta = {
    "demo.mp4": (
        "20 s 1920x1080@30 product teaser rendered by HyperFrames from "
        "examples/good/composition (kinetic type, self-typing UI mockup, "
        "animated counter/chart, live search filter, eased end card)",
        "hyperframes render examples/good/composition -o master/output.mp4 "
        "-f 30 -w 2; ffmpeg -i master/output.mp4 -c:v libx264 -crf 18 "
        "-preset slow -pix_fmt yuv420p -movflags +faststart demo.mp4",
        "examples/good/composition/index.html rendered by hyperframes "
        "0.8.61 (chrome-headless-shell 152.0.7977.30)"),
    "result.png": (
        "poster frame at t=6.9s: beat 1 'Capture ideas in one keystroke' "
        "with the self-typed note and the capture toast",
        "ffmpeg -ss 6.9 -i demo.mp4 -frames:v 1 result.png",
        "media/demo.mp4"),
    "strip.png": (
        "six frames across the teaser: title, quick capture, sync counter, "
        "search filter, end card (3x2, 640x360 tiles)",
        "ffmpeg -i demo.mp4 -vf select+scale=640:360,tile=3x2 strip.png "
        "(frames 45,159,285,419,537,578)",
        "media/demo.mp4"),
}
out = {"files": []}
for name, (shows, cmd, src) in meta.items():
    h = hashlib.sha256(open(os.path.join(media, name), "rb").read())
    out["files"].append({"file": name, "shows": shows,
                         "command": cmd, "source": src,
                         "sha256": h.hexdigest()})
with open(os.path.join(media, "MANIFEST.json"), "w") as f:
    json.dump(out, f, indent=2)
    f.write("\n")
print("[media] MANIFEST.json written")
PY
echo "[media] done"
