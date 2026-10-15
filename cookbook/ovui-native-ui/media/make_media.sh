#!/usr/bin/env bash
# media/make_media.sh -- regenerate every shipped media file from real
# judge outputs.  Idempotent: run from the repo root or the demo dir.
#
#   bash media/make_media.sh
#
# Requires: judge venv (judge/setup.sh), ffmpeg, and network the first
# time (to install the pinned matplotlib stack).  Produces:
#
#   media/result.png, media/loop.png     figures (real judge numbers)
#   media/demo.mp4                       the 20-60 s walkthrough video
#   media/MANIFEST.json                  what each file shows + sha256s
#   media/data/*.json|png                the underlying real judge outputs
#
# media/master/ holds the lossless video master (-crf 0); git ignores it.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$HERE/.." && pwd)"
TOOLS_DIR="${TOOLS_DIR:-$HOME/tools/ovui-native-ui}"
VENV="$TOOLS_DIR/venv"
STUB="$TOOLS_DIR/cuda-stub"
MVENV="$HERE/.venv"

[ -x "$VENV/bin/python" ] || { echo "run judge/setup.sh first" >&2; exit 2; }
command -v ffmpeg >/dev/null || { echo "ffmpeg not installed" >&2; exit 2; }

# -- the pinned matplotlib stack (judge venv pins live in judge/requirements)
if [ ! -x "$MVENV/bin/python" ]; then
  python3 -m venv "$MVENV"
  "$MVENV/bin/pip" install --no-cache-dir --require-hashes \
    -r "$HERE/requirements.txt"
fi

# -- 1. real judge outputs -> media/data/ ---------------------------------
"$MVENV/bin/python" -I "$HERE/make_data.py" "$DEMO" "$VENV/bin/python" "$STUB"

# -- 2. the real camera frames the video is cut from (needs the judge venv,
#      which has omni.ui) -> media/.frames/ (git-ignored) ---------------
rm -rf "$HERE/.frames"
(cd "$DEMO" && LD_LIBRARY_PATH="$STUB:${LD_LIBRARY_PATH:-}" \
    OMNIUI_HEADLESS=1 OMNIUI_LAVAPIPE=1 OMNIUI_BACKEND=vulkan \
    "$VENV/bin/python" -I "$HERE/make_frames.py" "$DEMO" "$HERE/.frames")

# -- 3. figures ------------------------------------------------------------
"$MVENV/bin/python" -I "$HERE/make_figures.py"

# -- 4. video (lossless master + web encode) -------------------------------
"$MVENV/bin/python" -I "$HERE/make_video.py"

# -- 5. manifest (sha256s of what we just wrote) ----------------------------
"$MVENV/bin/python" -I "$HERE/make_manifest.py"

echo "make_media.sh: done"
