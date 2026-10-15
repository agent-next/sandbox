#!/usr/bin/env bash
# judge/setup.sh -- install pinned tools for the ovui-native-ui demo.
#
# Idempotent; installs into $HOME/tools/ovui-native-ui. The only system
# writes are apt packages (Vulkan loader + Mesa lavapipe + a C compiler).
#
# Installs: Mesa lavapipe (CPU Vulkan), ovui (pinned wheel, sha256-checked),
# Pillow + numpy (pinned wheels, sha256-checked), and two generated CUDA
# stub libraries that satisfy omni.ui's DT_NEEDED on libcuda.so.1 /
# libcudart.so.12 on a host with no CUDA. See SPEC.md "Why the CUDA stubs".
set -euo pipefail

TOOLS_DIR="${TOOLS_DIR:-$HOME/tools/ovui-native-ui}"
VENV="$TOOLS_DIR/venv"
STUB_DIR="$TOOLS_DIR/cuda-stub"
WHEEL_DIR="$TOOLS_DIR/wheels"

# -- pinned apt packages (Debian bookworm, amd64) --------------------------
# vulkan-tools is not needed to render; it provides `vulkaninfo`, whose
# device summary is the "== vulkan device ==" section of VERSIONS.txt.
APT_PACKAGES="mesa-vulkan-drivers libvulkan1 libgl1 gcc libc6-dev vulkan-tools"

# -- pinned pip wheels (Python 3.12, linux x86_64), sha256-checked ---------
OVUI_VERSION="0.3.0"
OVUI_WHEEL="ovui-0.3.0-cp312-cp312-manylinux_2_35_x86_64.whl"
OVUI_SHA256="f9d15732c41ae1817346ad856c0e67fae747de536710ed07203046ad33d6a116"
PILLOW_VERSION="12.3.0"
PILLOW_WHEEL="pillow-12.3.0-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl"
PILLOW_SHA256="78cb2c6865a35ab8ff8b75fd122f6033b92a62c82801110e48ddd6c936a45d91"
NUMPY_VERSION="2.5.4"
NUMPY_WHEEL="numpy-2.5.4-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl"
NUMPY_SHA256="fbde6962867ee75b48b0ee29b2b9372ec5d617799dbaf38e82dc0596f2f7738a"

# -- apt --------------------------------------------------------------------
need_apt=0
for p in $APT_PACKAGES; do
    dpkg -s "$p" >/dev/null 2>&1 || need_apt=1
done
if [ "$need_apt" = 1 ]; then
    # This image may ship empty apt lists; fetch them and prove they landed.
    if [ -z "$(ls /var/lib/apt/lists/*Packages* 2>/dev/null)" ]; then
        until sudo apt-get update -qq; do
            echo "apt-get update failed; retrying in 5 s" >&2
            sleep 5
        done
    fi
    [ -n "$(ls /var/lib/apt/lists/*Packages* 2>/dev/null)" ] \
        || { echo "ERROR: apt lists still empty after apt-get update" >&2; exit 1; }
    sudo apt-get install -y --no-install-recommends $APT_PACKAGES
fi

# lavapipe ICD must be registered (the CPU Vulkan device this demo renders on).
if ! ls /usr/share/vulkan/icd.d/lvp_icd.*.json >/dev/null 2>&1; then
    echo "ERROR: mesa lavapipe ICD not registered after install" >&2
    exit 1
fi

# -- pinned wheels ----------------------------------------------------------
if [ ! -x "$VENV/bin/python" ]; then
    python3 -m venv "$VENV"
fi

