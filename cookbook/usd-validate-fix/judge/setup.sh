#!/usr/bin/env bash
# Install pinned tools for the usd-validate-fix judge, idempotently, into $HOME.
#
#   usd-core==25.5                 Pixar OpenUSD pip wheel (Apache-2.0-modified)
#   usd-validation-nvidia==1.22.0  NVIDIA validator, Apache-2.0 AND CC-BY-4.0,
#                                  the official PyPI release of commit
#                                  14a998c0445f33140f56879e165691c2955afca1
#                                  ("Publish public mirror v1.22.0", 2026-09-10)
#
# Both are hash-pinned in requirements.txt and installed with pip
# --require-hashes into a venv at $HOME/.usd-validate-fix-venv.  The judge
# needs Python 3.10-3.12 (the usd-core 25.5 wheels ship no cp313+ ABI).
#
# --make-assets additionally regenerates task/traffic_cone_broken.usda and
# examples/good/traffic_cone_fixed.usda with task/make_task.py (in place,
# deterministic; run from a clean tree and check git diff).
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$JDIR/.." && pwd)"
VENV="$HOME/.usd-validate-fix-venv"
PY=python3

MAKE_ASSETS=0
for a in "$@"; do
    case "$a" in
        --make-assets) MAKE_ASSETS=1 ;;
        *) echo "setup: unknown argument '$a'" >&2; exit 2 ;;
    esac
done

# --- python: need 3.10 <= version <= 3.12 --------------------------------
"$PY" - <<'EOF' || { echo "setup: python3 3.10-3.12 required (usd-core 25.5 wheel ABIs)" >&2; exit 1; }
import sys
assert (3, 10) <= sys.version_info[:2] <= (3, 12), sys.version
EOF

# --- venv (idempotent) ----------------------------------------------------
if [ -x "$VENV/bin/nvidia_usd_validate" ] && \
   "$VENV/bin/python" - <<'EOF' 2>/dev/null
import importlib.metadata as md
assert md.version("usd-core") == "25.5"
assert md.version("usd-validation-nvidia") == "1.22.0"
EOF
then
    echo "setup: venv $VENV already has the pinned versions (skipping install)"
else
    echo "setup: creating venv $VENV and installing pinned wheels"
    rm -rf "$VENV"
    "$PY" -m venv "$VENV"
    "$VENV/bin/python" -m pip install --disable-pip-version-check --quiet \
        --only-binary :all: --require-hashes -r "$JDIR/requirements.txt"
fi

# --- record what is actually installed ------------------------------------
VAL_VER="$("$VENV/bin/nvidia_usd_validate" --version 2>/dev/null | tail -1)"
USD_VER="$("$VENV/bin/python" -c 'import importlib.metadata as m; print(m.version("usd-core"))')"
{
    echo "# usd-validate-fix judge: versions installed by judge/setup.sh"
    echo "# ($(uname -sm))"
    echo "python3 $("$PY" --version 2>&1 | awk '{print $2}') (venv: $("$VENV/bin/python" --version 2>&1 | awk '{print $2}'))"
    echo "usd-core $USD_VER"
    echo "usd-validation-nvidia $( [ -n "$VAL_VER" ] && echo "$VAL_VER" || echo unknown)"
    echo "nvidia_usd_validate path: $VENV/bin/nvidia_usd_validate"
    "$VENV/bin/python" -m pip freeze
} > "$JDIR/VERSIONS.txt"
echo "setup: wrote $JDIR/VERSIONS.txt"

if [ "$MAKE_ASSETS" -eq 1 ]; then
    echo "setup: regenerating task assets with task/make_task.py"
    (cd "$DEMO" && "$VENV/bin/python" task/make_task.py)
fi

echo "setup: done"
