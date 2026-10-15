#!/usr/bin/env bash
# Install pinned, sha256-checked tools for the aicad-freecad-mcp judge.
# Idempotent: re-running skips what is already installed and verified.
# Everything lands under $HOME; nothing needs sudo except apt packages.
set -euo pipefail

LOG() { printf '[setup] %s\n' "$*"; }

VENV_DIR="$HOME/.venvs/aicad-judge"
VERSIONS_FILE="$(dirname "$0")/VERSIONS.txt"
HERE="$(cd "$(dirname "$0")" && pwd)"

# ---------------------------------------------------------------------------
# 1. Judge Python stack (pinned pip wheels) into a dedicated venv
# ---------------------------------------------------------------------------
JUDGE_REQ_SHA256="sha256:$(sha256sum "$HERE/requirements.txt" | cut -d' ' -f1)"
if [ -x "$VENV_DIR/bin/python" ] && "$VENV_DIR/bin/python" -c "
import trimesh, manifold3d, cadquery, ezdxf, numpy  # noqa" 2>/dev/null; then
    LOG "judge venv already satisfies requirements ($JUDGE_REQ_SHA256)"
else
    LOG "creating judge venv at $VENV_DIR"
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install --no-cache-dir -q --upgrade pip
    LOG "installing pinned judge deps (trimesh, manifold3d, cadquery/OCP, ezdxf)"
    "$VENV_DIR/bin/pip" install --no-cache-dir -q -r "$HERE/requirements.txt"
fi

# ---------------------------------------------------------------------------
# 2. FreeCAD 1.0.1 (AppImage -> extracted tree; LGPL-2.1+, run not vendored)
#    https://github.com/FreeCAD/FreeCAD/releases/tag/1.0.1
# ---------------------------------------------------------------------------
FREECAD_VER="1.0.1"
FREECAD_SHA256="5a3fc405771b4fbb5f270110d055bc135123c9fc91bb7dbb5d068ac7fbe50f6e"
FREECAD_URL="https://github.com/FreeCAD/FreeCAD/releases/download/${FREECAD_VER}/FreeCAD_${FREECAD_VER}-conda-Linux-x86_64-py311.AppImage"
FREECAD_DIR="$HOME/freecad-${FREECAD_VER}"
FREECAD_APPIMAGE="$HOME/FreeCAD_${FREECAD_VER}-conda-Linux-x86_64-py311.AppImage"

if [ -x "$FREECAD_DIR/usr/bin/freecad" ] && [ -x "$FREECAD_DIR/usr/bin/freecadcmd" ]; then
    LOG "FreeCAD ${FREECAD_VER} already extracted at $FREECAD_DIR"
else
    if [ ! -f "$FREECAD_APPIMAGE" ] || ! sha256sum "$FREECAD_APPIMAGE" | grep -q "^$FREECAD_SHA256"; then
        LOG "downloading FreeCAD ${FREECAD_VER} AppImage (~850 MB)"
        curl -fL --retry 3 -o "$FREECAD_APPIMAGE" "$FREECAD_URL"
        ACTUAL_SHA256="$(sha256sum "$FREECAD_APPIMAGE" | cut -d' ' -f1)"
        if [ "$ACTUAL_SHA256" != "$FREECAD_SHA256" ]; then
            echo "FATAL: FreeCAD AppImage sha256 mismatch" >&2
            echo "  expected $FREECAD_SHA256" >&2
            echo "  got      $ACTUAL_SHA256" >&2
            exit 1
        fi
        LOG "FreeCAD sha256 verified"
    else
        LOG "FreeCAD AppImage present, sha256 verified earlier"
    fi
    chmod +x "$FREECAD_APPIMAGE"
    rm -rf "$FREECAD_DIR"
    LOG "extracting AppImage (takes a couple of minutes)"
    (cd "$HOME" && "$FREECAD_APPIMAGE" --appimage-extract > /dev/null)
    rm -rf "$FREECAD_DIR"
    mv "$HOME/squashfs-root" "$FREECAD_DIR"
    LOG "extracted to $FREECAD_DIR"
fi

