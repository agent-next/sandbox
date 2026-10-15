#!/usr/bin/env bash
# go1-walk judge setup: the graded simulation runs on a remote 4 GiB
# VRAM-slice lease whose image is fixed (warp-lang 1.13.0, mujoco 3.8.1,
# mujoco-warp 3.8.1, torch 2.10.0+cu128, numpy 1.26.4 on an RTX 5090).
# _eval.py asserts those versions at grade time and fails on any drift,
# so there is nothing to install here. This script only validates the
# local side (python3 stdlib + an API key) and records VERSIONS.txt.
set -euo pipefail
cd "$(dirname "$0")"

python3 - <<'EOF'
import sys
assert sys.version_info >= (3, 10), "need python >= 3.10"
EOF

if [ -z "${SBX_API_KEY:-${E2B_API_KEY:-}}" ]; then
    echo "setup.sh: export SBX_API_KEY (or E2B_API_KEY) first" >&2
    exit 1
fi

{
    echo "python3 $(python3 --version 2>&1 | awk '{print $2}')"
    echo "lease stack (asserted by _eval.py at grade time):"
    echo "  warp 1.13.0"
    echo "  mujoco 3.8.1"
    echo "  mujoco_warp 3.8.1"
    echo "  torch 2.10.0+cu128"
    echo "  numpy 1.26.4"
    echo "  GPU: RTX 5090 slice, 4 GiB VRAM"
} > VERSIONS.txt

echo "setup.sh: ok (judge runs on the GPU lease; see VERSIONS.txt)"
