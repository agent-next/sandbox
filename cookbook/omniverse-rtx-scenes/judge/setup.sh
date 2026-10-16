#!/usr/bin/env bash
# judge/setup.sh — install the pinned CPU-judge toolchain into a venv.
#
# Idempotent.  Every wheel is sha256-verified with
# `pip install --require-hashes`, so the judge cannot silently change under
# the demo.  No ranges, nothing published in the last two weeks at pin time
# (2026-10-15):
#
#   usd-core 25.8.0    released 2025-07-31
#   numpy    2.2.6     released 2025-05-17
#   Pillow   11.0.0    released 2024-10-15
#
# The GPU-side toolchain is NOT installed here: it lives inside the
# `omniverse` template lease and is never mutable by this judge (see
# PRODUCT-FRICTION.md and SPEC.md §8.2).
#
# Usage:
#   bash judge/setup.sh                 # install into $HOME/.venv-omnv-judge
#   bash judge/setup.sh --force         # recreate the venv
#
# Exit codes: 0 ok, 1 install/verification failure, 2 no network.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REQ="$SCRIPT_DIR/judge-requirements.txt"
VENV="${VENV:-$HOME/.venv-omnv-judge}"
FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

log() { echo "[setup] $*"; }

[[ -f "$REQ" ]] || { log "ERROR: missing $REQ"; exit 1; }

if [[ $FORCE -eq 1 && -d "$VENV" ]]; then
    log "recreating $VENV"
    rm -rf "$VENV"
fi

if [[ ! -x "$VENV/bin/python" ]]; then
    log "creating venv at $VENV"
    python3 -m venv "$VENV" || { log "ERROR: python3 -m venv failed"; exit 1; }
fi

PY="$VENV/bin/python"
"$PY" -m pip install -q --upgrade pip || {
    log "ERROR: could not upgrade pip (no network?)"; exit 2; }

log "installing pinned wheels (sha256-verified)..."
if ! "$PY" -m pip install -q --require-hashes -r "$REQ"; then
    log "ERROR: pinned install failed (digest mismatch or missing wheel)"
    exit 1
fi

# Verify the imports the judge actually needs, in a clean process.
if ! "$PY" - <<'EOF'
import numpy, PIL, pxr.Usd, pxr.UsdGeom, pxr.UsdUtils
from PIL import Image
print("judge imports OK")
EOF
then
    log "ERROR: imports failed after install"
    exit 1
fi

cat > "$SCRIPT_DIR/VERSIONS.txt" <<EOF
# omniverse-rtx-scenes judge toolchain (CPU side).
# Installed by judge/setup.sh with --require-hashes from judge-requirements.txt.
# Recorded $(date -Iseconds).
python=$("$PY" -V 2>&1)
$("$PY" -m pip freeze --exclude-editable)
EOF

log "judge toolchain installed and verified"
log "(versions recorded in judge/VERSIONS.txt)"
