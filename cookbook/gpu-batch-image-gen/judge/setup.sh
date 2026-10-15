#!/bin/sh
# Install the pinned judge toolchain into $HOME/.venvs/gpu-image-gen, then
# fetch the pinned OpenAI CLIP ViT-B-32 checkpoint.
#
# Everything is sha256-checked: pip installs through --require-hashes from
# judge/requirements.lock (torch 2.14.0+cpu, torchvision 0.29.0+cpu,
# open_clip_torch 3.3.0 and the full transitive closure), and the CLIP
# checkpoint is downloaded from a pinned URL and verified against its sha256.
# Idempotent: an existing venv that already provides the pinned versions and
# an existing verified checkpoint are left untouched.

set -eu

VENV="$HOME/.venvs/gpu-image-gen"
CACHE="$HOME/.gpu-image-gen-weights"
HERE=$(cd "$(dirname "$0")" && pwd)

case "$(uname -s):$(uname -m)" in
    Linux:x86_64) ;;
    *) echo "setup.sh: unsupported platform $(uname -s) $(uname -m) \
(supported: x86-64 Linux, CPython 3.10-3.13)" >&2; exit 2 ;;
esac

case "$(python3 -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')" in
    3.10|3.11|3.12|3.13) ;;
    *) echo "setup.sh: unsupported Python \
$(python3 -c 'import sys; print(sys.version.split()[0])') (supported: 3.10-3.13)" >&2
       exit 2 ;;
esac

if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" - <<EOF
import importlib.util as u
def have(name, ver):
    m = u.find_spec(name)
    return m is not None and getattr(__import__(name), "__version__", "") == ver
import sys
sys.exit(0 if have("torch", "2.14.0+cpu") and have("open_clip", "3.3.0")
           and have("PIL", "11.3.0") else 1)
EOF
then
    echo "setup.sh: venv already provides the pinned toolchain"
else
    echo "setup.sh: creating venv at $VENV"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --quiet --upgrade pip==25.0.1
    "$VENV/bin/pip" install --require-hashes -r "$HERE/requirements.lock"
fi

# OpenAI CLIP ViT-B-32 open_clip checkpoint (MIT licence), pinned to repo
# revision a6f597a30f7b82c51704746581f9a4e41421e878 so the judge oracle never
# moves. The sha256 is of the served bytes.
CLIP_URL="https://huggingface.co/timm/vit_base_patch32_clip_224.openai/resolve/a6f597a30f7b82c51704746581f9a4e41421e878/open_clip_model.safetensors"
CLIP_SHA256="e6d1bd7789aa45192b3bf90570a789b478bae1b74ebcce7eddd908e83a2b7c31"
mkdir -p "$CACHE"
if [ -f "$CACHE/open_clip_model.safetensors" ] \
   && [ "$(sha256sum "$CACHE/open_clip_model.safetensors" | cut -d' ' -f1)" = "$CLIP_SHA256" ]; then
    echo "setup.sh: CLIP checkpoint already present and verified"
else
    echo "setup.sh: downloading pinned CLIP ViT-B-32 checkpoint (578 MiB)"
    curl -sSL --retry 3 -o "$CACHE/open_clip_model.safetensors.tmp" "$CLIP_URL"
    got=$(sha256sum "$CACHE/open_clip_model.safetensors.tmp" | cut -d' ' -f1)
    if [ "$got" != "$CLIP_SHA256" ]; then
        rm -f "$CACHE/open_clip_model.safetensors.tmp"
        echo "setup.sh: CLIP checkpoint sha256 mismatch (got $got)" >&2
        exit 1
    fi
    mv "$CACHE/open_clip_model.safetensors.tmp" "$CACHE/open_clip_model.safetensors"
fi

# Record what actually installed, for RECEIPT.md.
"$VENV/bin/pip" list --format=freeze > "$HERE/VERSIONS.txt"
printf '## judge venv (python %s)\n' \
    "$("$VENV/bin/python" -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')" \
    > "$HERE/VERSIONS.brief"
printf '## CLIP checkpoint sha256 %s\n' "$CLIP_SHA256" >> "$HERE/VERSIONS.brief"
cat "$HERE/VERSIONS.brief" "$HERE/VERSIONS.txt" > "$HERE/VERSIONS.tmp"
mv "$HERE/VERSIONS.tmp" "$HERE/VERSIONS.txt"
rm -f "$HERE/VERSIONS.brief"

echo "setup.sh: ok"
