#!/usr/bin/env bash
# Install pinned judge tools into $HOME/ct-judge-venv (idempotent).
# Every package — pip itself included — is a sha256-pinned wheel
# (manylinux cp312 x86_64) installed via pip --require-hashes; a hash
# mismatch aborts the install. Nothing floating, nothing built from source.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
VENV="$HOME/ct-judge-venv"
PY="${VENV}/bin/python3"

if [ -x "$PY" ]; then
  echo "setup: already installed at $VENV (delete it to re-install)"
else
  python3 -m venv "$VENV"
  # one hash-checked install of the full closure, pip included
  PIP_DISABLE_PIP_VERSION_CHECK=1 "$PY" -m pip install --no-cache-dir \
      --require-hashes -r "$HERE/requirements.txt" >/dev/null
fi

# record what is actually installed (standard: judge/VERSIONS.txt)
"$PY" -m pip freeze > "$HERE/VERSIONS.txt"
"$PY" - <<'EOF' >> "$HERE/VERSIONS.txt"
import sys
print(f"python {sys.version.split()[0]}")
import control, slycot, numpy, scipy
print(f"control {control.__version__}")
print(f"slycot {slycot.__version__}")
print(f"numpy {numpy.__version__}")
print(f"scipy {scipy.__version__}")
EOF
cat "$HERE/VERSIONS.txt"
echo "setup: ok"
