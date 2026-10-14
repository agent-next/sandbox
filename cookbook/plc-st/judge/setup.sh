#!/usr/bin/env bash
# cookbook/plc-st: install pinned toolchain idempotently into $HOME.
#
# Installs (into $HOME/.plc-st):
#   - MATIEC iec2c (commit 75d6e82..., sha256-pinned tarball) -> $PREFIX/bin/iec2c
#   - the C runtime headers it needs (shipped inside the MATIEC tree)
# Also installs the Debian build deps needed to compile MATIEC from source.
# Safe to re-run; uses exact versions, never "latest".
#
# Usage: bash judge/setup.sh
set -euo pipefail

# ---------------------------------------------------------------------------
# Pinned versions (source of truth: judge/VERSIONS.txt)
# ---------------------------------------------------------------------------
MATIEC_COMMIT="75d6e82cce5bc8b98ce03a417b106884cbb7ebb5"
MATIEC_SHA256="a679c8e69459c2e4a05850438e073866eeb695b598ff244029dac0ea5d8e9a08"
MATIEC_BASE="matiec-${MATIEC_COMMIT}"
MATIEC_TARBALL="matiec-${MATIEC_COMMIT}.tar.gz"
MATIEC_URL="https://github.com/thiagoralves/matiec/archive/${MATIEC_COMMIT}.tar.gz"

PREFIX="${HOME}/.plc-st"
SRC="${HOME}/.plc-st/src"
BIN="${PREFIX}/bin"
LIB="${PREFIX}/lib"             # MATIEC lib tree: *.txt + C/*.h

# ---------------------------------------------------------------------------
# apt: ensure the build-essential tools MATIEC needs are present.
# Pinned to Debian bookworm defaults; exact versions recorded in VERSIONS.txt.
# ---------------------------------------------------------------------------
apt_ensure() {
    if command -v bison >/dev/null 2>&1 && command -v flex >/dev/null 2>&1 \
        && command -v autoconf >/dev/null 2>&1 && command -v automake >/dev/null 2>&1 \
        && command -v libtoolize >/dev/null 2>&1; then
        return 0
    fi
    echo "[setup] installing Debian build deps (bison flex autoconf automake libtool ...)"
    sudo apt-get update -qq
    sudo apt-get install -y -qq \
        build-essential bison flex autoconf automake libtool pkg-config
}

# ---------------------------------------------------------------------------
# download and verify MATIEC (sha256-pinned)
# ---------------------------------------------------------------------------
fetch_matiec() {
    mkdir -p "${SRC}" "${BIN}"
    if [ -x "${BIN}/iec2c" ] && [ -f "${LIB}/ieclib.txt" ] && [ -f "${LIB}/C/iec_std_lib.h" ]; then
        echo "[setup] iec2c already installed -> ${BIN}/iec2c"
        return 0
    fi
    echo "[setup] downloading MATIEC ${MATIEC_COMMIT}"
    local tmp
    tmp="$(mktemp -d)"
    curl -fsSL --retry 3 -o "${tmp}/${MATIEC_TARBALL}" "${MATIEC_URL}"
    echo "${MATIEC_SHA256}  ${tmp}/${MATIEC_TARBALL}" | sha256sum -c - >/dev/null
    tar xzf "${tmp}/${MATIEC_TARBALL}" -C "${tmp}"
    echo "[setup] building iec2c from source (gcc/bison/flex)"
    (
        cd "${tmp}/${MATIEC_BASE}"
        autoreconf -i >/dev/null
        ./configure >/dev/null
        make -j"$(nproc)" >/dev/null
    )
    # install the compiler binary and a private copy of the full lib tree
    # (lib/*.txt standard-library sources for iec2c, lib/C/*.h runtime
    #  headers for the C link step)
    cp "${tmp}/${MATIEC_BASE}/iec2c" "${BIN}/iec2c"
    cp "${tmp}/${MATIEC_BASE}/iec2iec" "${BIN}/iec2iec" 2>/dev/null || true
    rm -rf "${PREFIX}/lib"
    cp -R "${tmp}/${MATIEC_BASE}/lib" "${PREFIX}/lib"
    rm -rf "${tmp}"
    echo "[setup] installed ${BIN}/iec2c"
}

# ---------------------------------------------------------------------------
apt_ensure
fetch_matiec

echo "[setup] done."
echo "  iec2c   -> ${BIN}/iec2c"
echo "  lib     -> ${LIB}"
"${BIN}/iec2c" -v 2>&1 | head -2 || true