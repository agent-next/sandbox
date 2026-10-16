#!/usr/bin/env bash
#
# collect-media-deps.sh -- install the terminal player's python deps.
#
# media/term.py replays the asciicast recordings through a terminal
# emulator (pyte) and rasterises each frame (Pillow).  Neither is part of
# the distro python, and term.py runs under `-I` (isolated mode, because the
# recordings are untrusted input) which drops the user site-packages.  So
# they are installed into media/.pylib/ -- next to term.py, never inside a
# directory an archive is extracted into.
#
# media/.pylib/ is git-ignored: it is a build input, not a source file.
# media/make_media.sh calls this; run it directly to refresh the deps.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="${HERE}/.pylib"

# Pinned to what the committed clips were rendered with: term.py's cell
# metrics come from the font, and a different Pillow can size a terminal
# cell differently enough to change the rendering.  wcwidth comes in as a
# pyte dependency and is pinned by pip's resolver, not listed here.
PINS="pyte==0.8.2 Pillow==12.3.0"

if [ -d "${LIB}" ] && [ -f "${LIB}/.pinned" ]; then
    want=$(echo "${PINS}" | tr ' ' '\n' | sort)
    have=$(cat "${LIB}/.pinned" 2>/dev/null | tr ' ' '\n' | sort)
    if [ "${want}" = "${have}" ]; then
        echo "collect-media-deps: ${LIB} already holds ${PINS}"
        exit 0
    fi
fi

python3 -m pip install --quiet --no-cache-dir \
    --target "${LIB}" ${PINS}
echo "${PINS}" > "${LIB}/.pinned"
echo "collect-media-deps: installed ${PINS} into ${LIB}"
