#!/usr/bin/env bash
# Install pinned judge tools into $HOME/ct-judge-venv (idempotent).
# Exact versions with sha256-pinned wheels (manylinux cp312 x86_64) via
# pip --require-hashes: every package in the closure is hash-checked,
# nothing floating, nothing built from source.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
VENV="$HOME/ct-judge-venv"
PY="${VENV}/bin/python3"

if [ -x "$PY" ]; then
  echo "setup: already installed at $VENV (delete it to re-install)"
else
  python3 -m venv "$VENV"
  "$PY" -m pip install --no-cache-dir --upgrade pip >/dev/null
  "$PY" -m pip install --no-cache-dir --require-hashes \
      -r "$HERE/requirements.txt" >/dev/null
fi

"$PY" - <<'EOF'
import control, slycot, numpy, scipy
print("control", control.__version__)
print("slycot", slycot.__version__)
print("numpy", numpy.__version__)
print("scipy", scipy.__version__)
EOF
echo "setup: ok"
