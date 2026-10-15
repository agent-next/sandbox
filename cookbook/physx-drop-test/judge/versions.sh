#!/usr/bin/env bash
# judge/versions.sh — write judge/VERSIONS.txt: what setup.sh actually
# installed, with --version output of each tool.  Run after judge/setup.sh.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${PHYSX_DROP_TEST_VENV:-$HOME/.venvs/physx-drop-test}"
PY="$VENV/bin/python"

if [[ ! -x "$PY" ]]; then
    echo "[versions] ERROR: venv python not found at $PY — run judge/setup.sh first" >&2
    exit 1
fi

OUT="$SCRIPT_DIR/VERSIONS.txt"
{
    echo "# physx-drop-test toolchain — recorded by judge/versions.sh"
    echo "# from the venv at ${VENV/#$HOME/\$HOME}"
    echo
    echo "python: $("$PY" --version 2>&1)"
    echo "platform: $(uname -sm)"
    echo
    echo "pip freeze (${PY/#$HOME/\$HOME} -m pip freeze):"
    "$PY" -m pip freeze | sed 's/^/  /'
    echo
    echo "native-library load check (ovphysx.PhysX imports):"
    "$PY" -I - <<'PY' | sed 's/^/  /'
from ovphysx import PhysX
import ovphysx, ovstage, warp, numpy
from importlib import metadata
for name in ("ovphysx", "ovstage", "newton-usd-schemas", "warp-lang",
             "numpy", "packaging"):
    print(f"{name} {metadata.version(name)}")
print("PhysX importable:", PhysX is not None)
PY
} > "$OUT"

echo "[versions] wrote $OUT"
