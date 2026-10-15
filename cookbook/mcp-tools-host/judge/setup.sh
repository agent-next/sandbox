#!/usr/bin/env bash
# judge/setup.sh — install the pinned judge toolchain into $HOME, idempotently.
#
# Installs the official MCP Python SDK (mcp 1.30.0, MIT) and every transitive
# dependency into a dedicated venv, hash-pinned from judge/requirements.txt
# (pip --require-hashes refuses any archive whose sha256 does not match).
# Records what was actually installed in judge/VERSIONS.txt.
#
# Exits non-zero on any failure (wrong platform, failed install, wrong
# versions). No sudo, nothing outside $HOME and the judge directory.

set -euo pipefail

JUDGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HOME/.venvs/mcp-tools-host"
PINNED_MCP="1.30.0"

echo "setup: python3 $(python3 --version 2>&1 | cut -d' ' -f2)"

# The pinned wheels in requirements.txt are CPython 3.12 on linux x86_64
# (the sandbox image this demo pins); anything else fails fast instead of
# resolving differently.
python3 - <<'PY' || { echo "setup: FAIL — pinned wheels target CPython 3.12, linux x86_64" >&2; exit 1; }
import platform, sys
ok = platform.python_implementation() == "CPython" \
    and platform.python_version_tuple()[:2] == ("3", "12") \
    and platform.machine() == "x86_64" \
    and sys.platform.startswith("linux")
sys.exit(0 if ok else 1)
PY

need_install=1
if [ -x "$VENV/bin/python" ]; then
    if "$VENV/bin/python" - "$PINNED_MCP" <<'PY' >/dev/null 2>&1
import importlib.metadata as md, sys
assert md.version("mcp") == sys.argv[1]
from mcp.client.session import ClientSession  # noqa: F401
from mcp.server.fastmcp import FastMCP        # noqa: F401
PY
    then
        need_install=0
        echo "setup: venv already healthy ($VENV, mcp $PINNED_MCP)"
    fi
fi

if [ "$need_install" = 1 ]; then
    echo "setup: creating venv $VENV"
    python3 -m venv "$VENV"
    # Hash-pinned: pip verifies the sha256 of every archive it downloads
    # and refuses anything that does not match requirements.txt.
    "$VENV/bin/pip" install --require-hashes --only-binary=:all: \
        -r "$JUDGE_DIR/requirements.txt"
fi

# Verify the interpreter the judge will actually use, not just pip metadata.
"$VENV/bin/python" - "$PINNED_MCP" <<'PY'
import importlib.metadata as md, sys
want, got = sys.argv[1], md.version("mcp")
if got != want:
    print(f"setup: FAIL — mcp {got} installed, expected {want}", file=sys.stderr)
    sys.exit(1)
from mcp.client.session import ClientSession  # noqa: F401
from mcp.server.fastmcp import FastMCP        # noqa: F401
print(f"setup: mcp {got} — client and server import OK")
PY

VJSON="$VENV/bin/python"
{
    echo "# Recorded by judge/setup.sh $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "# Toolchain the mcp-tools-host judge actually ran with."
    echo
    echo "\$ python3 --version"
    python3 --version
    echo
    echo "\$ $VENV/bin/pip --version"
    "$VENV/bin/pip" --version
    echo
    echo "\$ $VENV/bin/pip freeze"
    "$VENV/bin/pip" freeze
} > "$JUDGE_DIR/VERSIONS.txt"
echo "setup: wrote $JUDGE_DIR/VERSIONS.txt"
echo "setup: done"
