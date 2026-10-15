#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 agent-next contributors
# SPDX-License-Identifier: Apache-2.0
#
# grade.sh <artifact.usda> [--seed N] [--json out.json]
#
# Grades one USDA artifact against every gate in ../SPEC.md. Prints one JSON
# verdict on stdout; exits 0 only if every gate passed. The Python judge
# (judge/judge.py) is the engine; this wrapper only resolves the pinned
# toolchain into the environment and forwards the arguments unchanged.
#
# Usage:
#   bash judge/grade.sh examples/good/scene.usda --json /tmp/verdict.json
set -euo pipefail

DEMO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JUDGE_DIR="$DEMO_DIR/judge"
PREFIX="${NANOUSD_RENDER_PREFIX:-$HOME/.nanousd-render}"

if [ $# -lt 1 ]; then
    printf 'usage: grade.sh <artifact.usda> [--seed N] [--json out.json]\n' >&2
    exit 2
fi

PY="$PREFIX/venv/bin/python"
if [ ! -x "$PY" ]; then
    printf '[grade] ERROR: no pinned interpreter at %s -- run judge/setup.sh first\n' "$PY" >&2
    exit 1
fi

export NANOUSD_RENDER_PREFIX="$PREFIX"
# The renderer needs software GLES/EGL; judge.py sets these too, but export
# them here as well so any child process sees the llvmpipe configuration.
export LIBGL_ALWAYS_SOFTWARE=1
export GALLIUM_DRIVER=llvmpipe
export LD_LIBRARY_PATH="$PREFIX/build/nanousd-opengl-renderer:$PREFIX/build/nanousd-opengl-renderer/Release:$PREFIX/build/nanousd/Release:${LD_LIBRARY_PATH:-}"

cd "$DEMO_DIR"
exec "$PY" "$JUDGE_DIR/judge.py" "$@"
