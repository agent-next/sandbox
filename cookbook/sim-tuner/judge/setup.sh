#!/bin/sh
# Install the pinned judge toolchain into $HOME/.venvs/sim-tuner.
#
# The judge's acceptance oracle is CPU MuJoCo 3.8.1 + numpy 1.26.4, pinned
# with sha256 via pip's --require-hashes mode (judge/requirements.lock,
# CPython 3.10 - 3.13, x86-64 Linux). The GPU-side stack (mujoco-warp etc.)
# lives on the lease image and is validated, not installed: the first time
# you run against the reference image, run
#
#   judge/setup.sh --record
#
# which additionally leases a fresh 4 GiB slice, queries its stack versions
# and pins them to judge/version-table.json. Every later grade then fails if
# the served lease stack differs (see SPEC.md "Toolchain"). Idempotent: an
# existing venv with the pinned versions is left untouched.
set -eu

VENV="$HOME/.venvs/sim-tuner"
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

if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" - <<'EOF'
import importlib.util as u
import sys
def have(name, ver):
    m = u.find_spec(name)
    return m is not None and getattr(__import__(name), "__version__", "") == ver
numpy_version = "2.1.3" if sys.version_info[:2] == (3, 13) else "1.26.4"
sys.exit(0 if have("mujoco", "3.8.1") and have("numpy", numpy_version) else 1)
EOF
then
    echo "setup.sh: venv already provides the pinned toolchain"
else
    echo "setup.sh: creating venv at $VENV"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --quiet --upgrade pip==25.0.1
    "$VENV/bin/pip" install --require-hashes -r "$HERE/requirements.lock"
fi

# Record what was actually installed for RECEIPT.md.
"$VENV/bin/pip" list --format=freeze > "$HERE/VERSIONS.txt"
{
    printf '## python %s, mujoco %s, numpy %s\n' \
        "$("$VENV/bin/python" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')" \
        "$("$VENV/bin/python" -c 'import mujoco; print(mujoco.__version__)')" \
        "$("$VENV/bin/python" -c 'import numpy; print(numpy.__version__)')"
    cat "$HERE/VERSIONS.txt"
} > "$HERE/VERSIONS.tmp" && mv "$HERE/VERSIONS.tmp" "$HERE/VERSIONS.txt"

if [ "${1:-}" = "--record" ]; then
    echo "setup.sh: recording the reference GPU lease stack to version-table.json"
    SIM_TUNER_PYTHON="$VENV/bin/python" "$VENV/bin/python" "$HERE/record_lease.py"
fi

echo "setup.sh: ok"
