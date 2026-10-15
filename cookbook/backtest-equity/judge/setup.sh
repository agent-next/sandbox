#!/usr/bin/env bash
# Pinned toolchain for the backtest-equity demo, idempotent.
#
# * judge side: Python >= 3.10 from the system, standard library only --
#   nothing is downloaded for the judge itself.
# * agent/artifact side: numpy + matplotlib (and their deps) at the exact
#   pinned versions in judge/requirements.txt, installed with
#   `pip --require-hashes` into $HOME/.venvs/backtest-equity.  Those wheels
#   are interpreter-tagged, so a sandbox whose python3 differs from the one
#   recorded in judge/VERSIONS.txt cannot install into the same venv; the
#   venv is therefore keyed on the interpreter version.
#
# Every download is sha256-checked by pip's hashing mode.  On any checksum
# or install failure this script exits non-zero.  No "latest"; nothing
# published in the last two weeks (all pins are at least that old).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$HOME/.venvs/backtest-equity"
REQS="$SCRIPT_DIR/requirements.txt"

# --- runtime checks -------------------------------------------------------
python3 - <<'EOF' || { echo "setup: Python >= 3.10 required" >&2; exit 1; }
import sys
assert sys.version_info >= (3, 10), sys.version
EOF
PYVER="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"

for bin in curl; do
    command -v "$bin" >/dev/null 2>&1 || {
        echo "setup: $bin is required (sudo apt-get install curl)" >&2
        exit 1
    }
done

# --- pinned wheel install (idempotent) -----------------------------------
# The build host may not have pip either; python3 -m venv always provides it.
if [ -x "$VENV_DIR/bin/python" ] \
        && "$VENV_DIR/bin/python" -c 'import numpy, matplotlib' >/dev/null 2>&1 \
        && "$VENV_DIR/bin/python" -V 2>&1 | grep -q " $PYVER\." ; then
    echo "setup: numpy/matplotlib already installed in $VENV_DIR (skipping pip)"
else
    echo "setup: installing pinned wheels (python $PYVER, --require-hashes) into $VENV_DIR"
    rm -rf "$VENV_DIR"
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --quiet --no-cache-dir --require-hashes \
        -r "$REQS" || {
        echo "setup: pinned wheel install FAILED (checksum or download error)" >&2
        exit 1
    }
fi

# --- verify the exact pins actually import -------------------------------
"$VENV_DIR/bin/python" - "$REQS" <<'EOF' || exit 1
import re
import sys
from pathlib import Path

reqs = Path(sys.argv[1])
pins = {}
for line in reqs.read_text().splitlines():
    m = re.match(r"^([A-Za-z0-9_.-]+)==(\S+)", line.strip())
    if m:
        pins[m.group(1)] = m.group(2)

import importlib.metadata as md
for name, want in sorted(pins.items()):
    got = md.version(name)
    if got != want:
        print(f"setup: {name} {got} is installed, {want} is pinned", file=sys.stderr)
        raise SystemExit(1)
    print(f"pin ok: {name}=={got}")
EOF

# --- no third-party data, no fixture in the install ----------------------
# The pinned fixture ships with the demo (tools/data/ohlcv.csv +
# tools/data/ohlcv.csv.sha256).  Verify it so a corrupted checkout is
# caught here, before anything is graded.
FIXTURE_SHA="$(sed -n '1s/ .*//p' "$SCRIPT_DIR/../tools/data/ohlcv.csv.sha256")"
FIXTURE_GOT="$(sha256sum "$SCRIPT_DIR/../tools/data/ohlcv.csv" | cut -d' ' -f1)"
if [ "$FIXTURE_SHA" != "$FIXTURE_GOT" ]; then
    echo "setup: the pinned fixture sha256 $FIXTURE_GOT != $FIXTURE_SHA" >&2
    exit 1
fi
echo "setup: pinned fixture ok (sha256 $FIXTURE_GOT)"

# --- versions record (what setup.sh actually installed) ------------------
{
    echo "# backtest-equity judge: versions installed by judge/setup.sh"
    echo "# ($(uname -sm))"
    echo "python3 $PYVER ($(python3 -c 'import sys; print(sys.executable)'))"
    for pkg in numpy matplotlib contourpy cycler fonttools kiwisolver packaging pillow pyparsing python-dateutil six; do
        echo "$pkg $("$VENV_DIR/bin/python" -c "
import importlib.metadata as md
print(md.version('$pkg'))")"
    done
    echo "pip $("$VENV_DIR/bin/pip" --version | awk '{print $2}')"
    echo "fixture tools/data/ohlcv.csv sha256:$FIXTURE_GOT"
} > "$SCRIPT_DIR/VERSIONS.txt"
echo "setup: wrote $SCRIPT_DIR/VERSIONS.txt"

echo "setup: done (venv: $VENV_DIR)"