# ---------------------------------------------------------------------------
# 3. freecad-mcp (MIT) — MCP server package + FreeCAD addon, pinned git SHA
#    https://github.com/neka-nat/freecad-mcp
# ---------------------------------------------------------------------------
FCMCP_SHA="78bf0230a03324b56c9a0b7f55150fb5be2a0d42"
FCMCP_DIR="$HOME/freecad-mcp-${FCMCP_SHA:0:12}"
FCMCP_VENV="$HOME/.venvs/freecad-mcp"

if [ -d "$FCMCP_DIR" ] && [ -x "$FCMCP_VENV/bin/freecad-mcp" ]; then
    LOG "freecad-mcp already installed at $FCMCP_VENV (git $FCMCP_SHA)"
else
    LOG "cloning freecad-mcp at pinned SHA $FCMCP_SHA"
    rm -rf "$FCMCP_DIR"
    git clone -q https://github.com/neka-nat/freecad-mcp.git "$FCMCP_DIR"
    (cd "$FCMCP_DIR" && git checkout -q "$FCMCP_SHA")
    LOG "installing freecad-mcp into its own venv"
    rm -rf "$FCMCP_VENV"
    python3 -m venv "$FCMCP_VENV"
    "$FCMCP_VENV/bin/pip" install --no-cache-dir -q --upgrade pip
    "$FCMCP_VENV/bin/pip" install --no-cache-dir -q "$FCMCP_DIR"
fi

# Install the addon into FreeCAD's user Mod dir and enable RPC auto-start on
# loopback only (this is how run.py gets the RPC server up without a GUI click).
MOD_DIR="$($FREECAD_DIR/usr/bin/freecadcmd -c 'import FreeCAD; print(FreeCAD.getUserAppDataDir())' 2>/dev/null | tail -1)Mod"
mkdir -p "$MOD_DIR"
rm -rf "$MOD_DIR/FreeCADMCP"
cp -r "$FCMCP_DIR/addon/FreeCADMCP" "$MOD_DIR/FreeCADMCP"
printf '{\n  "remote_enabled": false,\n  "allowed_ips": "127.0.0.1",\n  "auto_start_rpc": true,\n  "auth_token": ""\n}\n' \
    > "$HOME/.local/share/FreeCAD/freecad_mcp_settings.json"
LOG "freecad-mcp addon installed with loopback-only RPC auto-start"

# ---------------------------------------------------------------------------
# 4. X11 headless support for the FreeCAD GUI + addon (Debian packages)
# ---------------------------------------------------------------------------
if ! command -v xvfb-run >/dev/null 2>&1; then
    LOG "apt lists may be empty in this image; refreshing"
    sudo apt-get update -q || true
    LOG "installing xvfb + xauth (FreeCAD GUI needs an X server for the RPC addon)"
    sudo apt-get install -y -q xvfb xauth
else
    LOG "xvfb-run already present"
fi

# ---------------------------------------------------------------------------
# 5. Record exact versions
# ---------------------------------------------------------------------------
{
    echo "aicad-freecad-mcp judge tool versions"
    echo "recorded: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "requirements.txt sha256: $(sha256sum "$HERE/requirements.txt" | cut -d' ' -f1)"
    echo "freecad: $($FREECAD_DIR/usr/bin/freecadcmd --version 2>/dev/null | tail -1)"
    echo "freecad appimage sha256: $FREECAD_SHA256"
    echo "freecad-mcp git SHA: $FCMCP_SHA"
    echo "freecad-mcp addon version: $(grep -o '<version>[^<]*</version>' "$FCMCP_DIR/addon/FreeCADMCP/package.xml" | head -1 | sed 's/<[^>]*>//g')"
    "$VENV_DIR/bin/python" - <<'PY'
import importlib.metadata as md
for pkg in ("trimesh", "manifold3d", "cadquery", "ezdxf", "numpy"):
    print("%s: %s" % (pkg, md.version(pkg)))
try:
    import OCP
    print("OCP: %s (via cadquery)" % md.version("cadquery-ocp"))
except Exception:
    pass
PY
} > "$VERSIONS_FILE"
LOG "versions recorded in $VERSIONS_FILE"
LOG "setup complete"
