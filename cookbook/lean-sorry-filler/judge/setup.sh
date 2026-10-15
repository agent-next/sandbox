#!/bin/sh
# Install the pinned Lean 4 toolchain into $HOME/.elan, idempotently.
#
#   elan v4.2.4        from the official GitHub release tarball (sha256-checked)
#   Lean 4 + lake v4.34.1  from the official release tarball (sha256-checked),
#                       extracted straight into elan's toolchain store and set
#                       as the default toolchain, so `lake` resolves the
#                       fixture's lean-toolchain with no further network access.
#
# If the exact tarballs are already present next to this script or in
# $LSF_CACHE (e.g. pre-seeded in an image), they are used and no download
# happens; otherwise they are downloaded from the official release URLs.
# Licence: elan and Lean 4 are Apache-2.0 (https://github.com/leanprover/lean4,
# https://github.com/leanprover/elan).
#
# Writes judge/VERSIONS.txt with the exact versions installed.

set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
ELAN_DIR="${ELAN_HOME:-$HOME/.elan}"
TOOLCHAINS="$ELAN_DIR/toolchains"
LEAN_VER="4.34.1"
ELAN_VER="4.2.4"
LEAN_SHA256="47bf4bbd78f70c2e9670598ab7124d92b6efb7330ff33e5fbb4030f6fd72e4e4"
ELAN_SHA256="42b94d4244e8353142c456ec0e4ca6528fd898a6c604d4059f494e706e431f63"
LEAN_URL="https://github.com/leanprover/lean4/releases/download/v4.34.1/lean-4.34.1-linux.tar.zst"
ELAN_URL="https://github.com/leanprover/elan/releases/download/v4.2.4/elan-x86_64-unknown-linux-gnu.tar.gz"
TRIPLET="leanprover/lean4:v4.34.1"

case "$(uname -s):$(uname -m)" in
    Linux:x86_64) ;;
    *) echo "setup.sh: unsupported platform $(uname -s) $(uname -m) \
(supported: x86-64 Linux)" >&2; exit 2 ;;
esac

fetch() { # fetch <url> <sha256> <dest-file>
    url=$1; want=$2; dest=$3
    if [ -f "$dest" ] && echo "$want  $dest" | sha256sum -c --quiet 2>/dev/null; then
        echo "setup.sh: using cached $(basename "$dest") (sha256 ok)"
        return 0
    fi
    echo "setup.sh: downloading $(basename "$dest") from the pinned release URL"
    curl -fsSL --retry 3 -o "$dest.part" "$url"
    echo "$want  $dest.part" | sha256sum -c --quiet
    mv "$dest.part" "$dest"
}

export ELAN_HOME="$ELAN_DIR"
mkdir -p "$ELAN_DIR/bin" "$TOOLCHAINS"

# ---- elan (the version manager and proxy binary) --------------------------
if [ ! -x "$ELAN_DIR/bin/elan" ] || ! "$ELAN_DIR/bin/elan" --version 2>/dev/null \
        | grep -q "elan $ELAN_VER"; then
    work=$(mktemp -d)
    trap 'rm -rf "$work"' EXIT
    fetch "$ELAN_URL" "$ELAN_SHA256" "$work/elan.tar.gz"
    # untrusted archive: extract into its own empty dir, then copy the one
    # expected binary out by name
    mkdir "$work/x"
    tar -xzf "$work/elan.tar.gz" -C "$work/x"
    [ -f "$work/x/elan-init" ] || { echo "setup.sh: elan tarball lacks elan-init" >&2; exit 2; }
    cp "$work/x/elan-init" "$ELAN_DIR/bin/elan"
    chmod +x "$ELAN_DIR/bin/elan"
fi

# ---- Lean + lake (single toolchain, no elan download path) -----------------
if [ ! -x "$TOOLCHAINS/$TRIPLET/bin/lean" ] || \
    ! "$TOOLCHAINS/$TRIPLET/bin/lean" --version 2>/dev/null | grep -q "version $LEAN_VER"; then
    work=$(mktemp -d)
    trap 'rm -rf "$work"' EXIT
    fetch "$LEAN_URL" "$LEAN_SHA256" "$work/lean.tar.zst"
    # untrusted archive: extract into its own empty dir, then rsync the one
    # expected tree into the toolchain store
    mkdir "$work/x"
    tar -x --zstd -f "$work/lean.tar.zst" -C "$work/x"
    [ -x "$work/x/lean-4.34.1-linux/bin/lean" ] || \
        { echo "setup.sh: lean tarball has unexpected layout" >&2; exit 2; }
    rm -rf "$TOOLCHAINS/$TRIPLET"
    mkdir -p "$TOOLCHAINS/$TRIPLET"
    cp -a "$work/x/lean-4.34.1-linux/." "$TOOLCHAINS/$TRIPLET/"
fi

# elan needs its proxy shims (lean, lake, ...) on PATH pointing at itself
if [ -x "$ELAN_DIR/bin/elan" ]; then
    for tool in lean lake leanc leanchecker; do
        ln -sf elan "$ELAN_DIR/bin/$tool"
    done
fi
PATH="$ELAN_DIR/bin:$PATH"
export PATH

# default toolchain = the pinned one (also satisfies the fixture's
# lean-toolchain without any elan network resolution)
if ! "$ELAN_DIR/bin/elan" toolchain list 2>/dev/null | grep -q "v$LEAN_VER (default)"; then
    "$ELAN_DIR/bin/elan" default "$TRIPLET" 2>/dev/null \
        || printf 'default_toolchain = "%s"\n' "$TRIPLET" > "$ELAN_DIR/settings.toml"
fi

# ---- record what actually got installed ------------------------------------
{
    echo "## elan $("$ELAN_DIR/bin/elan" --version 2>/dev/null | head -1)"
    echo "## lean $("$ELAN_DIR/bin/lean" --version 2>/dev/null | head -1)"
    echo "## lake $(cd "$TOOLCHAINS/$TRIPLET" && ./bin/lake --version 2>/dev/null | head -1)"
    echo "## elan home: $ELAN_DIR"
    echo "## toolchain: $TRIPLET"
} > "$HERE/VERSIONS.txt"

if grep -q "version $LEAN_VER" "$HERE/VERSIONS.txt"; then
    echo "setup.sh: ok"
else
    echo "setup.sh: installed lean does not report v$LEAN_VER" >&2
    cat "$HERE/VERSIONS.txt" >&2
    exit 1
fi
