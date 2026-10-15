#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 agent-next contributors
# SPDX-License-Identifier: Apache-2.0
#
# setup.sh — install the pinned toolchain for the nanousd-render demo into
# $HOME/.nanousd-render. Idempotent: re-running rebuilds nothing that is
# already in place (kept idempotent via sentinel files and cmake's own
# incremental build).
#
# Pinned pieces (versions echoed at the end into VERSIONS.txt):
#   - CMake 3.31.6 official release tarball (sha256-checked) -> $PREFIX/cmake
#     (needed because the renderer's pinned MaterialX v1.39.4 requires
#     cmake >= 3.26 and Debian bookworm ships 3.25)
#   - Debian bookworm packages (apt verifies sha256 itself): ninja-build,
#     build-essential, Mesa GLES/EGL + llvmpipe (libegl-mesa0 22.3.6),
#     python3-venv, curl, git
#   - omniverse-labs @ NANOUSD_COMMIT (tarball, sha256-checked) bringing
#     nanousd + nanousd-opengl-renderer sources; the renderer's own
#     FetchContent pins MaterialX v1.39.4 + meshoptimizer v0.24
#   - usd-core==25.5, numpy==2.2.6, pillow==11.2.1 via pip into $PREFIX/venv
#     (version-pinned; pip's own hash checking is not used because the wheel
#     set differs across platforms -- see judge/requirements.txt)
#
set -euo pipefail

DEMO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JUDGE_DIR="$DEMO_DIR/judge"
PREFIX="$HOME/.nanousd-render"
NANOUSD_COMMIT="ea045a027c4d0cc717174ed92f13ba56fffeb39d"
NANOUSD_TARBALL_URL="https://github.com/NVIDIA-Omniverse/omniverse-labs/archive/${NANOUSD_COMMIT}.tar.gz"
# sha256 of the GitHub-generated tarball for the pinned commit, recorded
# from the reference download: `curl -L <url> | sha256sum`.
NANOUSD_TARBALL_SHA256="6b15c9cef649abf43e097906c4df68bfc6d1d376993c7cf79583fad1a2cbfeee"

CMAKE_VERSION="3.31.6"
CMAKE_TARBALL="cmake-${CMAKE_VERSION}-linux-x86_64.tar.gz"
CMAKE_URL="https://github.com/Kitware/CMake/releases/download/v${CMAKE_VERSION}/${CMAKE_TARBALL}"
CMAKE_SHA256="5a1133ff103c71eb5120e2cc3de922733e7d8a26a98ae716397e8676adb367bf"

