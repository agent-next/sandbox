#!/bin/sh
# Install the pinned judge toolchain into $HOME/.venvs/gpu-llm-batch-eval.
#
# The judge proper (grade.sh -> _grade.py -> extract.py) imports only the
# Python standard library, so a machine that only ever *grades* needs no
# third-party package at all. The venv exists because the same interpreter
# runs the real artifact (examples/good/eval.py) when a bundle is
# regenerated, and because the judge pins its own interpreter rather than
# trusting whatever `python3` the sandbox happens to have.
#
# Everything comes from judge/requirements.lock with exact versions and
# sha256 hashes, enforced by pip's --require-hashes: nothing unpinned is
# installed and nothing is a `latest` tag. Idempotent: an existing venv
# that already provides the pinned versions is left untouched.
#
#   pip install --require-hashes -r judge/requirements.lock
#
# Two index URLs are needed because the CPU-only torch wheel is published
# on the PyTorch index, not on PyPI; the pin records torch==2.10.0+cpu.

set -eu

VENV="$HOME/.venvs/gpu-llm-batch-eval"
HERE=$(cd "$(dirname "$0")" && pwd)
LOCK="$HERE/requirements.lock"
PYPI="https://download.pytorch.org/whl/cpu"
EXTRA="https://pypi.org/simple"

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

if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" - <<'EOF'
import importlib.util as u
def ver(name):
    spec = u.find_spec(name)
    if spec is None:
        return None
    return getattr(__import__(name), "__version__", "")
ok = ver("torch") == "2.10.0+cpu" and ver("transformers") == "4.57.6"
import sys
sys.exit(0 if ok else 1)
EOF
then
    echo "setup.sh: venv already provides the pinned toolchain"
else
    echo "setup.sh: creating venv at $VENV"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --quiet --upgrade "pip==25.0.1"
    "$VENV/bin/pip" install --quiet --require-hashes \
        --index-url "$PYPI" --extra-index-url "$EXTRA" -r "$LOCK"
fi

# Record what was actually installed, with versions, for RECEIPT.md.
{
    printf '## python %s (venv %s)\n' \
        "$("$VENV/bin/python" -c 'import sys; print(sys.version.split()[0])')" \
        "$VENV"
    printf '## torch %s\n' \
        "$("$VENV/bin/python" -c 'import torch; print(torch.__version__)')"
    printf '## transformers %s\n' \
        "$("$VENV/bin/python" -c 'import transformers; print(transformers.__version__)')"
    "$VENV/bin/pip" freeze --all
} > "$HERE/VERSIONS.txt"

echo "setup.sh: ok"
