#!/usr/bin/env bash
# Regenerate every file in media/ from the judge's own output
# (cookbook/DEMO-STANDARD.md: media must be reproducible, not hand-edited).
#
#   1. collect_data.sh   judge/setup.sh must have run first: grades the
#                        known-good controller, the 8 mutants and the
#                        agent-loop replay with `grade.sh --json` and
#                        `grade.sh --trace`, and runs the self-test.
#                        Writes media/data/{verdicts,traces,selftest.txt}
#                        and media/work/ (the judged scene, for renders).
#   2. fig_result.py     media/result.png
#   3. fig_loop.py       media/loop.png
#   4. vid_render.py     the 3D frames of the video (real headless MuJoCo
#                        renders, software rasterised -- slow, so it is a
#                        separate resumable step: a frame that already
#                        exists is skipped).
#   5. make_video.py     composites the frames with the figures into
#                        media/demo.mp4 (and a lossless master under
#                        media/master/, which git ignores).
#
# Everything is pinned by media/requirements.txt; the renders use the same
# pinned MuJoCo that graded the trajectory.  Headless GL: EGL if the host
# has it (a /dev/dri node), otherwise OSMesa.
set -euo pipefail
MEDIA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$MEDIA"

if [ -z "${MUJOCO_GL:-}" ]; then
    if [ -d /dev/dri ]; then export MUJOCO_GL=egl; else export MUJOCO_GL=osmesa; fi
fi
echo "make_media: MUJOCO_GL=$MUJOCO_GL"

PY=python3
command -v "$PY" >/dev/null || { echo "make_media: python3 not found" >&2; exit 1; }

step() { printf '\n== %s ==\n' "$*"; }

step "collect_data.sh (judge outputs)"
bash ./collect_data.sh

step "fig_result.py -> result.png"
"$PY" ./fig_result.py

step "fig_loop.py -> loop.png"
"$PY" ./fig_loop.py

step "vid_render.py -> frames/ (3D renders; slow)"
# The shot list is the single source of truth in vid_render.py; ask it.
"$PY" - <<'PYPY'
import subprocess, sys, os
sys.path.insert(0, os.getcwd())
import vid_render
for shot, (_trace, n, _spec) in vid_render.shots().items():
    print(f"  {shot}: {n} frames")
PYPY
for shot in $("$PY" -c "import sys,os; sys.path.insert(0,'.'); import vid_render; print(' '.join(vid_render.shots()))"); do
    n=$("$PY" -c "import sys; sys.path.insert(0,'.'); import vid_render; print(vid_render.shots()['$shot'][1])")
    "$PY" ./vid_render.py "$shot" 0 "$n"
done

step "make_video.py -> demo.mp4"
"$PY" ./make_video.py

step "video_gate.py"
GATE="$(mktemp)"
git -C "$(git -C "$MEDIA" rev-parse --show-toplevel)" show \
    origin/main:cookbook/tools/video_gate.py > "$GATE" 2>/dev/null || true
if [ -s "$GATE" ]; then
    "$PY" "$GATE" ./demo.mp4
else
    echo "make_media: cookbook/tools/video_gate.py not in origin/main; skipped"
fi
rm -f "$GATE"

printf '\nmake_media: done -> %s\n' "$MEDIA"
