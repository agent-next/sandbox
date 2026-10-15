#!/usr/bin/env bash
# media/make_media.sh — regenerate every media file from the judge outputs.
# Requires Python 3.10+, matplotlib and ffmpeg (prints versions first).
set -euo pipefail

MEDIA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "$MEDIA_DIR")"

echo "[media] tool versions:"
python3 --version
python3 -c "import matplotlib; print('matplotlib', matplotlib.__version__)"
ffmpeg -version | head -1

python3 "$MEDIA_DIR/make_media.py"
