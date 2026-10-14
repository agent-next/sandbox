#!/usr/bin/env bash
# cookbook/cnc-gcode: install pinned judge tools idempotently into $HOME.
#
# Installs (into $HOME/.cnc-gcode/venv):
#   - numpy 2.5.3, sha256-pinned wheels from judge/requirements.txt
# The rest of the judge (G-code parser, heightmap simulator, gates) is Python
# 3.12 stdlib + numpy.  Safe to re-run; exact versions, never "latest".
#
# Usage: bash judge/setup.sh
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${HOME}/.cnc-gcode/venv"
PY="${VENV}/bin/python"

python3 - <<'EOF' || { echo "setup: python3 >= 3.12 required" >&2; exit 1; }
import sys
assert sys.version_info >= (3, 12), sys.version
EOF

if [ -x "$PY" ] && "$PY" -c "import numpy" >/dev/null 2>&1 \
   && [ "$("$PY" -c "import numpy;print(numpy.__version__)")" = "2.5.3" ]; then
    echo "setup: numpy 2.5.3 already installed in ${VENV} (skipping)"
else
    echo "setup: creating venv + installing pinned numpy"
    rm -rf "$VENV"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --no-cache-dir --upgrade "pip==25.0.1" >/dev/null
    "$VENV/bin/pip" install --no-cache-dir --require-hashes \
        -r "${JDIR}/requirements.txt"
fi

echo "setup: tool versions"
"$PY" --version
"$PY" -c "import numpy;print('numpy', numpy.__version__)"
{
    echo "# cnc-gcode judge: versions installed by judge/setup.sh"
    echo "# ($(uname -sm))"
    "$PY" --version
    "$PY" -c "import numpy;print('numpy', numpy.__version__)"
} > "$JDIR/VERSIONS.txt"
echo "setup: wrote $JDIR/VERSIONS.txt"
echo "setup: done"
