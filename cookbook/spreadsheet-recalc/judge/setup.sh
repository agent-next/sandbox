#!/usr/bin/env bash
# Install pinned tools for the spreadsheet-recalc judge, idempotently.
#
# Tools:
#   - libreoffice-calc 7.4.x from Debian bookworm (apt, version-pinned)
#   - openpyxl 3.1.5 (pip wheel, sha256-pinned via --require-hashes)
#
# Idempotent: skips steps already satisfied.
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- openpyxl via pip (pinned, sha256-checked) ---
OPENPYXL_VERSION="3.1.5"
OPENPYXL_WHEEL_SHA256="9f945149b72df8ac1d4e5d35d85d14d92b468c74c3e474962ba5036ad800c24f"

PY="${PYTHON:-python3}"

if "$PY" -c "import openpyxl; assert openpyxl.__version__ == '$OPENPYXL_VERSION'" 2>/dev/null; then
    echo "setup: openpyxl $OPENPYXL_VERSION already present"
else
    echo "setup: installing openpyxl $OPENPYXL_VERSION (sha256-checked)"
    tmpdir="$(mktemp -d)"
    trap 'rm -rf "$tmpdir"' EXIT

    # Download the pinned wheel from PyPI
    wheel_url="https://files.pythonhosted.org/packages/py3/o/openpyxl/openpyxl-${OPENPYXL_VERSION}-py2.py3-none-any.whl"
    # Use PyPI JSON API to resolve the exact URL (more stable than guessing)
    wheel_url="$("$PY" -c "
import json, urllib.request
d = json.load(urllib.request.urlopen('https://pypi.org/pypi/openpyxl/${OPENPYXL_VERSION}/json'))
for f in d['urls']:
    if f['filename'].endswith('.whl') and 'py3' in f['filename'] and 'none-any' in f['filename']:
        print(f['url']); break
")"

    curl -fsSL -o "$tmpdir/openpyxl.whl" "$wheel_url"
    actual_sha=$(sha256sum "$tmpdir/openpyxl.whl" | awk '{print $1}')
    if [ "$actual_sha" != "$OPENPYXL_WHEEL_SHA256" ]; then
        echo "setup: sha256 mismatch on openpyxl wheel (got $actual_sha, want $OPENPYXL_WHEEL_SHA256)" >&2
        exit 1
    fi
    "$PY" -m pip install --quiet "$tmpdir/openpyxl.whl"
    rm -rf "$tmpdir"
    trap - EXIT
fi

# --- LibreOffice via apt (version-pinned) ---
LO_PKG="libreoffice-calc"
LO_VERSION="4:7.4.7-1+deb12u14"
installed_lo="$(dpkg-query -W -f='${Version}' "$LO_PKG" 2>/dev/null || true)"

if [ "$installed_lo" != "$LO_VERSION" ]; then
    echo "setup: installing $LO_PKG $LO_VERSION via apt"
    sudo apt-get update -qq
    sudo apt-get install -y -qq "$LO_PKG=$LO_VERSION" 2>/dev/null || {
        # Fall back to whatever version apt resolves if exact pin is unavailable
        echo "setup: exact pin $LO_VERSION unavailable; installing latest available"
        sudo apt-get install -y -qq "$LO_PKG"
    }
fi

# Verify LibreOffice is callable
if ! command -v libreoffice >/dev/null 2>&1; then
    echo "setup: libreoffice not found on PATH after install" >&2
    exit 1
fi

# --- Record actual versions ---
{
    echo "# spreadsheet-recalc judge: versions installed by judge/setup.sh"
    echo "# ($(uname -sm), $(date -u +%Y-%m-%dT%H:%M:%SZ))"
    echo "openpyxl $($PY -c 'import openpyxl; print(openpyxl.__version__)')"
    echo "libreoffice $(libreoffice --version 2>&1 | head -1)"
    echo "libreoffice-calc debian package: $(dpkg-query -W -f='${Version}' libreoffice-calc)"
    echo "python3 $($PY --version 2>&1 | awk '{print $2}')"
} > "$JDIR/VERSIONS.txt"

echo "setup: wrote $JDIR/VERSIONS.txt"
echo "setup: done"
