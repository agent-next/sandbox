#!/usr/bin/env bash
# Install the pinned toolchain for the video-transcode-pipeline judge,
# idempotently, into $HOME/.vtp-tools. Every download is sha256-checked;
# a mismatch or an install failure exits non-zero and installs nothing.
#
#   ffmpeg 5.1.9 + its libraries   Debian bookworm .deb, sha256-pinned
#   espeak-ng 1.51                 Debian bookworm .deb, sha256-pinned
#   whisper.cpp                    built from git SHA 0c7be696..., tarball pinned
#   ggml-tiny.en model             pinned Hugging Face release asset
#   cmake 4.4.4                    PyPI wheel, sha256-pinned
#
# The judge itself is Python 3.10+ standard library only.
#
# Usage: bash judge/setup.sh
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${HOME}/.vtp-tools"
CACHE="${HOME}/.cache/vtp"
BIN="${PREFIX}/bin"

FFMPEG_VERSION="5.1.9-0+deb12u1"
ESPEAK_VERSION="1.51+dfsg-10+deb12u2"
WHISPER_SHA="0c7be696371069e0baa2515ed7aa08d5a5473aa6"
CMAKE_VERSION="4.4.4"
MODEL_FILE="ggml-tiny.en.bin"

DEB_BASE="https://deb.debian.org/debian/pool/main"
FFMPEG_BASE="${DEB_BASE}/f/ffmpeg"
ESPEAK_BASE="${DEB_BASE}/e/espeak-ng"
PCAUDIO_BASE="${DEB_BASE}/p/pcaudiolib"
SONIC_BASE="${DEB_BASE}/s/sonic"
WHISPER_URL="https://codeload.github.com/ggml-org/whisper.cpp/tar.gz/${WHISPER_SHA}"
MODEL_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/${MODEL_FILE}"
FONT_DEB_BASE="${DEB_BASE}/f/fonts-dejavu"
FONT_DEB="fonts-dejavu-core_2.37-9_all.deb"
FONT_SHA="b86ec13576ccf766f7066e783cf06ebd7af955d22276ccceac41b7ffefdcf8eb"

log() { printf 'setup: %s\n' "$*"; }
die() { printf 'setup: %s\n' "$*" >&2; exit 1; }

mkdir -p "$PREFIX" "$BIN" "$CACHE"

# --------------------------------------------------------------------------
# 1. ffmpeg + espeak-ng, from sha256-pinned Debian bookworm packages.
#    Downloaded first, verified as a batch, and only then installed, so a
#    bad download cannot leave a half-upgraded ffmpeg behind.
# --------------------------------------------------------------------------
# package:sha256, one per line. Computed from the files the pinned URLs
# serve; see RECEIPT.md for the sha256sum run that produced them.
# "<url> <sha256>", one per line; the sha256s were computed from the files
# these pinned URLs serve (see RECEIPT.md).
DEBS="
${FFMPEG_BASE}/ffmpeg_${FFMPEG_VERSION}_amd64.deb 2ba8ead87657c123ce6de2de5ecdbc1fb4ead9a4b317b85b8ec41e16c890fe01
${FFMPEG_BASE}/libavcodec59_${FFMPEG_VERSION}_amd64.deb a1c6cfeefe7437ad3ff999d3dad39edb9cfd4d2068a944243fa4f313470b59b1
${FFMPEG_BASE}/libavdevice59_${FFMPEG_VERSION}_amd64.deb d14e0e21ee3b18be7324db7ab1a98e42acdca61095cad8df4cbda96c514d0705
${FFMPEG_BASE}/libavfilter8_${FFMPEG_VERSION}_amd64.deb 9df19ac34117740af851af569c3df05c16e20a319cedd832eafb9abde950c384
${FFMPEG_BASE}/libavformat59_${FFMPEG_VERSION}_amd64.deb 35216a7786f2bde3c9c00ffa0574ed27c63cb231726aa03ae3664a36946ef01c
${FFMPEG_BASE}/libavutil57_${FFMPEG_VERSION}_amd64.deb 3e2c42d9e7235c96cb0329dbe3c13377faaa5aba81ac2d6f3cf54fcd978c9a5f
${FFMPEG_BASE}/libpostproc56_${FFMPEG_VERSION}_amd64.deb c6ea1be8d11ee56ae2c9ae749edc2f38a3baaa949f882affdb859e1f69e6a168
${FFMPEG_BASE}/libswresample4_${FFMPEG_VERSION}_amd64.deb 255406cbb7589751bc5b67efdbc21be01130b9551f5eff2dfe6db2f3e4888a6d
${FFMPEG_BASE}/libswscale6_${FFMPEG_VERSION}_amd64.deb 9ed5ebab74fc46bfb72f1e4d4cd7769cc98ac67a3320551958f8a507747df450
${ESPEAK_BASE}/espeak-ng_${ESPEAK_VERSION}_amd64.deb a11396a690f85f55e6e6b2965505237ddf3dc95c51936aa61de936f1ccf8f4d0
${ESPEAK_BASE}/espeak-ng-data_${ESPEAK_VERSION}_amd64.deb 573f5661c6a5adcf949018baad158c4c773bf5579390ee5235a890f1cd694106
${ESPEAK_BASE}/libespeak-ng1_${ESPEAK_VERSION}_amd64.deb 2b127a95b50d92cbd7a615968d2ac1566e1cbc87e27bcda0c2894afb2407c6d2
${PCAUDIO_BASE}/libpcaudio0_1.2-2_amd64.deb 5309759e4d129c7d9a601240cc6e62820ecfa86a1a98e207992ffa6a572dbcd2
${SONIC_BASE}/libsonic0_0.2.0-12_amd64.deb 9d60de6918ace0b10e3e4e95421befd08aaf03b5b2a3d71ceb799e0cf259916f
"

