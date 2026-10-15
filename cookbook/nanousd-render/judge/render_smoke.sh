#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 agent-next contributors
# SPDX-License-Identifier: Apache-2.0
#
# render_smoke.sh — setup.sh's post-build sanity check: the pinned
# nanousd-opengl-renderer must open a USD stage and render headlessly on
# CPU Mesa (EGL pbuffer on llvmpipe), no X, no GPU.
#
# Usage: render_smoke.sh <render_once binary> <scene.usda>
set -euo pipefail

BIN="${1:?usage: render_smoke.sh <render_once> <scene.usda>}"
SCENE="${2:?usage: render_smoke.sh <render_once> <scene.usda>}"

# Force software rendering even if another EGL driver is present.
export LIBGL_ALWAYS_SOFTWARE=1
export GALLIUM_DRIVER=llvmpipe
# The renderer libs live in the setup prefix (their baked-in RUNPATH
# already points there, but LD_LIBRARY_PATH also covers relocated trees).
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH:-}:$(dirname "$BIN")/../build/nanousd-opengl-renderer:$(dirname "$BIN")/../build/nanousd-opengl-renderer/Release:$(dirname "$BIN")/../build/nanousd/Release"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

python3 - "$tmp/cam.bin" <<'PY'
import struct, sys
# The pinned renderer consumes 4x4 COLUMN-VECTOR matrices (p' = M @ p)
# stored in ROW-MAJOR array order: flat[r*4 + c] = M[r][c], so the
# translation column is flat[12..14] and M[2][3] (view z at index 11)
# holds it here (eye z=5 -> -5). Transposing the layout (column-major
# array order) is what draws nothing, so the convention is load-bearing
# and must match judge.py's camera_math and render_once.c's header.
view = [1,0,0,0,  0,1,0,0,  0,0,1,0,  0,0,0,1]
view[11] = -5.0
f = 1.0 / __import__("math").tan(__import__("math").radians(45.0) / 2)
proj = [0] * 16
proj[0]  = f / (640 / 480)                  # M[0][0]
proj[5]  = f                               # M[1][1]
proj[10] = -(100 + 0.1) / (100 - 0.1)       # M[2][2]
proj[11] = -(2 * 100 * 0.1) / (100 - 0.1)   # M[2][3]
proj[14] = -1.0                            # M[3][2] -> w = -z
buf = struct.pack("<39f", *(view + proj + [0, 0, 5] + [640, 480, 0, 0]))
open(sys.argv[1], "wb").write(buf)
PY

"$BIN" "$SCENE" "$tmp/cam.bin" "$tmp/a.raw" "$tmp/b.raw" >/dev/null
size=$(stat -c %s "$tmp/a.raw")
[ "$size" -eq $((640 * 480 * 4)) ] || { echo "render_smoke: wrong RGBA size $size" >&2; exit 1; }
cmp -s "$tmp/a.raw" "$tmp/b.raw" || { echo "render_smoke: renders not byte-identical" >&2; exit 1; }

# A render that produced only one color did not really draw the scene.
python3 - "$tmp/a.raw" <<'PY'
import sys
data = open(sys.argv[1], "rb").read()
px = {data[i:i+4] for i in range(0, len(data), 4)}
if len(px) < 2:
    print("render_smoke: image is a single flat color", file=sys.stderr)
    sys.exit(1)
PY

echo "render_smoke: ok (llvmpipe headless render, deterministic)"
