#!/usr/bin/env bash
# media/video/render_clips.sh — turn judge output into the three real motion
# clips the Remotion composition plays (30 fps H.264 in media/clips/).
#
# Steps (all data from THIS run's judge output):
#   1. replay the good cavity case with --trace (saved time dirs + residuals)
#   2. render each time dir as a |U| field with flowing streamlines
#      (VTK OpenFOAMReader offscreen, Xvfb — no ParaView install needed)
#   3. encode hook.mp4 (field developing t=0->30s)
#   4. encode cavity.mp4 (same field, camera zoom + sweep)
#   5. encode agent.mp4 from make_media.sh's selftest trace (54 s -> 8 s)
# ffmpeg only encodes/decodes here; every pixel of motion comes from VTK.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEDIA="$(dirname "$HERE")"
DEMO="$(dirname "$MEDIA")"
REPLAY="$MEDIA/judge_runs/replay"
CLIPS="$MEDIA/clips"
PY="${PYTHON:-python3}"

mkdir -p "$CLIPS" "$REPLAY"

echo "=== 1. replay the good cases (dense trace for the video) ==="
grade() { bash "$DEMO/judge/grade.sh" "$@"; }
rm -rf "$REPLAY/cavity_traces" "$REPLAY/verdicts"
grade "$DEMO/examples/good/cavity" \
    --json "$REPLAY/verdicts/04_cavity_good.json" --seed 42 \
    --trace "$REPLAY/cavity_traces" >/dev/null

echo "=== 2. render the field with VTK offscreen (Xvfb) ==="
if ! command -v Xvfb >/dev/null; then
    echo "render_clips: Xvfb required for headless VTK rendering" >&2; exit 1
fi
"$PY" - "$REPLAY/cavity_traces" "$HERE/vtk_frames" <<'PY'
import os, sys, glob
import numpy as np
from vtk.util.numpy_support import vtk_to_numpy

import vtk

trace, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)

cent = []
with open(os.path.join(trace, 'cellcentres.csv')) as f:
    for line in f:
        if line.startswith('x,y') or not line.strip():
            continue
        x, y = line.split(',')
        cent.append((float(x), float(y)))
X = np.array([c[0] for c in cent]); Y = np.array([c[1] for c in cent])

times = sorted((d for d in os.listdir(trace)
                if d.replace('.', '', 1).isdigit()
                and os.path.isdir(os.path.join(trace, d))),
               key=float)

src = vtk.vtkOpenFOAMReader()
src.SetFileName(os.path.join(trace, '..', 'cavity.foam'))  # set below
src.EnableAllCellArrays()
src.Update()
ds = src.GetOutput()

# find the internal-mesh block (the one whose U array length == len(cent))
internal = None
for bi in range(ds.GetNumberOfBlocks()):
    b = ds.GetBlock(bi)
    if b is None or b.GetNumberOfCells() == 0:
        continue
    if b.GetCellData().GetArray('U') is None:
        continue
    if b.GetNumberOfCells() == len(cent):
        internal = b
        break
if internal is None:
    sys.exit('render_clips: internal mesh block not found')

# probe one U read to find the time->block mapping
ntimes = src.GetNumberOfTimeSteps()
print('[vtk] time steps:', ntimes, 'cells:', internal.GetNumberOfCells())
PY
echo "render_clips: probe done"
