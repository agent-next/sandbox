#!/usr/bin/env bash
# judge/setup.sh — install pinned tools for KiCad PCB demo
# Run from cookbook/kicad-pcb/

set -euo pipefail

KICAD_VERSION="9.0.9"
KICAD_TARBALL="kicad-${KICAD_VERSION}-x86_64.AppImage.tar"
KICAD_URL="https://github.com/KiCad/kicad-source-mirror/releases/download/${KICAD_VERSION}/${KICAD_TARBALL}"
KICAD_SHA256="796bc651078618a54dc20df77ada2f01ba1ea9435e167bb9b7673a006289a80b"
PYGERBER_VERSION="1.0.0"

INSTALL_DIR="${HOME}/.local/kicad-pcb-demo"
BIN_DIR="${INSTALL_DIR}/bin"
LIB_DIR="${INSTALL_DIR}/lib"

echo "=== KiCad PCB Demo Judge Setup ==="
echo "Installing to: ${INSTALL_DIR}"
echo "KiCad version: ${KICAD_VERSION}"
echo "pygerber version: ${PYGERBER_VERSION}"

mkdir -p "${BIN_DIR}" "${LIB_DIR}"

# --- KiCad ---
KICAD_APPIMAGE="${BIN_DIR}/kicad-${KICAD_VERSION}-x86_64.AppImage"
KICAD_CLI_WRAPPER="${BIN_DIR}/kicad-cli"

if [[ -x "${KICAD_CLI_WRAPPER}" ]] && APPIMAGE_EXTRACT_AND_RUN=1 "${KICAD_APPIMAGE}" kicad-cli --version 2>/dev/null | grep -q "${KICAD_VERSION}"; then
    echo "KiCad ${KICAD_VERSION} already installed"
else
    echo "Downloading KiCad ${KICAD_VERSION}..."
    cd /tmp
    if [[ ! -f "${KICAD_TARBALL}" ]]; then
        curl -L -o "${KICAD_TARBALL}" "${KICAD_URL}"
    fi
    echo "Verifying SHA256..."
    echo "${KICAD_SHA256}  ${KICAD_TARBALL}" | sha256sum -c -
    echo "Extracting..."
    tar -xf "${KICAD_TARBALL}"
    chmod +x "kicad-${KICAD_VERSION}-x86_64.AppImage"
    mv "kicad-${KICAD_VERSION}-x86_64.AppImage" "${KICAD_APPIMAGE}"
    # Extract AppImage to get libraries
    "${KICAD_APPIMAGE}" --appimage-extract >/dev/null 2>&1
    cp -rf squashfs-root/usr/share/kicad "${LIB_DIR}/"
    rm -rf squashfs-root
    echo "KiCad ${KICAD_VERSION} installed"
fi

# Create kicad-cli wrapper that uses APPIMAGE_EXTRACT_AND_RUN
cat > "${KICAD_CLI_WRAPPER}" << 'EOF'
#!/usr/bin/env bash
# Wrapper for kicad-cli that uses APPIMAGE_EXTRACT_AND_RUN
APPIMAGE="${HOME}/.local/kicad-pcb-demo/bin/kicad-9.0.9-x86_64.AppImage"
export APPIMAGE_EXTRACT_AND_RUN=1
exec "${APPIMAGE}" kicad-cli "$@"
EOF
chmod +x "${KICAD_CLI_WRAPPER}"

# --- pygerber ---
if python3 -c "import pygerber; assert pygerber.__version__ == '${PYGERBER_VERSION}'" 2>/dev/null; then
    echo "pygerber ${PYGERBER_VERSION} already installed"
else
    echo "Installing pygerber ${PYGERBER_VERSION}..."
    pip3 install --user "pygerber==${PYGERBER_VERSION}" >/dev/null
    echo "pygerber ${PYGERBER_VERSION} installed"
fi

# --- gerbv ---
if command -v gerbv >/dev/null 2>&1; then
    echo "gerbv already installed"
else
    echo "Installing gerbv..."
    sudo apt-get update -qq && sudo apt-get install -y -qq gerbv >/dev/null
    echo "gerbv installed"
fi

# Verify all tools
echo ""
echo "=== Verification ==="
"${KICAD_CLI_WRAPPER}" --version
python3 -c "import pygerber; print(f'pygerber {pygerber.__version__}')"
gerbv --version 2>&1 | head -1

echo ""
echo "Setup complete. Add to PATH: export PATH=\"${BIN_DIR}:\$PATH\""
echo "KICAD_CLI=\"${KICAD_CLI_WRAPPER}\""
echo "KICAD_LIBS=\"${LIB_DIR}/kicad\""