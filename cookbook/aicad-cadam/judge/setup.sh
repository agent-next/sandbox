#!/usr/bin/env bash
# judge/setup.sh — install the pinned judge toolchain.
#
#  * OpenSCAD 2021.01-6 (Debian bookworm .deb, sha256-checked against
#    judge/package-sha256.txt before install) — the CAD kernel CADAM's
#    backend vendors as openscad-wasm, run natively/headless.
#  * A venv at $HOME/.venvs/aicad with hash-pinned wheels:
#    cadquery-ocp (OCCT), trimesh, manifold3d, ezdxf, numpy.
#
# Idempotent; writes what it actually installed to judge/VERSIONS.txt.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${AICAD_VENV:-$HOME/.venvs/aicad}"
OPENSCAD_VERSION="2021.01-6"
DEB_NAME="openscad_${OPENSCAD_VERSION}_amd64.deb"
DEB_SHA="$(awk '$1=="'"$DEB_NAME"'" {print $2}' "$SCRIPT_DIR/package-sha256.txt")"

log() { echo "[setup] $*"; }
SUDO=""
if [[ "$(id -u)" -ne 0 ]]; then SUDO=sudo; fi

# ---------------------------------------------------------------- OpenSCAD
have_openscad() {
    [[ "$(dpkg-query -W -f='${Version}' openscad 2>/dev/null || true)" \
        == "$OPENSCAD_VERSION" ]] && command -v openscad >/dev/null 2>&1
}

if ! have_openscad; then
    log "Fetching apt package lists..."
    if ! out="$($SUDO apt-get update -qq 2>&1)"; then
        echo "$out" | tail -n 3
        log "ERROR: apt-get update failed"; exit 2
    fi
    if [[ "$(apt-cache policy openscad)" != *"$OPENSCAD_VERSION"* ]]; then
        log "ERROR: openscad $OPENSCAD_VERSION not in apt lists"
        log "       (empty lists are a known failure mode of fresh images)"
        exit 2
    fi
    DL="$(mktemp -d /tmp/aicad-deb.XXXXXX)"
    trap 'rm -rf "$DL"' EXIT
    (cd "$DL" && apt-get download "openscad=$OPENSCAD_VERSION" -qq)
    actual_sha="$(sha256sum "$DL/$DEB_NAME" | cut -d' ' -f1)"
    if [[ "$actual_sha" != "$DEB_SHA" ]]; then
        log "ERROR: $DEB_NAME sha256 mismatch"
        log "       expected $DEB_SHA"
        log "       got      $actual_sha"
        exit 1
    fi
    log "sha256 ok: $DEB_NAME"
    $SUDO apt-get install -y -qq --no-install-recommends \
        "$DL/$DEB_NAME" >/dev/null
    have_openscad || { log "ERROR: openscad did not install"; exit 1; }
else
    log "openscad $OPENSCAD_VERSION already installed"
fi

# ------------------------------------------------------------------- venv
if [[ ! -x "$VENV/bin/python" ]] || ! "$VENV/bin/python" - <<'PY' >/dev/null 2>&1
import importlib.metadata as md
pins = {"cadquery-ocp": "7.7.2", "ezdxf": "1.3.0", "fonttools": "4.67.0",
        "manifold3d": "3.0.1", "numpy": "1.26.4", "pyparsing": "3.3.3",
        "trimesh": "4.3.2", "typing_extensions": "4.16.0"}
for pkg, ver in pins.items():
    try:
        assert md.version(pkg) == ver
    except Exception:
        raise SystemExit(1)
PY
then
    log "Creating judge venv at $VENV..."
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install -q --require-hashes \
        -r "$SCRIPT_DIR/requirements.txt"
else
    log "judge venv already pinned at $VENV"
fi

# ---------------------------------------------------------------- VERSIONS
{
    echo "# written by judge/setup.sh $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "openscad: $(openscad --version 2>&1)"
    echo "openscad-deb: $(dpkg-query -W -f='${Version}' openscad)"
    for p in cadquery-ocp ezdxf fonttools manifold3d numpy pyparsing \
             trimesh typing_extensions; do
        echo "$p: $("$VENV/bin/python" -c \
            "import importlib.metadata as md; print(md.version('$p'))")"
    done
    echo "python: $("$VENV/bin/python" --version 2>&1)"
} > "$SCRIPT_DIR/VERSIONS.txt"
log "wrote $SCRIPT_DIR/VERSIONS.txt"
log "done"
