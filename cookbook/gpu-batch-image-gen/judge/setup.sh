#!/bin/sh
# Install the pinned judge toolchain into $HOME/.venvs/gpu-image-gen, then
# fetch the pinned OpenAI CLIP ViT-B-32 checkpoint.
#
# Everything is sha256-checked: pip installs through --require-hashes from
# judge/requirements.lock (torch 2.14.0+cpu, torchvision 0.29.0+cpu,
# open_clip_torch 3.3.0 and the full transitive closure), and the CLIP
# checkpoint is downloaded from a pinned URL and verified against its sha256.
#
# Stages (idempotent, individually addressable so a driver can resume after
# an interrupted sandbox lifetime; each checks its own completion first):
#
#   judge/setup.sh                  # everything, in order (humans)
#   judge/setup.sh --stage=prefill  # fill $HOME pip wheel cache from the lock
#   judge/setup.sh --stage=clip     # download + verify the CLIP checkpoint
#   judge/setup.sh --stage=venv     # staging venv -> pinned install -> freeze
#   judge/setup.sh --stage=versions # rewrite judge/VERSIONS.txt from the venv
#
# The venv is built in a .staging directory and moved into place only after
# a complete pinned install plus an import smoke test, so an interrupted run
# can never leave a half-installed judge behind.

set -eu

VENV="$HOME/.venvs/gpu-image-gen"
STAGING="$VENV.staging"
CACHE="$HOME/.gpu-image-gen-weights"
PIP_CACHE="$CACHE/pip-cache"
CLIP_FILE="ViT-B-32.pt"
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

# OpenAI CLIP ViT-B-32 (354 MiB .pt; MIT licence — the OpenAI/public CLIP
# weights, different file from the 578 MiB timm HF re-upload). The judge
# never imports this file: open_clip reads the original OpenAI state dict
# straight off it, so the judge oracle is byte-for-byte what OpenAI shipped.
# No Hugging Face access needed from the judge sandbox (no GPU either way).
CLIP_URL="https://openaipublic.azureedge.net/clip/models/40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af/ViT-B-32.pt"
CLIP_SHA256="40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af"

stage_prefill() {
    mkdir -p "$PIP_CACHE"
    echo "setup.sh: prefilling pip wheel cache from requirements.lock"
    python3 -m pip download --quiet --require-hashes \
        --cache-dir "$PIP_CACHE" -r "$HERE/requirements.lock" -d "$PIP_CACHE"
}

stage_clip() {
    if [ -f "$CACHE/$CLIP_FILE" ] \
       && [ "$(sha256sum "$CACHE/$CLIP_FILE" | cut -d' ' -f1)" = "$CLIP_SHA256" ]; then
        echo "setup.sh: CLIP checkpoint already present and verified"
        return 0
    fi
    echo "setup.sh: downloading pinned CLIP ViT-B-32 checkpoint (354 MiB)"
    mkdir -p "$CACHE"
    curl -sS -L -C - --retry 3 --retry-all-errors \
        -o "$CACHE/$CLIP_FILE.part" "$CLIP_URL"
    got=$(sha256sum "$CACHE/$CLIP_FILE.part" | cut -d' ' -f1)
    if [ "$got" != "$CLIP_SHA256" ]; then
        rm -f "$CACHE/$CLIP_FILE.part"
        echo "setup.sh: CLIP checkpoint sha256 mismatch (got $got)" >&2
        exit 1
    fi
    mv "$CACHE/$CLIP_FILE.part" "$CACHE/$CLIP_FILE"
}

venv_complete() {
    [ -x "$1/bin/python" ] && "$1/bin/python" - <<'PYEOF'
import importlib.util as u
def have(name, ver):
    m = u.find_spec(name)
    return m is not None and getattr(__import__(name), "__version__", "") == ver
import sys
sys.exit(0 if have("torch", "2.14.0+cpu") and have("open_clip", "3.3.0")
           and have("PIL", "11.3.0") else 1)
PYEOF
}

stage_venv() {
    if venv_complete "$VENV"; then
        echo "setup.sh: venv already provides the pinned toolchain"
        return 0
    fi
    rm -rf "$STAGING"
    echo "setup.sh: creating venv at $VENV (staging at $STAGING)"
    python3 -m venv "$STAGING"
    "$STAGING/bin/pip" install --quiet --upgrade pip==25.0.1
    "$STAGING/bin/pip" install --quiet --require-hashes \
        --cache-dir "$PIP_CACHE" -r "$HERE/requirements.lock"
    # Import smoke test before the freeze: a venv that cannot even import
    # its pinned stack is a failed install, not a judge.
    "$STAGING/bin/python" -c 'import torch, PIL, open_clip, numpy, torchvision'
    rm -rf "$VENV"
    mv "$STAGING" "$VENV"
}

stage_versions() {
    if ! venv_complete "$VENV"; then
        echo "setup.sh: refusing to record versions: venv incomplete" >&2
        exit 1
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
}

case "${1:---all}" in
    --stage=prefill)  stage_prefill ;;
    --stage=clip)     stage_clip ;;
    --stage=venv)     stage_venv ;;
    --stage=versions) stage_versions ;;
    --all)
        stage_prefill
        stage_venv
        stage_clip
        stage_versions
        ;;
    *)
        echo "setup.sh: unknown stage '$1' (use --stage=prefill|clip|venv|versions)" >&2
        exit 2
        ;;
esac

echo "setup.sh: ok"
