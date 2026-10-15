#!/usr/bin/env bash
# go1-walk judge setup.
#
# Grading runs on a remote 4 GiB VRAM-slice lease whose image is fixed
# (warp-lang 1.13.0, mujoco 3.8.1, mujoco-warp 3.8.1, torch 2.10.0+cu128,
# numpy 1.26.4, Python 3.13 on an RTX 5090); judge/_eval.py asserts those
# versions at grade time and fails on any drift, so there is nothing to
# install on the lease.
#
# Locally the only dependency is numpy, used by judge/mutants.py to
# re-pack policy.npz weight files into known-bad mutants. It is installed
# sha256-checked (pip --require-hashes, judge/requirements.lock) into a
# private venv at $HOME/.venvs/go1-walk. Idempotent: an existing venv with
# the pinned numpy is left untouched.
set -euo pipefail
cd "$(dirname "$0")"

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

if [ -z "${SBX_API_KEY:-${E2B_API_KEY:-}}" ]; then
    echo "setup.sh: export SBX_API_KEY (or E2B_API_KEY) first" >&2
    exit 1
fi

VENV="$HOME/.venvs/go1-walk"
if [ -x "$VENV/bin/python" ] && "$VENV/bin/python" -c \
    'import numpy; assert numpy.__version__ == "2.2.6"' 2>/dev/null; then
    echo "setup.sh: venv already provides numpy 2.2.6"
else
    echo 'setup.sh: creating $HOME/.venvs/go1-walk'
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --quiet --require-hashes -r requirements.lock
fi

{
    echo "# local side ($(date -u +%Y-%m-%d))"
    echo "python3 $(python3 --version 2>&1 | awk '{print $2}')"
    echo 'venv $HOME/.venvs/go1-walk:'
    "$VENV/bin/pip" list --format=freeze
    echo "lease stack (asserted by _eval.py at grade time):"
    echo "  warp-lang 1.13.0"
    echo "  mujoco 3.8.1"
    echo "  mujoco-warp 3.8.1"
    echo "  torch 2.10.0+cu128"
    echo "  numpy 1.26.4"
    echo "  GPU: RTX 5090 slice, 4 GiB VRAM"
} > VERSIONS.txt

echo 'setup.sh: rc=0 (pinned local NumPy; lease stack asserted before training and grading)'
