#!/usr/bin/env bash
# Install pinned judge tools into $HOME/ct-judge-venv (idempotent).
# Every package — pip itself included — is a sha256-pinned wheel
# (manylinux cp312 x86_64) installed via pip --require-hashes; a hash
# mismatch aborts the install. Nothing floating, nothing built from source.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
VENV="$HOME/ct-judge-venv"
PY="${VENV}/bin/python3"
# written only after a fully successful install; records what was installed
STAMP="${VENV}/.ct-judge-stamp"

# The venv counts as installed only when the stamp of a completed install
# matches the current requirements file AND the pinned set still imports.
# An interrupted install can leave an executable interpreter behind with
# half the packages missing, and a stale venv must not skip requirements
# added since it was created — either case triggers a full reinstall.
verify() {
  [ -x "$PY" ] || return 1
  [ -f "$STAMP" ] || return 1
  [ "$(cat "$STAMP")" = "$(sha256sum "$HERE/requirements.txt" \
      | cut -d' ' -f1)" ] || return 1
  "$PY" - >/dev/null 2>&1 <<'EOF'
import control, slycot, numpy, scipy, matplotlib, mujoco, PIL
EOF
}

if verify; then
  echo "setup: already installed at $VENV (delete it to re-install)"
else
  rm -rf "$VENV"
  python3 -m venv "$VENV"
  # one hash-checked install of the full closure, pip included
  PIP_DISABLE_PIP_VERSION_CHECK=1 "$PY" -m pip install --no-cache-dir \
      --require-hashes -r "$HERE/requirements.txt" >/dev/null
  sha256sum "$HERE/requirements.txt" | cut -d' ' -f1 > "$STAMP"
  verify
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