log() { printf '[setup] %s\n' "$*"; }
die() { printf '[setup] ERROR: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- apt deps
apt_install() {
    if [ "${SKIP_APT:-0}" = "1" ]; then return 0; fi
    export DEBIAN_FRONTEND=noninteractive
    if ! sudo -n true 2>/dev/null; then
        SUDO=""
    else
        SUDO="sudo"
    fi
    log "apt-get update (must fetch lists; an empty apt cache is not OK)"
    local out
    if ! out=$($SUDO apt-get update 2>&1); then
        die "apt-get update failed: $out"
    fi
    log "apt-get install build deps"
    $SUDO apt-get install -y --no-install-recommends \
        ca-certificates curl git xz-utils \
        build-essential pkg-config \
        cmake ninja-build \
        libegl1-mesa-dev libgl1-mesa-dev libgles2-mesa-dev \
        libegl-mesa0 libgl1-mesa-dri \
        python3 python3-venv >/dev/null
}

# ---------------------------------------------------------------- cmake
# MaterialX v1.39.4 (pinned by the renderer's FetchContent) needs
# cmake >= 3.26, Debian bookworm ships 3.25 -> install the official
# 3.31.6 release tarball, sha256-checked.
install_cmake() {
    if [ -x "$PREFIX/cmake/bin/cmake" ]; then
        if "$PREFIX/cmake/bin/cmake" --version | head -1 | grep -q "$CMAKE_VERSION"; then
            log "cmake $CMAKE_VERSION already installed"
            return 0
        fi
    fi
    local tmp; tmp="$(mktemp -d)"
    log "downloading cmake $CMAKE_VERSION"
    curl -fsSL "$CMAKE_URL" -o "$tmp/$CMAKE_TARBALL"
    echo "$CMAKE_SHA256  $tmp/$CMAKE_TARBALL" | sha256sum -c - \
        || die "cmake tarball sha256 mismatch"
    mkdir -p "$PREFIX/cmake"
    rm -rf "$PREFIX/cmake"/*
    tar -xzf "$tmp/$CMAKE_TARBALL" -C "$PREFIX/cmake" --strip-components=1
    rm -rf "$tmp"
}

# ---------------------------------------------------------------- sanity
check_cmake() {
    command -v ninja >/dev/null 2>&1 || die "ninja not found (apt install failed?)"
    "$PREFIX/cmake/bin/cmake" --version >/dev/null 2>&1 \
        || die "cmake $CMAKE_VERSION not usable"
}

# ---------------------------------------------------------------- nanousd source
fetch_nanousd() {
    local src="$PREFIX/src/omniverse-labs"
    if [ -f "$src/.pinned-$NANOUSD_COMMIT" ]; then
        log "omniverse-labs @ ${NANOUSD_COMMIT:0:8} already present"
        return 0
    fi
    local tmp; tmp="$(mktemp -d)"
    log "downloading omniverse-labs @ $NANOUSD_COMMIT"
    curl -fsSL "$NANOUSD_TARBALL_URL" -o "$tmp/src.tar.gz"
    echo "$NANOUSD_TARBALL_SHA256  $tmp/src.tar.gz" | sha256sum -c - \
        || die "omniverse-labs tarball sha256 mismatch"
    rm -rf "$src"
    mkdir -p "$src"
    tar -xzf "$tmp/src.tar.gz" -C "$src" --strip-components=1
    touch "$src/.pinned-$NANOUSD_COMMIT"
    rm -rf "$tmp"
}

# ---------------------------------------------------------------- nanousd build
build_nanousd() {
    local src="$PREFIX/src/omniverse-labs/projects/nanousd-labs/nanousd"
    local bld="$PREFIX/build/nanousd"
    if [ -f "$bld/.built" ]; then
        log "nanousd already built"
    else
        log "building nanousd (compliance tests on)"
        "$PREFIX/cmake/bin/cmake" -S "$src" -B "$bld" -G Ninja \
            -DCMAKE_BUILD_TYPE=Release \
            -DNANOUSD_BUILD_TESTS=ON
        "$PREFIX/cmake/bin/cmake" --build "$bld" -j "$(nproc)"
        log "running nanousd compliance_test"
        # The test binary finds its fixtures on a relative CWD path and
        # dlopen()s the backend by env var, so run it from the source tree.
        (cd "$src" && NANOUSD_BACKEND="$bld/Release/libnanousd.so" \
            "$bld/Release/compliance_test" >/dev/null) \
            || die "nanousd compliance_test failed"
        touch "$bld/.built"
    fi
}

# ---------------------------------------------------------------- renderer build
build_renderer() {
    local src="$PREFIX/src/omniverse-labs/projects/nanousd-labs/nanousd-opengl-renderer"
    local bld="$PREFIX/build/nanousd-opengl-renderer"
    if [ -f "$bld/.built" ]; then
        log "nanousd-opengl-renderer already built"
    else
        log "building nanousd-opengl-renderer (Ptex off, MDL off; pulls its own pinned MaterialX v1.39.4 + meshoptimizer v0.24 via FetchContent)"
        "$PREFIX/cmake/bin/cmake" -S "$src" -B "$bld" -G Ninja \
            -DCMAKE_BUILD_TYPE=Release \
            -DNUSD_ENABLE_PTEX=OFF \
            -DNUSD_ENABLE_MDL_SDK=OFF \
            -DNUSD_BUILD_TESTS=OFF \
            -DNANOUSD_DIR="$PREFIX/src/omniverse-labs/projects/nanousd-labs/nanousd"
        "$PREFIX/cmake/bin/cmake" --build "$bld" -j "$(nproc)"
        touch "$bld/.built"
    fi
}

# ---------------------------------------------------------------- judge drivers
build_drivers() {
    local nanousd_src="$PREFIX/src/omniverse-labs/projects/nanousd-labs/nanousd"
    local nanousd_bld="$PREFIX/build/nanousd"
    local rend_src="$PREFIX/src/omniverse-labs/projects/nanousd-labs/nanousd-opengl-renderer"
    local rend_bld="$PREFIX/build/nanousd-opengl-renderer"
    local out="$PREFIX/bin"
    mkdir -p "$out"
    log "compiling judge C drivers"
    # nanousd_dump: stage -> JSON through the pinned nanousd C API
    cc -O2 -std=c11 \
        -I"$nanousd_src/include" \
        "$JUDGE_DIR/nanousd_dump.c" \
        -L"$nanousd_bld" -lnanousdapi \
        -o "$out/nanousd_dump"

    # render_once: renderer's public viewer.h API -> raw RGBA (judge.py
    # wraps it into the PNG); reads view/proj/eye from a binary float file
    cc -O2 -std=c11 \
        -I"$rend_src/src" \
        "$JUDGE_DIR/render_once.c" \
        -L"$rend_bld" -lnusd_gles -lnusd_renderer_opengl \
        -L"$rend_bld/nanousd" -lnanousdapi \
        -Wl,-rpath,"$rend_bld" -Wl,-rpath,"$rend_bld/nanousd" \
        -lm -lEGL \
        -o "$out/render_once"

    # smoke: renderer must run headless on llvmpipe against the known-good scene
    log "renderer smoke: headless EGL on llvmpipe"
    "$JUDGE_DIR/render_smoke.sh" "$out/render_once" \
        "$DEMO_DIR/examples/good/scene.usda" \
        || die "renderer smoke failed (llvmpipe EGL not available?)"
}

# ---------------------------------------------------------------- python venv
install_python() {
    if [ ! -x "$PREFIX/venv/bin/python" ]; then
        log "creating venv"
        python3 -m venv "$PREFIX/venv"
    fi
    log "installing pinned python wheels"
    "$PREFIX/venv/bin/pip" install --no-cache-dir \
        --requirement "$JUDGE_DIR/requirements.txt"
}

# ---------------------------------------------------------------- versions
record_versions() {
    {
        echo "cmake: $("$PREFIX/cmake/bin/cmake" --version | head -1)"
        echo "ninja: $(ninja --version)"
        echo "gcc: $(gcc --version | head -1)"
        echo "omniverse-labs commit: $NANOUSD_COMMIT"
        echo "  tarball sha256: $NANOUSD_TARBALL_SHA256"
        echo "usd-core: $("$PREFIX/venv/bin/pip" show usd-core | awk '/^Version/{print $2}')"
        echo "numpy: $("$PREFIX/venv/bin/pip" show numpy | awk '/^Version/{print $2}')"
        echo "pillow: $("$PREFIX/venv/bin/pip" show pillow | awk '/^Version/{print $2}')"
        echo "mesa: $(dpkg-query -W -f='${Version}' libegl-mesa0 2>/dev/null || echo unknown)"
    } > "$JUDGE_DIR/VERSIONS.txt"
    log "wrote $JUDGE_DIR/VERSIONS.txt"
}

main() {
    mkdir -p "$PREFIX"/{src,build,bin}
    apt_install
    install_cmake
    check_cmake
    fetch_nanousd
    build_nanousd
    build_renderer
    build_drivers
    install_python
    record_versions
    log "setup done -> $PREFIX"
}

main "$@"
