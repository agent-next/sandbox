#!/bin/sh
# Install the pinned judge toolchain into $HOME/.venvs/gpu-sim-sweep.
#
# Installs mujoco 3.8.1, mujoco-warp 3.8.1, warp-lang 1.13.0, numpy 1.26.4
# and the full transitive closure, every package pinned and sha256-verified
# through pip's --require-hashes mode (CPython 3.12, x86-64 Linux only).
# Idempotent: an existing venv that
# already provides the pinned versions is left untouched.

set -eu

VENV="$HOME/.venvs/gpu-sim-sweep"
HERE=$(cd "$(dirname "$0")" && pwd)

case "$(uname -s):$(uname -m)" in
    Linux:x86_64) ;;
    *) echo "setup.sh: unsupported platform $(uname -s) $(uname -m) \
(supported: x86-64 Linux, CPython 3.12)" >&2; exit 2 ;;
esac

case "$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')" in
    3.12) ;;
    *) echo "setup.sh: unsupported Python \
$(python3 -c 'import sys; print(sys.version.split()[0])') (supported: CPython 3.12)" >&2
       exit 2 ;;
esac

if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" - <<EOF
import sys
sys.path.insert(0, "$VENV/lib")
import importlib.util as u
def have(name, ver):
    m = u.find_spec(name)
    return m is not None and getattr(__import__(name), "__version__", "") == ver
sys.exit(0 if have("mujoco", "3.8.1") and have("mujoco_warp", "3.8.1")
           and have("warp", "1.13.0") and have("numpy", "1.26.4") else 1)
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
printf '## mujoco %s, mujoco-warp %s, warp %s, numpy %s, python %s\n' \
    "$("$VENV/bin/python" -c 'import mujoco; print(mujoco.__version__)')" \
    "$("$VENV/bin/python" -c 'import mujoco_warp; print(mujoco_warp.__version__)')" \
    "$("$VENV/bin/python" -c 'import warp; print(warp.__version__)')" \
    "$("$VENV/bin/python" -c 'import numpy; print(numpy.__version__)')" \
    "$("$VENV/bin/python" -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')" \
    > "$HERE/VERSIONS.brief"
cat "$HERE/VERSIONS.brief" "$HERE/VERSIONS.txt" > "$HERE/VERSIONS.tmp"
mv "$HERE/VERSIONS.tmp" "$HERE/VERSIONS.txt"
rm -f "$HERE/VERSIONS.brief"

echo "setup.sh: ok"
