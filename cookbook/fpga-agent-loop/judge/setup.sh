#!/bin/bash
set -euo pipefail

# Judge toolchain setup for fpga-agent-loop
# Installs OSS CAD Suite 2026-09-27, RISC-V GCC, and riscv-tests

# Constants from SPEC.md
OSS_CAD_SUITE_URL="https://github.com/YosysHQ/oss-cad-suite-build/releases/download/2026-09-27/oss-cad-suite-linux-x64-20260927.tgz"
OSS_CAD_SUITE_SHA256="8af3500957e8a304a9bb67ecbcd1e9a7a8bc6ae0813075cc812bfac6143aed86"

# RISC-V GCC constants - using xPack rv32i/ilp32 capable version
# As of 2026-10-14, using xPack riscv-none-elf-gcc v15.2.0-1 released 2025-10-23 (older than two weeks)
RISCV_GCC_VERSION="15.2.0-1"
RISCV_GCC_URL="https://github.com/xpack-dev-tools/riscv-none-elf-gcc-xpack/releases/download/v${RISCV_GCC_VERSION}/xpack-riscv-none-elf-gcc-${RISCV_GCC_VERSION}-linux-x64.tar.gz"
# SHA256 for xpack-riscv-none-elf-gcc-15.2.0-1-linux-x64.tar.gz
RISCV_GCC_SHA256="aaaa8060c914851a3e5ee1ba82cc3d6f80972f90638a05c6e823a37557a33758"

# riscv-tests constants
# Using commit from September 2026 (older than two weeks from 2026-10-14)
RISCV_TESTS_SHA="7b68f7b91f827f8d94cc1c57ff123752c5c8f704"
RISCV_TESTS_REPO="https://github.com/riscv-software-src/riscv-tests.git"

# Installation directory
TOOLCHAIN_DIR="$HOME/riscv-toolchain"
OSS_CAD_SUITE_DIR="$TOOLCHAIN_DIR/oss-cad-suite"
RISCV_GCC_DIR="$TOOLCHAIN_DIR/riscv-none-elf"
RISCV_TESTS_DIR="$TOOLCHAIN_DIR/riscv-tests"

# Create toolchain directory
mkdir -p "$TOOLCHAIN_DIR"

# Function to download and verify tarball
download_and_verify() {
    local url="$1"
    local expected_sha256="$2"
    local output_file="$3"

    echo "Downloading $url"
    curl -L --retry 3 -o "$output_file" "$url"

    echo "Verifying SHA256"
    local actual_sha256=$(sha256sum "$output_file" | cut -d' ' -f1)
    if [[ "$actual_sha256" != "$expected_sha256" ]]; then
        echo "ERROR: SHA256 mismatch!"
        echo "Expected: $expected_sha256"
        echo "Got: $actual_sha256"
        return 1
    fi
    echo "SHA256 verified"
}

# Function to check if apt-get update succeeded
check_apt_update() {
    echo "Checking apt package lists..."
    if ! apt-get update 2>/dev/null; then
        echo "WARNING: apt-get update failed or returned empty package lists"
        return 1
    fi
    return 0
}

# Install OSS CAD Suite
if [[ ! -d "$OSS_CAD_SUITE_DIR" ]]; then
    echo "Installing OSS CAD Suite 2026-09-27..."
    OSS_CAD_SUITE_TARBALL="$TOOLCHAIN_DIR/oss-cad-suite.tgz"
    download_and_verify "$OSS_CAD_SUITE_URL" "$OSS_CAD_SUITE_SHA256" "$OSS_CAD_SUITE_TARBALL"
    tar -xzf "$OSS_CAD_SUITE_TARBALL" -C "$TOOLCHAIN_DIR"
    rm "$OSS_CAD_SUITE_TARBALL"
    # The tarball extracts directly to oss-cad-suite directory
else
    echo "OSS CAD Suite already installed"
fi

# Install RISC-V GCC
if [[ ! -d "$RISCV_GCC_DIR" ]]; then
    echo "Installing RISC-V GCC..."
    RISCV_GCC_TARBALL="$TOOLCHAIN_DIR/riscv-none-elf-gcc.tar.gz"
    download_and_verify "$RISCV_GCC_URL" "$RISCV_GCC_SHA256" "$RISCV_GCC_TARBALL"
    tar -xzf "$RISCV_GCC_TARBALL" -C "$TOOLCHAIN_DIR"
    rm "$RISCV_GCC_TARBALL"
    # Rename extracted directory to expected name
    mv "$TOOLCHAIN_DIR/xpack-riscv-none-elf-gcc-${RISCV_GCC_VERSION}" "$RISCV_GCC_DIR"
else
    echo "RISC-V GCC already installed"
fi

# Install riscv-tests
if [[ ! -d "$RISCV_TESTS_DIR" ]]; then
    echo "Cloning riscv-tests..."
    git clone "$RISCV_TESTS_REPO" "$RISCV_TESTS_DIR"
    # Checkout specific SHA - need to get from SPEC
    git -C "$RISCV_TESTS_DIR" checkout "$RISCV_TESTS_SHA"
else
    echo "riscv-tests already installed"
fi

# Add to PATH if not already there
if [[ ":$PATH:" != *":$OSS_CAD_SUITE_DIR/bin:"* ]]; then
    echo "Adding OSS CAD Suite to PATH in ~/.bashrc"
    echo "export PATH=\"$OSS_CAD_SUITE_DIR/bin:\$PATH\"" >> ~/.bashrc
fi

if [[ ":$PATH:" != *":$RISCV_GCC_DIR/bin:"* ]]; then
    echo "Adding RISC-V GCC to PATH in ~/.bashrc"
    echo "export PATH=\"$RISCV_GCC_DIR/bin:\$PATH\"" >> ~/.bashrc
fi

echo "Toolchain setup complete!"
echo "Please restart your shell or run: source ~/.bashrc"
