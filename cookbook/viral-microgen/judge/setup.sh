#!/usr/bin/env bash
# Install pinned tools for the viral-microgen judge, idempotently, into
# $HOME.  Two independent QR reference libraries are the point of the
# qr_scans gate, so both are pinned exactly:
#
#   zbarimg 0.23.92   (Debian bookworm package zbar-tools) -- sha256-checked
#                     .deb download from the Debian pool
#   zxing-cpp 2.3.0   (PyPI wheel) -- sha256-checked download, installed into
#                     a private virtualenv under $HOME so the system Python
#                     is untouched
#
# Everything else is the Python standard library plus numpy and Pillow, which
# the judge itself uses (judge/requirements.txt, pinned).
set -euo pipefail

ZBAR_VERSION="0.23.92-7+deb12u1"
ZBAR_URL="https://deb.debian.org/debian/pool/main/z/zbar/zbar-tools_0.23.92-7+deb12u1_amd64.deb"
ZBAR_SHA256="6bd3fcd8530e1f4acfc7ce80eed14cdfcabeb527a6b8fd59eee52a24645e1159"
ZBAR_LIB_URL="https://deb.debian.org/debian/pool/main/z/zbar/libzbar0_0.23.92-7+deb12u1_amd64.deb"
ZBAR_LIB_SHA256="c1f40f1af091f92cda290ca53e139081c1d06ca0cad5707eba022d053a8482a6"

ZXING_VERSION="2.3.0"
# one sha256-pinned manylinux x86_64 wheel per supported CPython minor
zxing_url() {
    case "$1" in
        310) echo "https://files.pythonhosted.org/packages/64/6c/1bf6e40fadcb73958f672385c5186b062485c818cecc32b36ddf5666da1e/zxing_cpp-2.3.0-cp310-cp310-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl" ;;
        311) echo "https://files.pythonhosted.org/packages/2e/d3/75a6d6485e704527c5e18f825f6bd6b5e5129f56c3526f28142911b48410/zxing_cpp-2.3.0-cp311-cp311-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl" ;;
        312) echo "https://files.pythonhosted.org/packages/95/30/3143bf75944d65c9432349a79b97f9414965a44875ec9eeb5745592b4ecd/zxing_cpp-2.3.0-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl" ;;
        313) echo "https://files.pythonhosted.org/packages/ce/5e/5784ad14f8514e4321f3a828dccc00ebcf70202f6ef967174d26bcb65568/zxing_cpp-2.3.0-cp313-cp313-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl" ;;
        *) return 1 ;;
    esac
}
zxing_sha() {
    case "$1" in
        310) echo "fd3f175f7b57cfbdea56afdb5335eaebaadeebc06e20a087d9aa3f99637c4aa5" ;;
        311) echo "64e5a4ff5168142d8b33ca648978c8ec4125c50b33aa1521e0c5344c6ffacef7" ;;
        312) echo "dec2805c0e9dec0d7707c97ca5196f98d2730d2dfcea80442807123b9f8ec850" ;;
        313) echo "7ba641ca5a0f19b97d7bc6a0212e61dab267a2b1a52a84946d02bdcd859ec318" ;;
        *) return 1 ;;
    esac
}

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${VIRAL_VENV:-$HOME/.viral-microgen-venv}"

tmpdir=""
cleanup() { [ -n "$tmpdir" ] && rm -rf "$tmpdir"; }
trap cleanup EXIT

# --- python -----------------------------------------------------------------
python3 - <<'EOF' || { echo "setup: python3 >= 3.10 required" >&2; exit 1; }
import sys
assert sys.version_info >= (3, 10), sys.version
EOF

# --- zbarimg ----------------------------------------------------------------
have_zbar="$(zbarimg --version 2>/dev/null || true)"
if [ "$have_zbar" = "$ZBAR_VERSION" ] || [ "$have_zbar" = "0.23.92" ]; then
    echo "setup: zbarimg $have_zbar already installed (skipping download)"
