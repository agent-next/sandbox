#!/bin/sh
# Install the pinned judge toolchain into $HOME/.venvs/gpu-video-upscale.
#
# Tried in the order the demo standard requires:
#   1. official release tarball — the Real-ESRGAN x4plus weights are already
#      committed under data/weights/ (upstream release v0.1.0, sha256
#      verified at build time and re-verified by the judge every grade);
#   2. pip wheels with exact versions — torch 2.14.1+cpu and numpy 2.4.3
#      from judge/requirements-cpu.lock, installed with --require-hashes;
#   3. Debian packages — ffmpeg only if it is not already on PATH.
#
# Idempotent: an existing venv that already provides the pinned versions is
# left untouched. Refuses unsupported platforms (x86-64 Linux, CPython
# 3.10-3.13).

set -eu

VENV="$HOME/.venvs/gpu-video-upscale"
HERE=$(cd "$(dirname "$0")" && pwd)
LOCK="$HERE/requirements-cpu.lock"

case "$(uname -s):$(uname -m)" in
    Linux:x86_64) ;;
    *) echo "setup.sh: unsupported platform $(uname -s) $(uname -m) \
(supported: x86-64 Linux, CPython 3.10-3.13)" >&2; exit 2 ;;
esac

case "$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')" in
    3.10|3.11|3.12|3.13) ;;
    *) echo "setup.sh: unsupported Python \
$(python3 -c 'import sys; print(sys.version.split()[0])') (supported: 3.10-3.13)" >&2
       exit 2 ;;
esac

# --- 1. weights: verify the committed pinned checkpoint -----------------
WEIGHTS="$HERE/../data/weights/RealESRGAN_x4plus.pth"
WANT_W="4fa0d38905f75ac06eb49a7951b426670021be3018265fd191d2125df9d682f1"
if [ -f "$WEIGHTS" ]; then
    GOT_W=$(sha256sum "$WEIGHTS" | cut -d' ' -f1)
    if [ "$GOT_W" != "$WANT_W" ]; then
        echo "setup.sh: pinned weights sha256 mismatch: $GOT_W" >&2
        exit 1
    fi
    echo "setup.sh: pinned Real-ESRGAN_x4plus.pth verified (sha256 $WANT_W)"
else
    echo "setup.sh: MISSING $WEIGHTS — commit the pinned checkpoint first" >&2
    exit 1
fi

# --- 2. pip closure ------------------------------------------------------
if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" - <<EOF
import importlib.util as u
def have(name, ver):
    m = u.find_spec(name)
    return m is not None and getattr(__import__(name), "__version__", "") == ver
import sys
sys.exit(0 if have("torch", "2.14.1+cpu") and have("numpy", "2.4.3") else 1)
EOF
then
    echo "setup.sh: venv already provides the pinned toolchain (cpu)"
else
    echo "setup.sh: creating venv at $VENV (cpu closure)"
    python3 -m venv "$VENV"
    # shellcheck disable=SC2086
    "$VENV/bin/pip" install --quiet --upgrade pip==26.2.1
    "$VENV/bin/pip" install --require-hashes -r "$LOCK"
fi

# --- 3. ffmpeg -----------------------------------------------------------
FFMPEG_VER=""
if command -v ffmpeg >/dev/null 2>&1; then
    FFMPEG_VER=$(ffmpeg -version 2>/dev/null | head -1)
    echo "setup.sh: ffmpeg already on PATH: $FFMPEG_VER"
else
    echo "setup.sh: ffmpeg missing; apt-get install"
    if ! apt-get update >&2; then
        echo "setup.sh: apt-get update FAILED (no network or no apt lists)" >&2
        exit 1
    fi
    # this image's apt lists may be empty: check update actually fetched lists
    if [ -z "$(find /var/lib/apt/lists -name '*Packages*' -size +0 2>/dev/null | head -1)" ]; then
        echo "setup.sh: apt-get update fetched no package lists; cannot install ffmpeg" >&2
        exit 1
    fi
    apt-get install -y ffmpeg >&2
    FFMPEG_VER=$(ffmpeg -version 2>/dev/null | head -1)
    echo "setup.sh: installed $FFMPEG_VER"
fi

# --- record what was actually installed ----------------------------------
"$VENV/bin/pip" list --format=freeze > "$HERE/VERSIONS.txt"
{
    printf '## judge toolchain: torch 2.14.1+cpu, numpy 2.4.3 (pypi wheels, --require-hashes)\n'
    printf '## ffmpeg: %s\n' "${FFMPEG_VER:-not installed}"
    printf '## python: %s\n' "$("$VENV/bin/python" -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')"
} >> "$HERE/VERSIONS.txt"

echo "setup.sh: ok (cpu)"
