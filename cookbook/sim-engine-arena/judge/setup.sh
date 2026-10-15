#!/bin/sh
# Install the pinned judge toolchain into $HOME/.venvs/sim-engine-arena.
#
# One closure, pinned in requirements.lock (mujoco 3.8.1 to match the GPU
# lease image, numpy 2.5.3 under the date rule), sha256-checked via pip's
# --require-hashes. Idempotent: an existing venv that already provides the
# pinned versions is left untouched.

set -eu

VENV="$HOME/.venvs/sim-engine-arena"
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

if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" - <<EOF
import sys
sys.path.insert(0, "$VENV/lib")
import importlib.util as u
def have(name, ver):
    m = u.find_spec(name)
    return m is not None and getattr(__import__(name), "__version__", "") == ver
sys.exit(0 if have("mujoco", "3.8.1") and have("numpy", "2.5.3") else 1)
EOF
then
    echo "setup.sh: venv already provides the pinned toolchain"
else
    echo "setup.sh: creating venv at $VENV"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --quiet --upgrade pip==25.0.1
    "$VENV/bin/pip" install --require-hashes -r "$HERE/requirements.lock"
fi

# Record what was actually installed, with versions, for RECEIPT.md.
"$VENV/bin/pip" list --format=freeze > "$HERE/VERSIONS.txt"
printf '## python %s, mujoco %s, numpy %s\n' \
    "$("$VENV/bin/python" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')" \
    "$("$VENV/bin/python" -c 'import mujoco; print(mujoco.__version__)')" \
    "$("$VENV/bin/python" -c 'import numpy; print(numpy.__version__)')" \
    > "$HERE/VERSIONS.brief"
cat "$HERE/VERSIONS.brief" "$HERE/VERSIONS.txt" > "$HERE/VERSIONS.tmp"
mv "$HERE/VERSIONS.tmp" "$HERE/VERSIONS.txt"
rm -f "$HERE/VERSIONS.brief"

echo "setup.sh: ok"
