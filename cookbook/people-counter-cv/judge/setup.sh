#!/bin/sh
# Install the pinned judge toolchain into $HOME/.venvs/people-counter-cv.
#
# One closure, pinned in requirements.lock (opencv-python-headless
# 4.13.0.92 under the date rule, numpy 2.5.3 under the date rule),
# sha256-checked via pip's --require-hashes. Idempotent: an existing
# venv that already provides the pinned versions is left untouched.

set -eu

VENV="$HOME/.venvs/people-counter-cv"
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
import importlib.metadata as md
import numpy
ok = (md.version("opencv-python-headless") == "4.13.0.92"
      and numpy.__version__ == "2.5.3")
import sys
sys.exit(0 if ok else 1)
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
printf '## python %s, opencv-python-headless %s, numpy %s\n' \
    "$("$VENV/bin/python" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')" \
    "$("$VENV/bin/python" -c 'import importlib.metadata as md; print(md.version("opencv-python-headless"))')" \
    "$("$VENV/bin/python" -c 'import numpy; print(numpy.__version__)')" \
    > "$HERE/VERSIONS.brief"
cat "$HERE/VERSIONS.brief" "$HERE/VERSIONS.txt" > "$HERE/VERSIONS.tmp"
mv "$HERE/VERSIONS.tmp" "$HERE/VERSIONS.txt"
rm -f "$HERE/VERSIONS.brief"

echo "setup.sh: ok"
