#!/bin/sh
# Regenerate every media file from real GPU runs. Needs SBX_API_KEY (GPU access),
# python3 with matplotlib + numpy, and ffmpeg. Work files go to media/work/ (ignored).
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WORK="$HERE/work"
rm -rf "$WORK"
python3 "$HERE/../run.py" --seed 17 --output "$WORK/run"
python3 "$HERE/frames.py" "$WORK/frames" --seed 17
python3 "$HERE/make_figures.py" "$WORK/run" "$WORK/frames"
