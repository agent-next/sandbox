#!/usr/bin/env bash
# judge/setup.sh — install the pinned toolchain into $HOME, idempotently.
#
# Two virtualenvs keep the converter's bundled USD apart from the judge's
# independent usd-core reader (they cannot share a site-packages):
#   $HOME/.venvs/cad2usd-convert  usd-convert-cad 0.3.0        (tool under test)
#   $HOME/.venvs/cad2usd-judge    usd-core 26.8 + cadquery-ocp 7.9.3.1.1 (oracle)
#
# Every wheel is sha256-checked by pip (--require-hashes) against
# judge/requirements-*.txt. Exact versions only; nothing here was
# published in the last two weeks (see judge/VERSIONS.txt for dates).
#
# Usage:  bash judge/setup.sh [--force]
# Exit codes: 0 ok, 1 failure, 2 wrong platform/python.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_BASE="${CAD2USD_VENV_BASE:-$HOME/.venvs}"
CONV_VENV="$VENV_BASE/cad2usd-convert"
JUDGE_VENV="$VENV_BASE/cad2usd-judge"
FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

log() { echo "[setup] $*"; }

# The pinned wheels are CPython-3.12 manylinux x86_64 builds.
need_python() {
    local py; py="$(command -v python3 || true)"
    [[ -n "$py" ]] || { log "ERROR: python3 not found"; exit 2; }
    local v; v="$("$py" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
    [[ "$v" == "3.12" ]] || {
        log "ERROR: need python3.12 (found $v at $py): the pinned wheels are cp312 builds"
        exit 2
    }
}

marker_ok() {  # marker_ok <venv> <requirements>
    local venv="$1" req="$2"
    [[ -f "$venv/.cad2usd-installed" ]] || return 1
    [[ "$(cat "$venv/.cad2usd-installed")" == "$(sha256sum "$req" | cut -d' ' -f1)" ]] || return 1
    # spot-check the imports that matter
    if [[ "$venv" == "$CONV_VENV" ]]; then
        "$venv/bin/python" -I -c "import usd_convert_cad" 2>/dev/null
    else
        "$venv/bin/python" -I -c "from pxr import Usd; import OCP; import OCP.STEPControl" 2>/dev/null
    fi
}

install_venv() {  # install_venv <venv> <requirements>
    local venv="$1" req="$2"
    if [[ $FORCE -eq 0 ]] && marker_ok "$venv" "$req"; then
        log "$(basename "$venv") already installed and matches $req"
        return 0
    fi
    rm -rf "$venv"
    python3 -m venv "$venv"
    log "installing into $(basename "$venv") from $(basename "$req") (sha256-checked)"
    "$venv/bin/pip" install --quiet --upgrade --no-cache-dir pip
    "$venv/bin/pip" install --require-hashes --no-cache-dir -r "$req"
    sha256sum "$req" | cut -d' ' -f1 > "$venv/.cad2usd-installed"
}

# Record what was actually installed into judge/VERSIONS.txt (committed:
# the standard's pinned-versions receipt) plus the venv-local copy above.
record_versions() {
    local out="$SCRIPT_DIR/VERSIONS.txt"
    {
        echo "recorded: $(date -u +%Y-%m-%dT%H:%M:%SZ) by judge/setup.sh"
        echo "python: $("$JUDGE_VENV/bin/python" -V 2>&1)"
        echo "usd-convert-cad: $("$CONV_VENV/bin/python" -c 'from importlib.metadata import version; print(version("usd-convert-cad"))')"
        echo "usd-core (pxr): $("$JUDGE_VENV/bin/python" -I -c 'from pxr import Usd; print(".".join(map(str, Usd.GetVersion())))')"
        echo "cadquery-ocp: $("$JUDGE_VENV/bin/python" -c 'from importlib.metadata import version; print(version("cadquery-ocp"))')"
        echo "vtk: $("$JUDGE_VENV/bin/python" -c 'from importlib.metadata import version; print(version("vtk"))')"
        echo "converter banner: $("$CONV_VENV/bin/usd-convert-cad" --help 2>&1 | head -1)"
    } > "$out"
    cat "$out"
}

need_python
install_venv "$CONV_VENV" "$SCRIPT_DIR/requirements-convert.txt"
install_venv "$JUDGE_VENV" "$SCRIPT_DIR/requirements-judge.txt"
record_versions
log "done"
