#!/usr/bin/env bash
#
# make_media.sh -- the demo's media are real-run frames, not renders.
#
# The task brief defers the final video/figure production to a later media
# step; what ships under media/ is a small set of real PNG frames (< 300 KB
# each) captured from the actual good run:
#
#   rea-analyze-checksum.png   REA `analyze` evidence JSON for checksum
#   rea-function-keycheck.png  REA `function`/`decompile` on keycheck 0x1011f0
#   binary-vs-reimpl.png       table of real binary vs reimpl.py outputs
#   judge-verdict.png          grade.sh listing all 21 gates PASS
#
# None of them is synthesized. A true render-the-movie script is not part
# of this step; what this script does is re-run the underlying commands so
# the frame sources are fresh, leaving an operator to re-capture.

set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "${HERE}")"

echo "make_media: frames in ${HERE} are real-run captures (see MANIFEST.json)"
echo "make_media: re-running the source commands to refresh the frame inputs"
echo

echo "--- rea analyze (checksum) -> evidence the frame shows"
( cd "${DEMO}" && . ./env.sh && \
  rea analyze targets/checksum --detail detailed --format json | sha256sum )

echo "--- differential spot-check rows (seed 20261014)"
( cd "${DEMO}" && printf 'hello' | targets/checksum )
( cd "${DEMO}" && printf 'hello' | python3 examples/good/checksum/reimpl.py )
( cd "${DEMO}" && ./targets/keycheck < examples/good/keycheck/key.txt )

echo "--- judge verdict (the frame source)"
( cd "${DEMO}" && bash judge/grade.sh examples/good --seed 20261014 | head -30 )

echo
echo "make_media: done; re-capture media/*.png from the terminal as needed"
