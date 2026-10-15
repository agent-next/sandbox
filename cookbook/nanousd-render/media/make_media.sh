#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 agent-next contributors
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

cd "$(dirname "$0")/.."
DEMO_DIR="$(pwd)"
JUDGE_DIR="$DEMO_DIR/judge"
PREFIX="${NANOUSD_RENDER_PREFIX:-$HOME/.nanousd-render}"
PY="$PREFIX/venv/bin/python"
MEDIA_DIR="$DEMO_DIR/media"
BUILD_DIR="$MEDIA_DIR/build"
MASTER_DIR="$MEDIA_DIR/master"

if [ ! -x "$PY" ]; then
    echo "[make_media] ERROR: run judge/setup.sh first (missing $PY)" >&2
    exit 1
fi

export NANOUSD_RENDER_PREFIX="$PREFIX"
export LIBGL_ALWAYS_SOFTWARE=1
export GALLIUM_DRIVER=llvmpipe
export LD_LIBRARY_PATH="$PREFIX/build/nanousd-opengl-renderer:$PREFIX/build/nanousd-opengl-renderer/Release:$PREFIX/build/nanousd/Release:${LD_LIBRARY_PATH:-}"

rm -rf "$BUILD_DIR"; mkdir -p "$BUILD_DIR" "$MASTER_DIR"

# 1. grade the known-good example: verdict.json carries G4 attrs (rects, k)
"$JUDGE_DIR/grade.sh" "$DEMO_DIR/examples/good/scene.usda" \
    --seed 0 --json "$BUILD_DIR/verdict.json" | tail -3

# 2. scene dump from the pinned nanousd C dumper (out-of-process, exactly
#    the way G2 reads the primes)
"$PREFIX/bin/nanousd_dump" "$PREFIX/build/nanousd/Release/libnanousd.so" \
    "$DEMO_DIR/examples/good/scene.usda" > "$BUILD_DIR/scene_dump.json"

# 3. selftest.json (mutant kill matrix)
"$JUDGE_DIR/selftest.sh" --json "$BUILD_DIR/selftest.json" \
    >/tmp/selftest.make_media.log 2>&1 || {
        cat /tmp/selftest.make_media.log >&2
        exit 1
    }

# 4. figures (result.png + loop.png) from the judge outputs above
"$PY" "$MEDIA_DIR/figures.py"

# 5. a real setup log extract for the terminal shot
if [ -s /tmp/setup_run1.log ]; then
    grep -E "^\[setup\] " /tmp/setup_run1.log > "$MEDIA_DIR/setup_progress.txt" || true
fi

# 6. video (master mp4 ignored, web encode committed)
SETUP_WALL_S="${DEMO_SETUP_WALL_S:-853}"
DEMO_SETUP_WALL_S="$SETUP_WALL_S" export DEMO_SETUP_WALL_S
"$PY" "$MEDIA_DIR/build_video.py"

# 7. MANIFEST.json (sha256 per committed file)
"$PY" - "$MEDIA_DIR" <<'PY'
import hashlib, json, os, subprocess, sys
media = sys.argv[1]
man = []
for root, _, files in os.walk(media):
    for f in sorted(files):
        p = os.path.join(root, f)
        rel = os.path.relpath(p, media)
        if rel == "MANIFEST.json":
            continue
        if "/master/" in rel or rel.startswith("build/") or rel.startswith("build_"):
            continue
        man.append({"file": rel,
                    "size_bytes": os.path.getsize(p),
                    "sha256": hashlib.sha256(open(p, "rb").read()).hexdigest(),
                    "produced_by": "media/make_media.sh"})
json.dump({"generated_at": __import__("datetime").datetime.utcnow().isoformat()+"Z",
           "commit": subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip(),
           "files": man}, open(os.path.join(media, "MANIFEST.json"), "w"), indent=2)
print("[make_media] wrote MANIFEST.json")
PY
echo "[make_media] DONE"
