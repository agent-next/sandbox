#!/usr/bin/env bash
# judge/grade.sh — grade a LoRA fine-tune artifact against every gate.
#
#   judge/grade.sh <artifact-dir-or-archive> [--seed N] [--json out.json]
#
# Thin wrapper: the gates live in _grade.py, run with the pinned venv
# installed by setup.sh. One JSON verdict to stdout; exit 0 only if every
# gate passes and the judge directory is unchanged by the run.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HOME/.venvs/gpu-lora-finetune"
PY="$VENV/bin/python"

[[ -x "$PY" ]] || { echo "[grade] ERROR: pinned venv missing — run judge/setup.sh first" >&2; exit 2; }
[[ $# -ge 1 ]] || { echo "Usage: $0 <artifact-dir-or-archive> [--seed N] [--json out.json]" >&2; exit 2; }

exec "$PY" "$SCRIPT_DIR/_grade.py" "$@"
