#!/usr/bin/env bash
# judge/setup.sh -- install pinned tools for the ovui-native-ui demo.
# Idempotent; installs into $HOME/tools/ovui-native-ui (no system writes
# except apt, which runs only when the pinned package set is missing).
set -euo pipefail

TOOLS_DIR="${TOOLS_DIR:-$HOME/tools/ovui-native-ui}"
VENV="$TOOLS_DIR/venv"
STUB_DIR="$TOOLS_DIR/cuda-stub"

# -- pinned apt packages (Debian bookworm, amd64) --------------------------
# Pinned versions recorded in judge/VERSIONS.txt after install.
APT_PACKAGES="mesa-vulkan-drivers libvulkan1 libgl1"

# -- pinned pip wheels (Python 3.12, linux x86_64), sha256-checked ---------
OVUI_WHEEL="ovui-0.3.0-cp312-cp312-manylinux_2_35_x86_64.whl"
OVUI_SHA256="f9d15732c41ae1817346ad856c0e67fae747de536710ed07203046ad33d6a116"
PILLOW_WHEEL="pillow-12.3.0-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl"
PILLOW_SHA256="78cb2c6865a35ab8ff8b75fd122f6033b92a62c82801110e48ddd6c936a45d91"
NUMPY_WHEEL="numpy-2.5.4-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl"
NUMPY_SHA256="fbde6962867ee75b48b0ee29b2b9372ec5d617799dbaf38e82dc0596f2f7738a"
PYPI="https://pypi.org/simple"

need_apt=0
for p in $APT_PACKAGES; do
    dpkg -s "$p" >/dev/null 2>&1 || need_apt=1
done
if [ "$need_apt" = 1 ]; then
    # apt lists must actually be fetched; this image may ship empty lists.
    until sudo apt-get update -qq; do
        echo "apt-get update failed; retrying in 5 s" >&2
        sleep 5
    done
    sudo apt-get install -y --no-install-recommends $APT_PACKAGES
fi

# lavapipe ICD must be registered (CPU Vulkan device).
if ! ls /usr/share/vulkan/icd.d/lvp_icd.*.json >/dev/null 2>&1; then
    echo "ERROR: mesa lavapipe ICD not registered after install" >&2
    exit 1
fi

if [ ! -x "$VENV/bin/python" ]; then
    python3 -m venv "$VENV"
fi

# Download pinned wheels and verify sha256.
WHEEL_DIR="$TOOLS_DIR/wheels"
mkdir -p "$WHEEL_DIR"
if [ ! -f "$WHEEL_DIR/$OVUI_WHEEL" ] || ! echo "$OVUI_SHA256  $WHEEL_DIR/$OVUI_WHEEL" | sha256sum -c - >/dev/null 2>&1; then
    rm -rf "$WHEEL_DIR.dl" && mkdir -p "$WHEEL_DIR.dl"
    "$VENV/bin/pip" download --quiet --no-deps --only-binary :all: \
        --dest "$WHEEL_DIR.dl" \
        "ovui==0.3.0" "pillow==12.3.0" "numpy==2.5.4"
    echo "$OVUI_SHA256  $WHEEL_DIR.dl/$OVUI_WHEEL" | sha256sum -c -
    echo "$PILLOW_SHA256  $WHEEL_DIR.dl/$PILLOW_WHEEL" | sha256sum -c -
    echo "$NUMPY_SHA256  $WHEEL_DIR.dl/$NUMPY_WHEEL" | sha256sum -c -
    mv "$WHEEL_DIR.dl"/*.whl "$WHEEL_DIR/" && rm -rf "$WHEEL_DIR.dl"
fi

"$VENV/bin/pip" install --quiet --no-index --find-links "$WHEEL_DIR" \
    ovui==0.3.0 pillow==12.3.0 numpy==2.5.4
"$VENV/bin/python" -c "import ovui, PIL, numpy; print('ovui', ovui.__version__ if hasattr(ovui,'__version__') else '?')" 2>/dev/null || true

# libcuda.so.1 stub: ovui links the CUDA driver unconditionally, but only
# calls into it on the CUDA-Vulkan interop path. On a CPU-only host the
# stub exports the 8 symbols ovui needs and reports "no CUDA device", so
# ovui falls back to its Vulkan path on Mesa lavapipe.
if [ ! -f "$STUB_DIR/libcuda.so.1" ]; then
    mkdir -p "$STUB_DIR"
    cat > "$STUB_DIR/cudastub.c" <<'C_EOF'
/* Minimal libcuda.so.1 stub: reports "no CUDA device" so callers fall back
 * to a software/CPU path. Used on CPU-only hosts for ovui headless Vulkan
 * rendering via Mesa lavapipe. */
typedef int CUresult;
typedef int CUdevice;
typedef void *CUcontext;

#define CUDA_ERROR_NO_DEVICE 100

CUresult cuInit(unsigned int Flags) { (void)Flags; return CUDA_ERROR_NO_DEVICE; }
CUresult cuDeviceGet(CUdevice *device, int ordinal) { (void)device; (void)ordinal; return CUDA_ERROR_NO_DEVICE; }
CUresult cuCtxCreate_v2(CUcontext *pctx, unsigned int flags, CUdevice dev) { (void)pctx; (void)flags; (void)dev; return CUDA_ERROR_NO_DEVICE; }
CUresult cuCtxDestroy_v2(CUcontext ctx) { (void)ctx; return 0; }
CUresult cuImportExternalMemory(void *extMem_out, const void *memHandleDesc) { (void)extMem_out; (void)memHandleDesc; return CUDA_ERROR_NO_DEVICE; }
CUresult cuExternalMemoryGetMappedBuffer(void *devPtr, void *extMem, const void *bufferDesc) { (void)devPtr; (void)extMem; (void)bufferDesc; return CUDA_ERROR_NO_DEVICE; }
CUresult cuDestroyExternalMemory(void *extMem) { (void)extMem; return 0; }
CUresult cuMemcpyDtoH_v2(void *dstHost, unsigned long long srcDevice, unsigned long long ByteCount) { (void)dstHost; (void)srcDevice; (void)ByteCount; return CUDA_ERROR_NO_DEVICE; }
C_EOF
    cc -shared -fPIC -O2 -o "$STUB_DIR/libcuda.so.1" "$STUB_DIR/cudastub.c" -Wl,-soname,libcuda.so.1
    ln -sf libcuda.so.1 "$STUB_DIR/libcuda.so"
fi
sha256sum "$STUB_DIR/libcuda.so.1" > "$STUB_DIR/libcuda.so.1.sha256"

# Record exact versions.
{
    echo "== apt =="
    dpkg -l $APT_PACKAGES 2>/dev/null | awk '/^ii/{print $2, $3}'
    echo "== pip =="
    "$VENV/bin/pip" list --format=freeze | sort
    echo "== vulkan =="
    (vulkaninfo --summary 2>/dev/null | grep -E "deviceName|driverName" ) || true
} > "$TOOLS_DIR/VERSIONS.txt"

echo "setup OK: $TOOLS_DIR"
