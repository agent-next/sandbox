#!/usr/bin/env bash
# Rebuild every committed media artefact of cookbook/cnc-gcode from the judge's
# own outputs:
#
#   media/result.png  media/make_result.py   (media/requirements.txt)
#   media/loop.png    media/make_loop.py     (media/requirements.txt)
#   media/demo.mp4    media/make_demo.py     (media/requirements-video.txt)
#
# Nothing here draws a number: each script reads media/data/, which the
# judge's own grade/selftest runs wrote (see media/collect_*.sh and
# media/README.md for the full provenance chain).
#
#   bash media/make_media.sh            # all three
#   bash media/make_media.sh result     # only result.png
#   bash media/make_media.sh loop       # only loop.png
#   bash media/make_media.sh demo       # only demo.mp4 (~25 min: 930 real
#                                       # renders, then a lossless master
#                                       # under media/master/, git-ignored)
#
# The media tools live in their own venv ($HOME/.cnc-gcode/mediavenv) so the
# judge's venv stays untouched.  demo.mp4 additionally needs a headless GL
# context: on Debian 12, 'apt install libegl1 libosmesa6' and make_demo.py's
# PYOPENGL_PLATFORM=egl does the rest (llvmpipe, no GPU, no display).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "$HERE")"
VENV="${HOME}/.cnc-gcode/mediavenv"
JENV="${HOME}/.cnc-gcode/venv"

WHAT="${1:-all}"

if [ ! -x "$VENV/bin/python" ]; then
    echo "make_media: creating $VENV (pinned, sha256-checked)"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --quiet --no-cache-dir --upgrade pip
    "$VENV/bin/pip" install --quiet --no-cache-dir --require-hashes \
        -r "$HERE/requirements.txt" -r "$HERE/requirements-video.txt"
fi

run_figure() {
    for f in "$@"; do
        [ -f "$HERE/data/$f" ] || {
            echo "make_media: media/data/$f missing -- see media/README.md" >&2
            exit 1
        }
    done
}

case "$WHAT" in
    result)
        run_figure trace_good/final.npz ref_compare.json \
                   replay/01_good.json replay/02_*.json
        "$VENV/bin/python" "$HERE/make_result.py"
        ;;
    loop)
        run_figure selftest.log replay/01_good.json replay/02_*.json
        "$VENV/bin/python" "$HERE/make_loop.py"
        ;;
    demo)
        run_figure trace_good/final.npz result.png loop.png selftest.log
        [ -d "$HERE/data/trace_mut" ] || {
            echo "make_media: media/data/trace_mut/ missing -- run" \
                 "'bash media/collect_mutant_traces.sh'" >&2
            exit 1
        }
        "$VENV/bin/python" "$HERE/make_demo.py"
        ;;
    all)
        "$0" result && "$0" loop && "$0" demo
        ;;
    *)
        echo "usage: bash media/make_media.sh [all|result|loop|demo]" >&2
        exit 2
        ;;
esac

# The judge's venv must still work: the media tools never touch it.
if [ -x "$JENV/bin/python" ] && [ "$WHAT" != "result" ]; then
    "$JENV/bin/python" -c 'import numpy' \
        || echo "make_media: WARNING: judge venv cannot import numpy" >&2
fi
echo "make_media: done ($WHAT)"