#!/usr/bin/env bash
#
# setup.sh -- install the toolchain this demo judges with, pinned and
# sha256-checked, into $HOME.  Idempotent: a second run is a no-op.
#
# Sourced in this order of preference:
#   1. official release tarball, sha256 verified   (ARM GNU toolchain)
#   2. Debian packages, exact version recorded     (QEMU)
# Nothing is downloaded from a `latest` URL; every version is spelled out.

set -euo pipefail

PREFIX="${HOME}/.firmware-qemu-tools"
BIN="${PREFIX}/bin"
mkdir -p "${PREFIX}" "${BIN}"

log() { printf 'setup: %s\n' "$*"; }

# --------------------------------------------------------------------------
# 1. Arm GNU toolchain -- official release tarball, pinned, sha256-checked.
# --------------------------------------------------------------------------
TC_VER=13.3.rel1
TC_FILE="arm-gnu-toolchain-${TC_VER}-x86_64-arm-none-eabi.tar.xz"
TC_URL="https://armkeil.blob.core.windows.net/developer/Files/downloads/gnu/${TC_VER}/binrel/${TC_FILE}"
TC_DIR="${PREFIX}/arm-gnu-toolchain-${TC_VER}-x86_64-arm-none-eabi"
TC_SHA256="95c011cee430e64dd6087c75c800f04b9c49832cc1000127a92a97f9c8d83af4"

# The tarball is ~147 MB; keep it out of the repo and out of the image.
DL="${HOME}/.cache/firmware-qemu"
mkdir -p "${DL}"

if [ ! -x "${TC_DIR}/bin/arm-none-eabi-gcc" ]; then
    if [ ! -s "${DL}/${TC_FILE}" ]; then
        log "downloading ${TC_FILE}"
        curl -fsSL --retry 5 --retry-delay 3 --retry-all-errors \
            -o "${DL}/${TC_FILE}.part" "${TC_URL}"
        mv "${DL}/${TC_FILE}.part" "${DL}/${TC_FILE}"
    else
        log "reusing cached ${TC_FILE}"
    fi
    log "verifying sha256 of ${TC_FILE}"
    echo "${TC_SHA256}  ${DL}/${TC_FILE}" | sha256sum -c -
    log "extracting ${TC_FILE}"
    tar -xJf "${DL}/${TC_FILE}" -C "${PREFIX}"
else
    log "toolchain ${TC_VER} already present"
fi

TC_COMPILER="${TC_DIR}/bin/arm-none-eabi-gcc"
if ! [ -x "${TC_COMPILER}" ]; then
    echo "setup: ${TC_COMPILER} missing after install" >&2
    exit 1
fi

# --------------------------------------------------------------------------
# 2. QEMU -- Debian package, exact version pinned, sha256-checked.
#    The .deb is downloaded from the Debian pool at a pinned URL and verified
#    before install; apt is used only to resolve its library dependencies.
#    The image's apt lists can be empty, so refresh before trusting them.
# --------------------------------------------------------------------------
QEMU_PKG_VER="1:7.2+dfsg-7+deb12u18+b3"
QEMU_DEB="qemu-system-arm_7.2%2bdfsg-7%2bdeb12u18%2bb3_amd64.deb"
QEMU_URL="http://deb.debian.org/debian/pool/main/q/qemu/${QEMU_DEB}"
QEMU_SHA256="78c4adf16152bb8ae1994784e966365128cae04d8ae37bc161bb0b6617c17d9c"

have_qemu() {
    command -v qemu-system-arm >/dev/null 2>&1
}

if ! have_qemu; then
    log "apt-get update (image apt lists may be empty)"
    sudo -n env DEBIAN_FRONTEND=noninteractive apt-get update -qq
    if [ ! -s "${DL}/${QEMU_DEB//%2b/+}" ]; then
        log "downloading ${QEMU_DEB}"
        curl -fsSL --retry 5 --retry-delay 3 --retry-all-errors \
            -o "${DL}/${QEMU_DEB//%2b/+}.part" "${QEMU_URL}"
        mv "${DL}/${QEMU_DEB//%2b/+}.part" "${DL}/${QEMU_DEB//%2b/+}"
    else
        log "reusing cached ${QEMU_DEB//%2b/+}"
    fi
    log "verifying sha256 of qemu-system-arm ${QEMU_PKG_VER}"
    echo "${QEMU_SHA256}  ${DL}/${QEMU_DEB//%2b/+}" | sha256sum -c -
    log "installing qemu-system-arm (${QEMU_PKG_VER}) with apt-resolved deps"
    sudo -n env DEBIAN_FRONTEND=noninteractive \
        apt-get install -y --no-install-recommends \
        "${DL}/${QEMU_DEB//%2b/+}"
else
    log "qemu-system-arm already present"
fi

if ! have_qemu; then
    echo "setup: qemu-system-arm not installed" >&2
    exit 1
fi

QEMU_VERSION="$(qemu-system-arm --version | head -1 | awk '{print $4}')"

# --------------------------------------------------------------------------
# 3. Record what is on the path, so the receipt is reproducible.
#    VERSIONS.txt lives in judge/ next to the scripts that installed the
#    tools: it is the `--version` output of every tool this setup placed on
#    the machine, plus the sha256 each download was verified against.
# --------------------------------------------------------------------------
cat > "${PREFIX}/versions.env" <<EOF
ARM_TOOLCHAIN_VERSION=${TC_VER}
ARM_TOOLCHAIN_SHA256=${TC_SHA256}
QEMU_PACKAGE_VERSION=${QEMU_PKG_VER}
QEMU_REPORTED_VERSION=${QEMU_VERSION}
ARM_GCC_VERSION=$("${TC_COMPILER}" -dumpversion)
ARM_GCC_FULL_VERSION=$("${TC_COMPILER}" -dumpfullversion)
EOF

JUDGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
{
    echo "# VERSIONS.txt -- recorded by judge/setup.sh"
    echo "# One entry per tool the demo depends on: the pinned version, the"
    echo "# sha256 the download was verified against, and the tool's own"
    echo "# --version output as actually installed."
    echo
    echo "arm-gnu-toolchain ${TC_VER} (x86_64 -> arm-none-eabi)"
    echo "  url    : ${TC_URL}"
    echo "  sha256 : ${TC_SHA256}"
    "${TC_COMPILER}" --version | sed 's/^/  /'
    echo
    echo "qemu-system-arm ${QEMU_PKG_VER} (Debian 12 package)"
    echo "  url    : ${QEMU_URL}"
    echo "  sha256 : ${QEMU_SHA256}"
    qemu-system-arm --version | sed 's/^/  /'
    echo
    echo "python3 (judge oracle: zlib.crc32, random.Random -- stdlib only)"
    if command -v python3 >/dev/null 2>&1; then
        python3 --version 2>&1 | sed 's/^/  /'
    else
        echo "  NOT FOUND"
    fi
    echo
    echo "make"
    if command -v make >/dev/null 2>&1; then
        make --version | head -1 | sed 's/^/  /'
    else
        echo "  NOT FOUND"
    fi
} > "${JUDGE_DIR}/VERSIONS.txt"

log "wrote ${PREFIX}/versions.env"
log "wrote ${JUDGE_DIR}/VERSIONS.txt"
log "done"
