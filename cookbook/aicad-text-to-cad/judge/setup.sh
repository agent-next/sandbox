#!/usr/bin/env bash
# judge/setup.sh — pinned install for the aicad-text-to-cad demo.
#
# Installs into a dedicated venv at $HOME/.venvs/aicad-judge:
#   * cadgen 0.7.2  — the text-to-cad tool under demo
#     (https://github.com/earthtojake/text-to-cad, MIT), whose model
#     runtime executes the checked-in agent-written model scripts.
#   * the judge oracle libraries: trimesh (mesh validity/volume),
#     manifold3d (boolean XOR reference diff), plus the OCP CAD kernel
#     pulled in by cadgen/build123d (STEP re-import, BRepCheck validity,
#     B-rep volume/bounds/cylindrical faces).  ezdxf rides along as a
#     cadgen dependency and is recorded in VERSIONS.txt.
#
# Every wheel is sha256-pinned in judge/requirements.txt and installed
# with --require-hashes --only-binary, so a replaced or rebuilt package
# on PyPI fails the install instead of silently changing the judge.
# Idempotent: exits 0 early when the exact pins are already active.
#
# Usage:  bash judge/setup.sh [--force]
# Exit codes: 0 ok, 1 install/verification failure, 2 no network.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${AICAD_JUDGE_VENV:-$HOME/.venvs/aicad-judge}"
MARK="$VENV/.installed"
REQS="$SCRIPT_DIR/requirements.txt"
PY_MIN_MINOR=12

log() { echo "[setup] $*"; }

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

need_install() {
    [[ $FORCE -eq 1 ]] && return 0
    [[ -f "$MARK" ]] || return 0
    # The marker records the requirements checksum; a changed pin file
    # reinstalls, and a missing python/pip inside the venv reinstalls.
    [[ -x "$VENV/bin/python" && -x "$VENV/bin/pip" ]] || return 0
    grep -q "^reqs_sha256=$(sha256sum "$REQS" | cut -d' ' -f1)$" "$MARK" || return 0
    # spot-check one pin actually importable
    "$VENV/bin/python" -c "import cadgen, trimesh, manifold3d, OCP" 2>/dev/null || return 0
    return 1
}

if ! need_install; then
    log "judge venv already installed at $VENV (pins unchanged)"
    exit 0
fi

# ---------------------------------------------------------------------------
# 1. Network probe.  A fresh sandbox may have a proxy that answers DNS
#    but not PyPI; fail with code 2 before the slow pip crawl, not after.
# ---------------------------------------------------------------------------
if ! python3 -c "import urllib.request; urllib.request.urlopen('https://pypi.org/simple/', timeout=15)" 2>/dev/null; then
    log "ERROR: cannot reach https://pypi.org/simple/ — check network"
    exit 2
fi

# ---------------------------------------------------------------------------
# 2. Host python.  The pinned scientific wheels need CPython 3.12/3.13;
#    cadgen itself needs >= 3.11.
# ---------------------------------------------------------------------------
PY_BIN="${AICAD_PYTHON:-python3}"
HOST_VER="$("$PY_BIN" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
if python3 - <<PY >/dev/null 2>&1
import sys
rc = sys.version_info[0] == 3 and sys.version_info[1] >= $PY_MIN_MINOR
sys.exit(0 if rc else 1)
PY
then
    :
else
    log "ERROR: host python is $HOST_VER; this stack needs CPython 3.$PY_MIN_MINOR+"
    log "  (pinned numpy/scipy/contourpy wheels ship no cp311 build)"
    exit 1
fi

log "creating venv at $VENV (host python $HOST_VER)"
rm -rf "$VENV"
"$PY_BIN" -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
# pip upgrade itself is unpinned (it installs nothing the judge imports);
# everything the judge touches is pinned next, hash-checked.

log "installing pinned, hash-checked wheels (this takes a few minutes)"
"$VENV/bin/pip" install \
    --require-hashes --only-binary :all: \
    --timeout 60 --retries 3 \
    -r "$REQS"

# ---------------------------------------------------------------------------
# 3. Verify the install: exact import versions and a kernel self-check.
# ---------------------------------------------------------------------------
log "verifying versions"
"$VENV/bin/python" - <<'PY'
import cadgen, trimesh, manifold3d, ezdxf, numpy, OCP
import importlib.metadata as md
for name, want in [
    ("cadgen", "0.7.2"),
    ("trimesh", "4.12.2"),
    ("manifold3d", "3.5.2"),
    ("build123d", "0.11.1"),
    ("cadquery-ocp-novtk", "7.9.3.1.1"),
    ("ezdxf", "1.4.4"),
]:
    got = md.version(name)
    if got != want:
        raise SystemExit(f"version mismatch: {name} {got} != pinned {want}")
# kernel smoke test: make a cylinder, check its volume analytically
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from math import pi
s = BRepPrimAPI_MakeCylinder(10.0, 5.0).Shape()
p = GProp_GProps()
BRepGProp.VolumeProperties_s(s, p)
assert abs(p.Mass() - pi * 100 * 5) < 1e-3, p.Mass()
print("[setup] kernel volume check ok:", round(p.Mass(), 3))
PY

# record what actually installed + the pin-file checksum that gated it
ENV_SHA="$(sha256sum "$REQS" | cut -d' ' -f1)"
{
    echo "reqs_sha256=$ENV_SHA"
    date -u +"installed_utc=%Y-%m-%dT%H:%M:%SZ"
} > "$MARK"

bash "$SCRIPT_DIR/versions.sh" > "$SCRIPT_DIR/VERSIONS.txt"
log "done. Tool: cadgen $("$VENV/bin/python" -c 'import importlib.metadata as m; print(m.version("cadgen"))') — pinned, verified."
