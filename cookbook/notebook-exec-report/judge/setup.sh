#!/usr/bin/env bash
# notebook-exec-report judge: install the pinned toolchain idempotently.
#
# The judge executes the artifact under test with nbclient on an ipykernel
# "python3" kernel, and refits the model with its own stdlib oracle.  Those
# wheels (numpy / scipy / scikit-learn / pandas / matplotlib / the Jupyter
# stack) are pinned in judge/requirements.txt with sha256 hashes and
# installed into ~/.judge-venv with --require-hashes, so the exact bytes
# PyPI served at pin time are the only bytes that can install.
#
# The pinned interpreter is CPython 3.12 (the version this demo was built
# and calibrated against); setup.sh refuses anything else so the numbers in
# SPEC.md stay reproducible.  No pin was published in the two weeks before
# the demo was written (cutoff 2026-09-30, enforced by judge/genlock.py).
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HOME/.judge-venv"
WANT_MINOR="3.12"

python3 - <<'EOF' || { echo "setup: python3 >= 3.10 required" >&2; exit 1; }
import sys
assert sys.version_info >= (3, 10), sys.version
EOF

# --- the pinned interpreter ------------------------------------------
have="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if [ "$have" != "$WANT_MINOR" ]; then
    echo "setup: system python3 is $have, this demo pins $WANT_MINOR" >&2
    echo "setup: (the judge's calibration numbers assume $WANT_MINOR)" >&2
    exit 1
fi

# --- the pinned venv --------------------------------------------------
# requirements.txt is hash-pinned; idempotence check is cheap: if the venv
# already imports every direct pin at the exact version, skip the install.
if [ ! -x "$VENV/bin/python" ] || ! "$VENV/bin/python" - <<'EOF' 2>/dev/null
import importlib.metadata as im
pins = {
    "numpy": "2.5.3", "scipy": "1.18.1", "scikit-learn": "1.9.1",
    "pandas": "3.0.6", "matplotlib": "3.11.2", "nbclient": "0.11.0",
    "nbformat": "5.11.1", "nbconvert": "7.17.1", "ipykernel": "7.4.0",
    "jupyter-client": "8.10.0", "traitlets": "5.16.1",
}
for name, want in pins.items():
    if im.version(name) != want:
        raise SystemExit(1)
EOF
then
    echo "setup: creating $VENV and installing judge/requirements.txt"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --disable-pip-version-check --no-cache-dir \
        --require-hashes -r "$JDIR/requirements.txt"
else
    echo "setup: $VENV already holds the pinned toolchain (skipping install)"
fi

# --- record what actually installed ----------------------------------
echo "setup: tool versions"
{
    echo "# notebook-exec-report judge: versions installed by judge/setup.sh"
    echo "# ($(uname -sm))"
    echo "python3 $(python3 --version | awk '{print $2}')"
    "$VENV/bin/python" - <<'EOF'
import importlib.metadata as im
names = ["numpy", "scipy", "scikit-learn", "pandas", "matplotlib",
         "nbclient", "nbformat", "nbconvert", "ipykernel",
         "jupyter-client", "traitlets"]
for n in sorted(names):
    print(f"{n} {im.version(n)}")
EOF
} > "$JDIR/VERSIONS.txt"
cat "$JDIR/VERSIONS.txt"

# --- smoke: the venv can run a notebook end to end -------------------
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
SMOKE="$tmp/smoke.ipynb" "$VENV/bin/python" - <<'EOF'
import os
from nbclient import NotebookClient
import nbformat
nb = nbformat.from_dict({
    "cells": [{"cell_type": "code", "execution_count": None,
               "metadata": {}, "outputs": [],
               "source": "import numpy, pandas, sklearn, matplotlib\n"
                         "print('smoke', numpy.__version__)"}],
    "metadata": {"kernelspec": {"display_name": "Python 3",
                                "language": "python", "name": "python3"}},
    "nbformat": 4, "nbformat_minor": 5,
})
NotebookClient(nb, timeout=120, kernel_name="python3", allow_errors=False,
               resources={"metadata": {"path": os.path.dirname(
                   os.environ["SMOKE"])}}).execute()
text = "".join("".join(o.get("text", []))
               for o in nb.cells[0].outputs)
assert "smoke" in text, text
print("setup: nbclient smoke kernel OK (" + text.strip() + ")")
EOF
echo "setup: done"