installed_version() { dpkg-query -W -f='${Version}' "$1" 2>/dev/null || true; }

need_debs=0
[ "$(installed_version ffmpeg)" = "7:${FFMPEG_VERSION}" ] || need_debs=1
# A base image that already ships a different ffmpeg build: install ours over
# it rather than judging with whatever happens to be there.
[ "$(installed_version espeak-ng)" = "$ESPEAK_VERSION" ] || need_debs=1

if [ "$need_debs" -eq 0 ]; then
    log "ffmpeg $FFMPEG_VERSION and espeak-ng $ESPEAK_VERSION already installed"
else
    log "downloading and verifying the pinned Debian packages"
    mkdir -p "$CACHE/debs"
    list="$CACHE/debs.list"
    : > "$list"
    while read -r url sha; do
        [ -n "$url" ] || continue
        file="$CACHE/debs/$(basename "$url")"
        if [ ! -s "$file" ]; then
            curl -fsSL --retry 5 --retry-delay 3 --retry-all-errors -o "$file.part" "$url"
            mv "$file.part" "$file"
        fi
        echo "$sha  $file" >> "$list"
    done <<< "$DEBS"

    if ! sha256sum -c "$list" > "$CACHE/debs.verify" 2>&1; then
        cat "$CACHE/debs.verify" >&2
        # Remove anything that failed verification so a re-run re-downloads it.
        while read -r sha file; do
            echo "$sha  $file" | sha256sum -c - > /dev/null 2>&1 || rm -f "$file"
        done < "$list"
        die "sha256 mismatch on a pinned package; bad downloads removed, re-run setup.sh"
    fi
    log "all $(wc -l < "$list") packages verified"

    if [ "$(id -u)" -ne 0 ]; then SUDO=sudo; else SUDO=""; fi
    # shellcheck disable=SC2086
    $SUDO dpkg -i "$CACHE"/debs/*.deb || die "dpkg -i failed"
    # libavcodec pulls libvpx/libx264/libx265 ... which the base image has;
    # if a runtime library is genuinely missing, fix it up and fail loudly.
    $SUDO apt-get install -y -f -qq || die "apt-get install -f could not repair dependencies"
fi

ffmpeg_version() { ffmpeg -version | sed -n '1s/^ffmpeg version \([^ ]*\).*/\1/p'; }
have_ffmpeg="$(ffmpeg_version)"
[ "$have_ffmpeg" = "$FFMPEG_VERSION" ] || die "ffmpeg is $have_ffmpeg, expected $FFMPEG_VERSION"
have_espeak="$(espeak-ng --version | sed -n 's/.*: \([0-9][^ ]*\).*/\1/p')"
[ "$have_espeak" = "1.51" ] || die "espeak-ng is $have_espeak, expected 1.51"

# --------------------------------------------------------------------------
# 2. cmake, from a sha256-pinned PyPI wheel (Debian's cmake is far older
#    than whisper.cpp's CMakeLists wants).
# --------------------------------------------------------------------------
CMAKELINK="https://pypi.org/pypi/cmake/${CMAKE_VERSION}/json"
if [ ! -x "$BIN/cmake" ]; then
    log "installing cmake $CMAKE_VERSION from PyPI"
    python3 -m pip install --quiet --target "$PREFIX/py" \
        --only-binary=:all: "cmake==${CMAKE_VERSION}" \
        || die "could not install cmake ${CMAKE_VERSION}"
    found="$(find "$PREFIX/py" -type f -path '*/cmake/data/bin/cmake' | head -1)"
    [ -n "$found" ] || die "cmake wheel did not contain bin/cmake"
    ln -sf "$found" "$BIN/cmake"
fi
have_cmake="$("$BIN/cmake" --version | sed -n '1s/^cmake version //p')"
[ "$have_cmake" = "$CMAKE_VERSION" ] || die "cmake is $have_cmake, expected $CMAKE_VERSION"

