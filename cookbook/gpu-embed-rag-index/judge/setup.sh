#!/bin/sh
# Install the pinned judge toolchain into $HOME/.venvs/gpu-embed-rag-index.
#
# CPU machines (default, incl. this builder sandbox) get the small torch
# 2.3.1+cpu closure. A machine with a real NVIDIA GPU gets the CUDA closure
# (same versions, CUDA wheels) so the judge's full mode works.
# Both come from judge/requirements.lock, sha256-checked via pip's
# --require-hashes; nothing is installed unpinned. Idempotent: an existing
# venv that already provides the pinned versions is left untouched.

set -eu

VENV="$HOME/.venvs/gpu-embed-rag-index"
HERE=$(cd "$(dirname "$0")" && pwd)

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

# CUDA closure only when pip can see a working NVIDIA driver stack.
LABEL="cpu"
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1 \
   && [ -n "$(nvidia-smi -L 2>/dev/null)" ]; then
    LABEL="cuda"
fi

if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" - <<EOF
import sys
sys.path.insert(0, "$VENV/lib")
import importlib.util as u
def have(name, ver):
    m = u.find_spec(name)
    return m is not None and getattr(__import__(name), "__version__", "") == ver
sys.exit(0 if have("torch", "2.3.1+cpu" if "$LABEL" == "cpu" else "2.3.1")
           and have("sentence_transformers", "2.7.0")
           and have("faiss", "1.8.0") else 1)
EOF
then
    echo "setup.sh: venv already provides the pinned toolchain ($LABEL)"
else
    echo "setup.sh: creating venv at $VENV ($LABEL closure)"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --quiet --upgrade pip==24.0
    "$VENV/bin/pip" install --require-hashes -r "$HERE/requirements.lock"
fi

# Record what was actually installed, with versions, for RECEIPT.md.
"$VENV/bin/pip" list --format=freeze > "$HERE/VERSIONS.txt"
printf '## torch build: %s (torch %s, sentence-transformers %s, faiss %s, python %s)\n' "$LABEL" \
    "$("$VENV/bin/python" -c 'import torch; print(torch.__version__)')" \
    "$("$VENV/bin/python" -c 'import sentence_transformers; print(sentence_transformers.__version__)')" \
    "$("$VENV/bin/python" -c 'import faiss; print(faiss.__version__)')" \
    "$("$VENV/bin/python" -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')" \
    > "$HERE/VERSIONS.brief"
cat "$HERE/VERSIONS.brief" "$HERE/VERSIONS.txt" > "$HERE/VERSIONS.tmp"
mv "$HERE/VERSIONS.tmp" "$HERE/VERSIONS.txt"
rm -f "$HERE/VERSIONS.brief"

echo "setup.sh: ok ($LABEL)"
