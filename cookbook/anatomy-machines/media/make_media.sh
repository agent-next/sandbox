#!/usr/bin/env bash
# media/make_media.sh — regenerate every file in media/ from the real figure.
#
# Uses the judge's own toolchain (judge/setup.sh must have run first):
# headless Chrome + SwiftShader renders the scene, Playwright screenshots
# #stageView at 1920x1080, ffmpeg encodes the frame series. The lossless
# master goes to media/master/ (git-ignored); demo.mp4 is the crf-18 web
# encode. MANIFEST.json records sha256 + provenance for each shipped file.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HOME/.anatomy-judge/venv"

if [[ ! -x "$VENV/bin/python" ]]; then
    echo "[media] ERROR: $VENV/bin/python missing — run judge/setup.sh first" >&2
    exit 2
fi
if ! command -v ffmpeg >/dev/null; then
    echo "[media] ERROR: ffmpeg not on PATH" >&2
    exit 2
fi

PLAYWRIGHT_BROWSERS_PATH="$HOME/.cache/ms-playwright" \
    "$VENV/bin/python" "$HERE/render_media.py" "$HERE"

echo "[media] done — files in $HERE"
