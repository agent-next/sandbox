#!/usr/bin/env bash
# judge/setup.sh — install the pinned physx-drop-test toolchain.
#
# Creates a venv at $HOME/.venvs/physx-drop-test and installs every wheel
# with `pip install --require-hashes` (sha256 table in requirements.txt),
# so a republished or tampered wheel fails loudly here instead of silently
# changing the physics under the judge.  Idempotent: if the venv already
# holds the exact pinned versions, it is left untouched.
#
# Usage: bash judge/setup.sh [--force]
# Exit codes: 0 ok, 1 failure, 2 environment not supported.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${PHYSX_DROP_TEST_VENV:-$HOME/.venvs/physx-drop-test}"
MARKER="$VENV/.physx-drop-test.ok"
REQS="$SCRIPT_DIR/requirements.txt"

log() { echo "[setup] $*"; }

# --- environment checks -----------------------------------------------------
if [[ "$(uname -m)" != "x86_64" ]]; then
    echo "[setup] ERROR: pinned wheels are x86_64-only (uname -m: $(uname -m))" >&2
    exit 2
fi
if [[ "$(uname -s)" != "Linux" ]]; then
    echo "[setup] ERROR: pinned wheels are Linux-only (uname -s: $(uname -s))" >&2
    exit 2
fi
# ovphysx prebuilt binaries require AVX on x86_64
if ! grep -qw avx /proc/cpuinfo; then
    echo "[setup] ERROR: CPU lacks AVX, required by the pinned ovphysx wheel" >&2
    exit 2
fi
command -v python3 >/dev/null || { echo "[setup] ERROR: python3 not found" >&2; exit 2; }

# --- idempotence --------------------------------------------------------------
if [[ "${1:-}" != "--force" && -f "$MARKER" ]] && "$VENV/bin/python" - <<'PY'
import sys
from importlib import metadata
expected = {
    "ovphysx": "0.6.3",
    "ovstage": "0.2.0.377349",
    "newton-usd-schemas": "0.5.0",
    "warp-lang": "1.17.0",
    "numpy": "2.2.6",
    "packaging": "23.2",
}
seen = {d.metadata["Name"]: d.version for d in metadata.distributions()}
for name, want in expected.items():
    if seen.get(name) != want:
        sys.exit(1)
PY
then
    log "venv already holds the pinned versions — nothing to do ($VENV)"
    exit 0
fi

# --- install ------------------------------------------------------------------
log "creating venv at $VENV"
rm -rf "$VENV"
python3 -m venv "$VENV"

log "installing pinned wheels (sha256-verified via --require-hashes)"
"$VENV/bin/pip" install --no-input --require-hashes -r "$REQS"

# --- verify: exact versions importable, native PhysX loads --------------------
"$VENV/bin/python" -I - <<'PY'
import importlib
from importlib import metadata
expected = {
    "ovphysx": "0.6.3",
    "ovstage": "0.2.0.377349",
    "newton-usd-schemas": "0.5.0",
    "warp-lang": "1.17.0",
    "numpy": "2.2.6",
    "packaging": "23.2",
}
for name, want in expected.items():
    dist = [d for d in metadata.distributions() if d.metadata["Name"] == name]
    if not dist or dist[0].version != want:
        raise SystemExit(f"version mismatch: {name}: wanted {want}, "
                         f"found {dist[0].version if dist else 'nothing'}")
import ovphysx
from ovphysx import PhysX  # triggers native library load
print("[setup] ovphysx native library loads:", PhysX is not None)
PY

touch "$MARKER"

log "installed versions:"
"$VENV/bin/pip" freeze
log "python: $("$VENV/bin/python" --version)"
log "done."
