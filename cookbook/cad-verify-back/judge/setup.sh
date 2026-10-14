#!/usr/bin/env bash
# cookbook/cad-verify-back: install the pinned CAD toolchain idempotently.
#
# Installs (system-wide via pip, plus apt graphics libs):
#   - cadquery 2.7.0 (its OCCT kernel via cadquery-ocp 7.8.1.1.post1)
#   - ezdxf 1.4.4
# every wheel sha256-pinned in requirements.txt. Safe to re-run.
#
# Usage: bash judge/setup.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REQS="${HERE}/requirements.txt"

PY=python3

# ---------------------------------------------------------------------------
# apt: OCCT's shared libraries need the GL/X runtime present at import time.
# Pinned to Debian bookworm defaults; exact versions recorded in VERSIONS.txt.
# ---------------------------------------------------------------------------
apt_ensure() {
    if [ -e /usr/lib/x86_64-linux-gnu/libGL.so.1 ] \
        && [ -e /usr/lib/x86_64-linux-gnu/libGLU.so.1 ] \
        && [ -e /usr/lib/x86_64-linux-gnu/libXrender.so.1 ] \
        && [ -e /usr/lib/x86_64-linux-gnu/libxkbcommon.so.0 ] \
        && [ -e /usr/lib/x86_64-linux-gnu/libEGL.so.1 ]; then
        return 0
    fi
    echo "[setup] installing apt graphics libs (libgl1 libglu1-mesa libxrender1 libxkbcommon0 libegl1)"
    sudo apt-get update -qq
    sudo apt-get install -y -qq libgl1 libglu1-mesa libxrender1 libxkbcommon0 libegl1
}

# ---------------------------------------------------------------------------
# pip: exact pinned wheels, verified against requirements.txt hashes.
# pip refuses to install any wheel whose sha256 does not match the pin.
# ---------------------------------------------------------------------------
pip_ensure() {
    if "$PY" -c "import cadquery, ezdxf" >/dev/null 2>&1 \
        && [ "$("$PY" -c 'import cadquery; print(cadquery.__version__)' 2>/dev/null)" = "2.7.0" ] \
        && [ "$("$PY" -c 'import ezdxf; print(ezdxf.__version__)' 2>/dev/null)" = "1.4.4" ]; then
        echo "[setup] cadquery 2.7.0 + ezdxf 1.4.4 already installed"
        return 0
    fi
    echo "[setup] installing pinned python wheels (cadquery 2.7.0, ezdxf 1.4.4, occt via cadquery-ocp)"
    "$PY" -m pip install --require-hashes --no-deps -r "$REQS"
}

# ---------------------------------------------------------------------------
apt_ensure
pip_ensure

# record what actually landed (goes to stdout; VERSIONS.txt in repo is the
# record from the reference install)
echo "[setup] installed:"
"$PY" - <<'EOF'
import importlib.metadata as md
for pkg in ("cadquery", "cadquery-ocp", "ezdxf", "ocp"):
    try:
        print(f"  {pkg} {md.version(pkg)}")
    except md.PackageNotFoundError:
        pass
EOF
"$PY" -c "import cadquery, ezdxf; print('[setup] import check OK (headless)')"
echo "[setup] done."
