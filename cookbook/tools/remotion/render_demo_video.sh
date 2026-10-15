#!/usr/bin/env bash
# Demo-facing entry point: render_demo_video.sh <props.json> <out.mp4>
# See README.md for the props shape and system requirements.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec bash "$HERE/render.sh" "$@"
