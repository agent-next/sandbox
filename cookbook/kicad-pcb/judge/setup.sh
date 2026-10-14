#!/usr/bin/env bash
# judge/setup.sh — install the pinned KiCad toolchain for this demo.
#
# Installs KiCad 9.0.9 (official lite AppImage tarball from the KiCad
# GitHub release mirror, SHA256-checked) into
#     $KICAD_DEMO_HOME   (default: ~/.local/kicad-pcb-demo)
# and writes a `kicad-cli` wrapper plus VERSIONS.txt recording exact
# tool versions. Idempotent: a verified install is reused.
#
# Tooling order per the demo standard: official release tarball only;
# no distribution packages are needed. KiCad 9.0.9 was released
# 2025-04-24 — well over two weeks old.

set -euo pipefail

KICAD_VERSION="9.0.9"
KICAD_TARBALL="kicad-${KICAD_VERSION}-x86_64-lite.AppImage.tar"
KICAD_URL="https://github.com/KiCad/kicad-source-mirror/releases/download/${KICAD_VERSION}/${KICAD_TARBALL}"
KICAD_SHA256="a54c3ff9072da707b360d698f070002dfcc8f557169d2f5993738be02a61e540"

DEMO_HOME="${KICAD_DEMO_HOME:-$HOME/.local/kicad-pcb-demo}"
BIN_DIR="$DEMO_HOME/bin"
APP_DIR="$DEMO_HOME/appimage"
CLI_WRAPPER="$BIN_DIR/kicad-cli"

echo "=== KiCad PCB demo — judge setup ==="
echo "install dir : $DEMO_HOME"
echo "KiCad       : $KICAD_VERSION (lite AppImage, sha256 pinned)"

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing dependency: $1" >&2; exit 1; }; }
need curl; need tar; need sha256sum; need python3

python3 -c 'import sys; assert sys.version_info >= (3, 10), sys.version' \
    || { echo "need python3 >= 3.10" >&2; exit 1; }

mkdir -p "$BIN_DIR" "$APP_DIR"

if [[ -x "$APP_DIR/bin/kicad-cli" ]] \
    && "$APP_DIR/bin/kicad-cli" --version 2>/dev/null | grep -q "$KICAD_VERSION"; then
    echo "KiCad $KICAD_VERSION already installed — reusing"
else
    WORK=$(mktemp -d)
    trap 'rm -rf "$WORK"' EXIT
    cd "$WORK"
    echo "downloading $KICAD_URL"
    curl -fL --retry 3 -o "$KICAD_TARBALL" "$KICAD_URL"
    echo "verifying sha256"
    echo "$KICAD_SHA256  $KICAD_TARBALL" | sha256sum -c -
    tar xf "$KICAD_TARBALL"
    chmod +x "kicad-${KICAD_VERSION}-x86_64-lite.AppImage"
    "./kicad-${KICAD_VERSION}-x86_64-lite.AppImage" --appimage-extract >/dev/null
    rm -rf "$APP_DIR"
    mkdir -p "$APP_DIR"
    cp -a squashfs-root/. "$APP_DIR/"
    cd - >/dev/null
    rm -rf "$WORK"; trap - EXIT
    echo "installed"
fi

cat > "$CLI_WRAPPER" <<EOF
#!/usr/bin/env bash
exec "$APP_DIR/bin/kicad-cli" "\$@"
EOF
chmod +x "$CLI_WRAPPER"

KICAD_VER_OUT="$("$CLI_WRAPPER" --version)"
PY_VER="$(python3 --version 2>&1)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for vf in "$DEMO_HOME/VERSIONS.txt" "$SCRIPT_DIR/VERSIONS.txt"; do
cat > "$vf" <<EOF
kicad-cli    : $KICAD_VER_OUT
kicad package: $KICAD_TARBALL
kicad url    : $KICAD_URL
kicad sha256 : $KICAD_SHA256
python3      : $PY_VER  ($(command -v python3))
EOF
done

echo "--- VERSIONS.txt ---"
cat "$DEMO_HOME/VERSIONS.txt"
echo "kicad-cli wrapper: $CLI_WRAPPER"
echo "KiCad share dir  : $APP_DIR/usr/share/kicad"
echo "Setup OK"