mkdir -p "$WHEEL_DIR"
verify() { echo "$2  $1" | sha256sum -c - >/dev/null 2>&1; }
if ! verify "$WHEEL_DIR/$OVUI_WHEEL" "$OVUI_SHA256" \
   || ! verify "$WHEEL_DIR/$PILLOW_WHEEL" "$PILLOW_SHA256" \
   || ! verify "$WHEEL_DIR/$NUMPY_WHEEL" "$NUMPY_SHA256"; then
    rm -rf "$WHEEL_DIR.dl" && mkdir -p "$WHEEL_DIR.dl"
    "$VENV/bin/pip" download --quiet --no-deps --only-binary :all: \
        --dest "$WHEEL_DIR.dl" \
        "ovui==$OVUI_VERSION" "pillow==$PILLOW_VERSION" "numpy==$NUMPY_VERSION"
    echo "$OVUI_SHA256  $WHEEL_DIR.dl/$OVUI_WHEEL" | sha256sum -c -
    echo "$PILLOW_SHA256  $WHEEL_DIR.dl/$PILLOW_WHEEL" | sha256sum -c -
    echo "$NUMPY_SHA256  $WHEEL_DIR.dl/$NUMPY_WHEEL" | sha256sum -c -
    mv "$WHEEL_DIR.dl"/*.whl "$WHEEL_DIR/" && rm -rf "$WHEEL_DIR.dl"
fi

"$VENV/bin/pip" install --quiet --no-index --find-links "$WHEEL_DIR" \
    "ovui==$OVUI_VERSION" "pillow==$PILLOW_VERSION" "numpy==$NUMPY_VERSION"

# -- generated CUDA stubs ---------------------------------------------------
# omni.ui's shared objects declare DT_NEEDED on libcuda.so.1 and
# libcudart.so.12, so on a CPU-only host a bare `import omni.ui` dies with
# "libcuda.so.1: cannot open shared object file". Both stubs are generated
# from the exact undefined-symbol list of the *installed* ovui shared
# objects, so they always match the pinned wheel. On the lavapipe path
# (OMNIUI_LAVAPIPE=1) ovui disables CUDA interop and never calls them.
SP="$VENV/lib/python3.12/site-packages/omni/ui"
STUB_STAMP="$STUB_DIR/.symbols.sha256"

if [ ! -f "$STUB_DIR/libcuda.so.1" ] || [ ! -f "$STUB_DIR/libcudart.so.12" ]; then
    mkdir -p "$STUB_DIR"
    # every undefined CUDA symbol across omni.ui's shared objects
    { for so in "$SP"/*.so "$SP"/*.so.*; do
          [ -e "$so" ] || continue
          nm -D --undefined-only "$so" 2>/dev/null
      done
    } | grep -oE '\b(cuda[A-Z][A-Za-z0-9_]+|cu[A-Z][A-Za-z0-9_]+)' \
      | grep -v '^cudart$' | sort -u > "$STUB_DIR/symbols.txt"
    [ -s "$STUB_DIR/symbols.txt" ] \
        || { echo "ERROR: no CUDA symbols found in $SP; is ovui installed?" >&2; exit 1; }

    # generate + compile both stubs (python3 is stdlib-only here)
    "$VENV/bin/python" - "$STUB_DIR" <<'PY'
import sys
stub = sys.argv[1]
syms = [l.strip() for l in open(f"{stub}/symbols.txt") if l.strip()]
cudart = [s for s in syms if s.startswith("cuda")]
driver = [s for s in syms if s.startswith("cu") and not s.startswith("cuda")]
# queries/allocs report "no CUDA device" (error 100); teardown calls succeed
OK_RT = {"cudaFree", "cudaFreeMipmappedArray", "cudaDestroyExternalMemory",
         "cudaDestroyExternalSemaphore", "cudaEventDestroy",
         "cudaEventSynchronize", "cudaStreamSynchronize",
         "cudaGraphicsUnmapResources", "cudaGraphicsUnregisterResource"}
OK_DRV = {"cuCtxDestroy_v2", "cuDestroyExternalMemory"}
HDR = ("/* Minimal {lib} stub for CPU-only hosts, generated by judge/setup.sh.\n"
       " * One function per undefined CUDA symbol in the installed omni.ui\n"
       " * shared objects. Queries/allocs report 'no CUDA device' (error 100);\n"
       " * teardown succeeds. On the lavapipe path ovui disables CUDA interop\n"
       " * and never calls these. */\n")
with open(f"{stub}/cudartstub.c", "w") as f:
    f.write(HDR.format(lib="libcudart.so.12"))
    f.write("typedef struct { int x, y, z, w; } cudaChannelFormatDesc;\n"
            "cudaChannelFormatDesc cudaCreateChannelDesc(int x,int y,int z,int w)"
            "{cudaChannelFormatDesc d={x,y,z,w};return d;}\n"
            'const char *cudaGetErrorString(int e){(void)e;return "no CUDA device";}\n')
    for n in cudart:
        if n in ("cudaCreateChannelDesc", "cudaGetErrorString"):
            continue
        f.write(f"int {n}(void) {{ return {'0' if n in OK_RT else '100'}; }}\n")
with open(f"{stub}/cudart.map", "w") as f:
    f.write("libcudart.so.12 {\n  global:\n")
    for n in cudart:
        f.write(f"    {n};\n")
    f.write("  local: *;\n};\n")
with open(f"{stub}/cudastub.c", "w") as f:
    f.write(HDR.format(lib="libcuda.so.1"))
    for n in driver:
        f.write(f"int {n}(void) {{ return {'0' if n in OK_DRV else '100'}; }}\n")
print(f"generated stubs: {len(cudart)} cudart + {len(driver)} driver symbols")
PY

    cc -shared -fPIC -O2 -o "$STUB_DIR/libcudart.so.12" "$STUB_DIR/cudartstub.c" \
        -Wl,-soname,libcudart.so.12 -Wl,--version-script="$STUB_DIR/cudart.map"
    cc -shared -fPIC -O2 -o "$STUB_DIR/libcuda.so.1" "$STUB_DIR/cudastub.c" \
        -Wl,-soname,libcuda.so.1
    ln -sf libcuda.so.1 "$STUB_DIR/libcuda.so"
fi
sha256sum "$STUB_DIR/symbols.txt" | awk '{print $1}' > "$STUB_STAMP"

# -- smoke test: does omni.ui import and can it see a CPU Vulkan device? -----
LD_LIBRARY_PATH="$STUB_DIR:${LD_LIBRARY_PATH:-}" "$VENV/bin/python" -I -c "
import omni.ui as ui
print('omni.ui import OK')" \
    || { echo "ERROR: omni.ui did not import with the CUDA stubs" >&2; exit 1; }

# -- record exact versions --------------------------------------------------
# Written to $TOOLS_DIR/VERSIONS.txt; judge/VERSIONS.txt in the repo is a
# copy of one such run with the $TOOLS_DIR prefix replaced by <tools>.
{
    echo "== apt =="
    dpkg -l $APT_PACKAGES 2>/dev/null | awk '/^ii/{print $2, $3}'
    echo "== compiler =="
    cc --version | head -1
    echo "== pip =="
    "$VENV/bin/pip" list --format=freeze | sort
    echo "== vulkan device =="
    (vulkaninfo --summary 2>/dev/null | grep -E "deviceName|driverName|deviceType") || true
    echo "== cuda stub symbols =="
    wc -l < "$STUB_DIR/symbols.txt"
    sha256sum "$STUB_DIR/libcuda.so.1" "$STUB_DIR/libcudart.so.12"
} > "$TOOLS_DIR/VERSIONS.txt"

echo "setup OK: $TOOLS_DIR"
