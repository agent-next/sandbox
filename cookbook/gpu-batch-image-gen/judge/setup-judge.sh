#!/bin/sh
# Staged, resumable install of the pinned judge toolchain. Runs INSIDE the
# demo's sbx sandbox (no GPU there): stage venv -> stage CLIP checkpoint ->
# freeze both in one move. If the sandbox dies mid-step the next run picks up
# at the first stage whose marker file is missing.
#
# judge/setup-judge.sh <sandbox_id> <ref>   (one stage per call)
set -eu

SID="$1"
REF="${2:-main}"
DEMO="cookbook/gpu-batch-image-gen"
VENV="$HOME/.venvs/gpu-image-gen"
CACHE="$HOME/.gpu-image-gen-weights"
CLIP_URL="https://huggingface.co/timm/vit_base_patch32_clip_224.openai/resolve/a6f597a30f7b82c51704746581f9a4e41421e878/open_clip_model.safetensors"
CLIP_SHA256="e6d1bd7789aa45192b3bf90570a789b478bae1b74ebcce7eddd908e83a2b7c31"
DONE_MARKER="$HOME/.setup-judge-done"

[ -n "${SID:-}" ] || { echo "usage: setup-judge.sh <sandbox_id> [ref]" >&2; exit 2; }
[ -f "$DONE_MARKER" ] && { echo "setup-judge: already complete"; exit 0; }

stage_venv() {
    if [ -x "$VENV.staging/bin/python" ] && "$VENV.staging/bin/python" - <<'PYEOF'
import importlib.util as u
def have(name, ver):
    m = u.find_spec(name)
    return m is not None and getattr(__import__(name), "__version__", "") == ver
import sys
sys.exit(0 if have("torch", "2.14.0+cpu") and have("open_clip", "3.3.0")
           and have("PIL", "11.3.0") else 1)
PYEOF
    then
        return 0
    fi
    echo "setup-judge: creating staging venv (pinned toolchain download)"
    python3 -m venv "$VENV.staging"
    "$VENV.staging/bin/pip" install --quiet --upgrade pip==25.0.1
    "$VENV.staging/bin/pip" install --require-hashes \
        -r "$DEMO/judge/requirements.lock"
}

stage_clip() {
    if [ -f "$CACHE/open_clip_model.safetensors" ] \
       && [ "$(sha256sum "$CACHE/open_clip_model.safetensors" | cut -d' ' -f1)" = "$CLIP_SHA256" ]; then
        return 0
    fi
    echo "setup-judge: downloading pinned CLIP ViT-B-32 checkpoint (578 MiB)"
    mkdir -p "$CACHE"
    curl -sSL --retry 3 -o "$CACHE/open_clip_model.safetensors.tmp" "$CLIP_URL"
    got=$(sha256sum "$CACHE/open_clip_model.safetensors.tmp" | cut -d' ' -f1)
    if [ "$got" != "$CLIP_SHA256" ]; then
        rm -f "$CACHE/open_clip_model.safetensors.tmp"
        echo "setup-judge: CLIP checkpoint sha256 mismatch (got $got)" >&2
        exit 1
    fi
    mv "$CACHE/open_clip_model.safetensors.tmp" "$CACHE/open_clip_model.safetensors"
}

if [ ! -d "$VENV" ]; then
    stage_venv
fi

if [ ! -f "$CACHE/open_clip_model.safetensors" ]; then
    stage_clip
fi

# Both stages done: freeze in one move. VERSIONS.txt is what setup.sh wrote
# into the repo clone before this script was started, so the recorded
# contents match what actually installed.
[ -f "$DEMO/judge/VERSIONS.txt" ] || { echo "setup-judge: VERSIONS.txt missing from clone" >&2; exit 1; }
mv "$VENV.staging" "$VENV" 2>/dev/null || true
mv "$DEMO/judge/VERSIONS.txt" "$CACHE/judge-VERSIONS.txt"
: > "$DONE_MARKER"
rm -rf "$VENV.staging" "$CACHE/judge-VERSIONS.txt"
echo "setup-judge: ok"
