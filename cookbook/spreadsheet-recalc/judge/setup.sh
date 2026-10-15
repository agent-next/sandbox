#!/usr/bin/env bash
# Install the pinned judge toolchain into $HOME/.venvs/spreadsheet-recalc.
#
# One closure, pinned in requirements.lock (openpyxl 3.1.5 + et_xmlfile
# 2.0.0), sha256-checked via pip's --require-hashes. LibreOffice is installed
# via apt (version-pinned to the Debian bookworm build). Idempotent: an
# existing venv that already provides the pinned versions is left untouched.
#
# The venv lives in $HOME so it works in a fresh sandbox without sudo and
# without touching system Python.

set -eu

VENV="$HOME/.venvs/spreadsheet-recalc"
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

# Resolve the interpreter that owns the pinned deps. grade.sh and
# selftest.sh call this script's venv via $PYTHON when they need it, but
# each is a separate `sbx exec` with no shared environment, so they
# self-detect the venv too. This resolution here is what they inherit.
if [ -x "$VENV/bin/python" ]; then
    PY="$VENV/bin/python"
else
    PY="$(command -v python3)"
fi
export PYTHON="$PY"

# --- Python deps via venv + pip --require-hashes ---
if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" - <<EOF
import sys
sys.path.insert(0, "$VENV/lib")
import importlib.util as u
def have(name, ver):
    m = u.find_spec(name)
    return m is not None and getattr(__import__(name), "__version__", "") == ver
sys.exit(0 if have("openpyxl", "3.1.5") and have("et_xmlfile", "2.0.0") else 1)
EOF
then
    echo "setup.sh: venv already provides the pinned toolchain"
else
    echo "setup.sh: creating venv at $VENV"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --quiet --upgrade pip==25.0.1
    "$VENV/bin/pip" install --require-hashes -r "$HERE/requirements.lock"
fi

# --- LibreOffice via apt (version-pinned) ---
LO_PKG="libreoffice-calc"
LO_VERSION="4:7.4.7-1+deb12u14"
installed_lo="$(dpkg-query -W -f='${Version}' "$LO_PKG" 2>/dev/null || true)"

if [ "$installed_lo" != "$LO_VERSION" ]; then
    echo "setup.sh: installing $LO_PKG $LO_VERSION via apt"
    sudo apt-get update -qq
    sudo apt-get install -y -qq "$LO_PKG=$LO_VERSION" 2>/dev/null || {
        # Fall back to whatever version apt resolves if exact pin is unavailable
        echo "setup.sh: exact pin $LO_VERSION unavailable; installing latest available"
        sudo apt-get install -y -qq "$LO_PKG"
    }
fi

# Verify LibreOffice is callable
if ! command -v libreoffice >/dev/null 2>&1; then
    echo "setup.sh: libreoffice not found on PATH after install" >&2
    exit 1
fi

# --- Record actual versions ---
{
    echo "# spreadsheet-recalc judge: versions installed by judge/setup.sh"
    echo "# ($(uname -sm), $(date -u +%Y-%m-%dT%H:%M:%SZ))"
    echo "openpyxl $($VENV/bin/python -c 'import openpyxl; print(openpyxl.__version__)')"
    echo "et_xmlfile $($VENV/bin/python -c 'import et_xmlfile; print(et_xmlfile.__version__)')"
    echo "libreoffice $(libreoffice --version 2>&1 | head -1)"
    echo "libreoffice-calc debian package: $(dpkg-query -W -f='${Version}' libreoffice-calc)"
    echo "python3 $($VENV/bin/python --version 2>&1 | awk '{print $2}')"
} > "$HERE/VERSIONS.txt"

echo "setup.sh: wrote $HERE/VERSIONS.txt"
echo "setup.sh: done"
