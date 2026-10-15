#!/bin/bash
# Rebuild every media artifact from the real judge outputs — media is
# reproducible, never hand-edited (cookbook/DEMO-STANDARD.md, Media).
#
# demo.mp4 storyboard slots, in order (fill in media/STORYBOARD.md first):
#   0-2 s       hook: the finished real result fills the frame
#               (no title card, logo, terminal, or blank chart)
#   2-10 s      input -> output: the prompt/spec/photo beside the result
#   10-35 s     escalate: camera moves, close-ups, the result stressed,
#               plus a sped-up agent run in the sandbox labelled "Nx speed"
#   then        proof: judge PASS + mutant kill matrix, in large text
#   last 2-3 s  end card: the one-line launch ("python3 run.py"), static
#
# Format: 16:9 master >= 1920x1080 (4K hero renders encouraged), 25-60 s,
# 30 fps, >= 0.8 scene cuts per 10 s, caption cap height >= 4 % of frame
# height. Every frame is real output from the pinned run; every number
# traces to RECEIPT.md. Check the encode with cookbook/tools/video_gate.py
# and judge it blind via media/REVIEW.json (Review panel rule).
set -euo pipefail
MEDIA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "TODO: implement media/make_media.sh in $MEDIA" >&2
exit 1