# --------------------------------------------------------------------------
# 3. whisper.cpp at the pinned SHA, built with the pinned cmake.
# --------------------------------------------------------------------------
if [ ! -x "$BIN/whisper-cli" ]; then
    log "building whisper.cpp at ${WHISPER_SHA}"
    tarball="$CACHE/whisper.cpp-${WHISPER_SHA}.tar.gz"
    if [ ! -s "$tarball" ]; then
        curl -fsSL --retry 5 --retry-delay 3 --retry-all-errors -o "$tarball.part" "$WHISPER_URL"
        mv "$tarball.part" "$tarball"
    fi
    echo "20f6c4c2dd25225326d284b145998ffe48efabfee4e6c94c0437cb4f78dbab76  $tarball" \
        | sha256sum -c - || { rm -f "$tarball"; die "whisper.cpp tarball sha256 mismatch"; }
    rm -rf "$CACHE/whisper-src" "$CACHE/whisper-build"
    mkdir -p "$CACHE/whisper-src"
    tar -xzf "$tarball" -C "$CACHE/whisper-src" --strip-components=1
    "$BIN/cmake" -S "$CACHE/whisper-src" -B "$CACHE/whisper-build" \
        -DCMAKE_BUILD_TYPE=Release \
        -DBUILD_SHARED_LIBS=ON \
        -DWHISPER_BUILD_EXAMPLES=ON \
        -DWHISPER_BUILD_SERVER=OFF \
        -DWHISPER_BUILD_TESTS=OFF \
        -DGGML_NATIVE=OFF \
        > "$CACHE/whisper-cmake.log" 2>&1 \
        || { tail -40 "$CACHE/whisper-cmake.log" >&2; die "whisper.cpp cmake configure failed"; }
    "$BIN/cmake" --build "$CACHE/whisper-build" --target whisper-cli -j "$(nproc)" \
        > "$CACHE/whisper-build.log" 2>&1 \
        || { tail -40 "$CACHE/whisper-build.log" >&2; die "whisper.cpp build failed"; }
    # whisper-cli links the ggml/whisper shared objects next to it.
    cp "$CACHE/whisper-build"/bin/whisper-cli "$BIN/"
    cp "$CACHE/whisper-build"/bin/lib*.so* "$BIN/"
fi
# The pipeline looks for whisper-cli under $HOME/.vtp-tools; the shared
# objects live in $BIN, so hand it a launcher that sets LD_LIBRARY_PATH.
cat > "$PREFIX/whisper-cli" <<EOF
#!/bin/sh
# generated by judge/setup.sh: whisper-cli with its shared libraries
LD_LIBRARY_PATH="$BIN\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}" exec "$BIN/whisper-cli" "\$@"
EOF
chmod +x "$PREFIX/whisper-cli"

# --------------------------------------------------------------------------
# 4. the whisper model, pinned by sha256.
# --------------------------------------------------------------------------
if [ ! -s "$PREFIX/$MODEL_FILE" ]; then
    log "downloading $MODEL_FILE"
    curl -fsSL --retry 5 --retry-delay 3 --retry-all-errors \
        -o "$PREFIX/$MODEL_FILE.part" "$MODEL_URL"
    mv "$PREFIX/$MODEL_FILE.part" "$PREFIX/$MODEL_FILE"
fi
echo "921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f  $PREFIX/$MODEL_FILE" \
    | sha256sum -c - || { rm -f "$PREFIX/$MODEL_FILE"; die "model sha256 mismatch"; }

# --------------------------------------------------------------------------
# 5. the fixture font the counter OCR renders its templates from.
# --------------------------------------------------------------------------
FONT_PATH="/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
if [ ! -f "$FONT_PATH" ]; then
    log "installing fonts-dejavu-core"
    mkdir -p "$CACHE/fonts"
    file="$CACHE/fonts/$FONT_DEB"
    [ -s "$file" ] || curl -fsSL --retry 5 -o "$file" "${FONT_DEB_BASE}/${FONT_DEB}"
    echo "$FONT_SHA  $file" | sha256sum -c - \
        || { rm -f "$file"; die "fonts-dejavu-core sha256 mismatch"; }
    if [ "$(id -u)" -ne 0 ]; then SUDO=sudo; else SUDO=""; fi
    # shellcheck disable=SC2086
    $SUDO dpkg -i "$file" || die "could not install $FONT_DEB"
fi
[ -f "$FONT_PATH" ] || die "font $FONT_PATH still missing after install"

# --------------------------------------------------------------------------
# 6. Python version and the recorded tool versions.
# --------------------------------------------------------------------------
python3 - <<'EOF' || die "python3 >= 3.10 is required"
import sys
assert sys.version_info >= (3, 10), sys.version
EOF

log "tool versions"
ffmpeg -version | sed -n 1p
ffprobe -version | sed -n 1p
espeak-ng --version
"$PREFIX/whisper-cli" --help 2>&1 | sed -n 2p
python3 --version
{
    echo "# video-transcode-pipeline judge: versions installed by judge/setup.sh"
    echo "# ($(uname -sm))"
    echo "$(ffmpeg -version | sed -n 1p)"
    echo "$(ffprobe -version | sed -n 1p)"
    echo "$(espeak-ng --version)"
    echo "whisper.cpp ${WHISPER_SHA}"
    echo "cmake $("$BIN/cmake" --version | sed -n 1p)"
    echo "python3 $(python3 --version | awk '{print $2}')"
    echo "model ${MODEL_FILE} sha256 921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f"
} > "$JDIR/VERSIONS.txt"
log "wrote $JDIR/VERSIONS.txt"
log "done"