else
    tmpdir="$(mktemp -d)"
    echo "setup: downloading zbar-tools $ZBAR_VERSION from the Debian pool"
    curl -fsSL -o "$tmpdir/libzbar0.deb" "$ZBAR_LIB_URL"
    curl -fsSL -o "$tmpdir/zbar-tools.deb" "$ZBAR_URL"
    echo "$ZBAR_LIB_SHA256  $tmpdir/libzbar0.deb" | sha256sum -c - || {
        echo "setup: sha256 mismatch on libzbar0.deb" >&2; exit 1; }
    echo "$ZBAR_SHA256  $tmpdir/zbar-tools.deb" | sha256sum -c - || {
        echo "setup: sha256 mismatch on zbar-tools.deb" >&2; exit 1; }
    sudo apt-get update -qq
    sudo apt-get install -y -qq "$tmpdir/libzbar0.deb" "$tmpdir/zbar-tools.deb"
    got="$(zbarimg --version 2>/dev/null || true)"
    if [ "$got" != "0.23.92" ]; then
        echo "setup: installed zbarimg version '$got' != '0.23.92'" >&2
        exit 1
    fi
fi

# --- zxing-cpp + judge requirements, in a private venv ----------------------
if [ -x "$VENV/bin/python" ] && \
   "$VENV/bin/python" -c "import zxingcpp" 2>/dev/null && \
   [ "$("$VENV/bin/python" -c 'import importlib.metadata as m; print(m.version("zxing-cpp"))')" = "$ZXING_VERSION" ]; then
    echo "setup: zxing-cpp $ZXING_VERSION already installed in $VENV"
else
    [ -n "$tmpdir" ] || tmpdir="$(mktemp -d)"
    pyver="$(python3 -c 'import sys; print(f"{sys.version_info[0]}{sys.version_info[1]}")')"
    ZXING_URL="$(zxing_url "$pyver")" || {
        echo "setup: no pinned zxing-cpp wheel for CPython $pyver" >&2; exit 1; }
    ZXING_SHA256="$(zxing_sha "$pyver")"
    echo "setup: creating $VENV and installing zxing-cpp $ZXING_VERSION (cp$pyver)"
    python3 -m venv "$VENV"
    "$VENV/bin/python" -m pip install --quiet --upgrade pip
    whl="$tmpdir/$(basename "$ZXING_URL")"
    curl -fsSL -o "$whl" "$ZXING_URL"
    echo "$ZXING_SHA256  $whl" | sha256sum -c - || {
        echo "setup: sha256 mismatch on the zxing-cpp wheel" >&2; exit 1; }
    "$VENV/bin/python" -m pip install --quiet --no-deps "$whl"
    got="$("$VENV/bin/python" -c 'import importlib.metadata as m; print(m.version("zxing-cpp"))')"
    if [ "$got" != "$ZXING_VERSION" ]; then
        echo "setup: installed zxing-cpp '$got' != '$ZXING_VERSION'" >&2
        exit 1
    fi
fi

# numpy + Pillow for the judge, pinned with hashes from requirements.txt
"$VENV/bin/python" -m pip install --quiet \
    --require-hashes -r "$JDIR/requirements.txt"

# --- record what was actually installed -------------------------------------
{
    echo "# viral-microgen judge: versions installed by judge/setup.sh"
    echo "# ($(uname -sm))"
    echo "zbarimg $(zbarimg --version 2>/dev/null || echo 'missing')"
    echo "zbar-tools debian package: $(dpkg-query -W -f='${Version}' zbar-tools 2>/dev/null || echo 'n/a')"
    echo "zxing-cpp $("$VENV/bin/python" -c 'import importlib.metadata as m; print(m.version("zxing-cpp"))')"
    echo "numpy $("$VENV/bin/python" -c 'import numpy; print(numpy.__version__)')"
    echo "Pillow $("$VENV/bin/python" -c 'import PIL; print(PIL.__version__)')"
    echo "python3 $(python3 --version | awk '{print $2}')"
    echo "venv $VENV"
} > "$JDIR/VERSIONS.txt"
cat "$JDIR/VERSIONS.txt"

echo "setup: done"
