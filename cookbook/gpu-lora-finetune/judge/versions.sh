#!/usr/bin/env bash
# judge/versions.sh — print what the judge stack actually reports.
# Used by setup.sh to write VERSIONS.txt (DEMO-STANDARD.md "Pinned everything").

set -euo pipefail

VENV="${VENV:-$HOME/.venvs/gpu-lora-finetune}"
PY="$VENV/bin/python"
[[ -x "$PY" ]] || { echo "versions.sh: no venv at $VENV (run setup.sh)" >&2; exit 2; }

echo "### interpreter"
echo "python=$("$PY" -c 'import platform;print(platform.python_version())')"
echo "platform=$("$PY" -c 'import platform;print(platform.platform())')"

echo
echo "### judge venv (\$HOME/.venvs/gpu-lora-finetune)"
"$PY" - <<'PY'
import importlib.metadata as im
names = ["torch", "transformers", "tokenizers", "peft", "safetensors",
         "accelerate", "numpy", "huggingface-hub"]
for n in names:
    try:
        print(f"{n}=={im.version(n)}")
    except im.PackageNotFoundError:
        print(f"{n}=MISSING")
PY

echo
echo "### base model (pinned by judge/pins.txt)"
MODEL_DIR="${GPU_LORA_MODEL_DIR:-$HOME/models/qwen3-0.6b}"
if [[ -f "$MODEL_DIR/.complete" ]]; then
    ( cd "$MODEL_DIR" && sha256sum config.json model.safetensors tokenizer.json )
else
    echo "model not installed at $MODEL_DIR"
fi
