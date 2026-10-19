#!/usr/bin/env bash
# Install pinned tools for the climate-glacier-model demo, idempotently.
#
# The artifact (model.py) needs numpy + matplotlib; the JUDGE is stdlib-only
# and imports neither.  Everything is pinned to an exact version and a
# sha256 in judge/requirements.txt and installed into a venv under $HOME,
# so no system Python is touched and a re-run is a no-op.
#
# No apt packages are installed: this image's apt lists may be empty and
# everything needed is a manylinux wheel.
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${GLACIER_VENV:-$HOME/glacier-venv}"

python3 - <<'EOF' || { echo "setup: python3 >= 3.10 required" >&2; exit 1; }
import sys
assert sys.version_info >= (3, 10), sys.version
EOF

# Idempotence: fast metadata check (no imports) of the two top-level pins.
if [ -x "$VENV/bin/python" ] &&
   [ "$("$VENV/bin/python" -c \
        'import importlib.metadata as m;print(m.version("numpy"),m.version("matplotlib"))' \
        2>/dev/null)" = "2.2.6 3.10.6" ]
then
    echo "setup: venv $VENV already has the pinned versions (skipping install)"
else
    echo "setup: creating venv $VENV"
    rm -rf "$VENV"
    python3 -m venv "$VENV"
    echo "setup: installing pinned wheels (sha256-checked by pip --require-hashes)"
    "$VENV/bin/pip" install --quiet --disable-pip-version-check \
        --no-cache-dir --require-hashes -r "$JDIR/requirements.txt"
fi

# Report and record what is actually installed.
"$VENV/bin/python" - <<'EOF'
import numpy, matplotlib, sys
print(f"setup: python {sys.version.split()[0]}")
print(f"setup: numpy {numpy.__version__}")
print(f"setup: matplotlib {matplotlib.__version__}")
EOF

{
    echo "# climate-glacier-model: versions installed by judge/setup.sh"
    echo "# ($(uname -sm), glibc $(ldd --version | head -1 | awk '{print $NF}'))"
    echo "python3 $(python3 --version | awk '{print $2}')"
    echo "venv $VENV"
    "$VENV/bin/python" -c 'import numpy,matplotlib;print("numpy",numpy.__version__);print("matplotlib",matplotlib.__version__)'
} > "$JDIR/VERSIONS.txt"
echo "setup: wrote $JDIR/VERSIONS.txt"
echo "setup: done"
