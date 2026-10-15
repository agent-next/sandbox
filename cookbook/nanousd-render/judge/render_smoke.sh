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

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

python3 - "$tmp/cam.bin" <<'PY'
import struct, sys
view = [1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,-5,1]   # column-major, eye at z=+5
proj = [0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,0]
f = 1.0 / __import__("math").tan(__import__("math").radians(45.0) / 2)
aspect = 640 / 480
proj[0] = f / aspect; proj[5] = f
proj[10] = -(100 + 0.1) / (100 - 0.1); proj[11] = -1.0
proj[14] = -(2 * 100 * 0.1) / (100 - 0.1)
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
