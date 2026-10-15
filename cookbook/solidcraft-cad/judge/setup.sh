#!/usr/bin/env bash
# Install pinned tools for the solidcraft-cad judge, idempotently.
#   SolidCraft 0.10.1 (official GitHub release tarball, sha256-checked)
#   OCP / OpenCascade + media deps in a venv (judge/requirements.txt, hashed)
set -euo pipefail

SC_VERSION="0.10.1"
SC_NAME="solidcraft-${SC_VERSION}-linux-x86_64"
SC_URL="https://github.com/bherbruck/solidcraft/releases/download/v${SC_VERSION}/${SC_NAME}.tar.gz"
SC_SHA256="2dee82978900dab0f50d092446eef924f4fd6da99121aa6e0fa041c224ca700b"

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="$HOME/.local"
CLI="$PREFIX/$SC_NAME/bin/solidcraft-cli"
VENV="$PREFIX/solidcraft-judge-venv"

if [ "$(uname -m)" != "x86_64" ]; then
    echo "setup: x86_64 Linux required (got $(uname -m))" >&2
    exit 1
fi

if [ -x "$CLI" ] && "$CLI" --version 2>/dev/null | grep -qx "solidcraft-cli $SC_VERSION"; then
    echo "setup: SolidCraft $SC_VERSION already installed (skipping download)"
else
    echo "setup: downloading SolidCraft $SC_VERSION release tarball"
    tmpdir="$(mktemp -d)"
    trap 'rm -rf "$tmpdir"' EXIT
    curl -fsSL --retry 3 -o "$tmpdir/sc.tar.gz" "$SC_URL"
    echo "$SC_SHA256  $tmpdir/sc.tar.gz" | sha256sum -c - || {
        echo "setup: sha256 mismatch on $SC_NAME.tar.gz" >&2
        exit 1
    }
    mkdir -p "$PREFIX"
    tar xzf "$tmpdir/sc.tar.gz" -C "$PREFIX"
    "$CLI" --version
fi

python3 - <<'PY' || { echo "setup: python3 3.12 or 3.13 required" >&2; exit 1; }
import sys
assert (3, 12) <= sys.version_info[:2] <= (3, 13), sys.version
PY

# Reuse a venv only if it was installed from this exact requirements.txt and
# every pinned package still has its pinned version.
REQ_SHA="$(sha256sum "$JDIR/requirements.txt" | cut -d' ' -f1)"
pins_ok() {
    "$VENV/bin/python" -I - "$JDIR/requirements.txt" <<'PY' 2>/dev/null
import importlib.metadata as md, re, sys
for ln in open(sys.argv[1]):
    m = re.match(r"([A-Za-z0-9_.-]+)==([^\s;\\]+)", ln.strip())
    if m and md.version(m[1]) != m[2]:
        sys.exit(1)
PY
}
if [ -x "$VENV/bin/python" ] && [ "$(cat "$VENV/.requirements.sha256" 2>/dev/null)" = "$REQ_SHA" ] && pins_ok; then
    echo "setup: judge venv matches requirements.txt (skipping pip)"
else
    if ! python3 -m venv "$VENV" 2>/dev/null; then
        # Debian ships venv separately; make sure apt actually has package lists.
        sudo apt-get update -qq
        [ -n "$(ls /var/lib/apt/lists/ 2>/dev/null | grep -v -e lock -e partial)" ] || {
            echo "setup: apt-get update fetched no package lists" >&2
            exit 1
        }
        sudo apt-get install -y -qq python3-venv
        python3 -m venv "$VENV"
    fi
    "$VENV/bin/pip" install -q --disable-pip-version-check --no-cache-dir --require-hashes -r "$JDIR/requirements.txt"
    echo "$REQ_SHA" > "$VENV/.requirements.sha256"
fi
# OCP needs libGL/libX11 at import time on minimal images.
if ! "$VENV/bin/python" -c "from OCP.STEPControl import STEPControl_Reader" 2>/dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq libgl1 libglu1-mesa libxrender1 libxkbcommon0 libegl1 libx11-6
    "$VENV/bin/python" -c "from OCP.STEPControl import STEPControl_Reader"
fi

echo "setup: tool versions"
{
    echo "# solidcraft-cad judge: versions installed by judge/setup.sh"
    echo "# ($(uname -sm))"
    "$CLI" --version
    echo "solidcraft release sha256 $SC_SHA256"
    echo "python3 $("$VENV/bin/python" -c 'import sys; print(sys.version.split()[0])')"
    "$VENV/bin/pip" freeze --all | grep -iE '^(cadquery-ocp|vtk|numpy|matplotlib)=='
} | tee "$JDIR/VERSIONS.txt"
echo "setup: wrote $JDIR/VERSIONS.txt"
echo "setup: done"
