#!/usr/bin/env bash
# judge/grade.sh — run all six SPEC gates on one artifact.
# Usage: judge/grade.sh <artifact_dir> [--seed N] [--json out.json]
#                       [--keep-frames DIR] [--frames "i j k"]
#
# The artifact is copied to a scratch directory; the committed files are
# never modified.  judge/ is checksummed before and after; the pinned
# upstream sources are sha256-verified at every grade.  The scene runs
# twice inside one headless Chromium (SwiftShader CPU WebGL) under
# judge/driver/ — the determinism gate compares the two runs.
#
# --keep-frames DIR writes real PNGs of the chosen frames (from run 1's
# RGBA readback, encoded with stdlib Python) for media/.
#
# Exit: 0 only if every gate passes; 2 on usage/environment errors.

set -euo pipefail

ARTIFACT_DIR=""
JSON_OUT=""
SEED=0
KEEP_FRAMES=""
FRAME_IDXS=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --json)         JSON_OUT="$2"; shift 2 ;;
        --seed)         SEED="$2"; shift 2 ;;
        --keep-frames)  KEEP_FRAMES="$2"; shift 2 ;;
        --frames)       FRAME_IDXS="$2"; shift 2 ;;
        *)              ARTIFACT_DIR="$1"; shift ;;
    esac
done

if [[ -z "$ARTIFACT_DIR" || ! -d "$ARTIFACT_DIR" ]]; then
    echo "Usage: $0 <artifact_dir> [--seed N] [--json out.json] [--keep-frames DIR]" >&2
    exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ABS_ARTIFACT="$(cd "$ARTIFACT_DIR" && pwd)"

for f in config.json drive.js obstacle.frag; do
    if [[ ! -f "$ABS_ARTIFACT/$f" ]]; then
        echo "[grade] ERROR: missing $f — not a webgl-fluid artifact" >&2
        exit 2
    fi
done

PREFIX="$HOME/.wfs-fluid"
NODE="$PREFIX/node/bin/node"
if [[ ! -x "$NODE" ]]; then
    echo "[grade] ERROR: toolchain missing — run judge/setup.sh first" >&2
    exit 2
fi
export PLAYWRIGHT_BROWSERS_PATH="$PREFIX"
# playwright-core lives in judge/vendor (installed by setup.sh); Node's
# default lookup does not descend into vendor/, so point NODE_PATH at it.
export NODE_PATH="$SCRIPT_DIR/vendor/node_modules"

echo "[grade] artifact  : $ABS_ARTIFACT"
echo "[grade] seed      : $SEED"

# --- pinned upstream integrity (sha256 at every grade) ----------------------
pin() { grep "^$1=" "$SCRIPT_DIR/setup.sh" | head -1 | cut -d'"' -f2; }
for pair in "script.js:SCRIPT_SHA256" "dat.gui.min.js:DATGUI_SHA256"; do
    f="${pair%%:*}"; var="${pair##*:}"
    want="$(pin "$var")"
    got="$(sha256sum "$SCRIPT_DIR/upstream/$f" | cut -d' ' -f1)"
    if [[ "$got" != "$want" ]]; then
        echo "[grade] ERROR: upstream/$f sha256 mismatch" >&2
        echo "        expected $want" >&2
        echo "        got      $got" >&2
        exit 2
    fi
done
echo "[grade] upstream  : sha256 OK (script.js, dat.gui.min.js)"

# Judge-integrity checksum (before)
SUM_BEFORE="$(cd "$SCRIPT_DIR" && find . -type f -not -path './vendor/*' \
    -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)"

# Work on a scratch copy so the artifact is never written to
WORK="$(mktemp -d "${TMPDIR:-/tmp}/wfs-judge.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/scene"
cp -a "$ABS_ARTIFACT"/. "$WORK/scene"/

ABS_JSON=""
if [[ -n "$JSON_OUT" ]]; then
    mkdir -p "$(dirname "$JSON_OUT")"
    ABS_JSON="$(cd "$(dirname "$JSON_OUT")" && pwd)/$(basename "$JSON_OUT")"
fi
ABS_FRAMES=""
if [[ -n "$KEEP_FRAMES" ]]; then
    mkdir -p "$KEEP_FRAMES"
    ABS_FRAMES="$(cd "$KEEP_FRAMES" && pwd)"
fi

# Which frames to stash for media: caller's list, else a spread over the run.
STASH_ARGS=()
if [[ -n "$ABS_FRAMES" ]]; then
    if [[ -z "$FRAME_IDXS" ]]; then
        FRAME_IDXS="$(python3 - "$WORK/scene/config.json" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
n = c['frames']; pick = sorted({max(0, c['probe']['frame'] + 4),
                               min(n - 1, c['aim']['frame'] + 6),
                               min(n - 1, 2 * n // 3), n - 1})
print(' '.join(map(str, pick)))
PY
)"
    fi
    # run_scene.cjs: arg2 = stash flag (count when no idx list), rest = idxs
    STASH_ARGS=(1 $FRAME_IDXS)
fi

T_START="$(date +%s.%N)"

echo "[grade] scene     : headless Chromium + SwiftShader (2 runs)"
set +e
"$NODE" "$SCRIPT_DIR/run_scene.cjs" "$WORK/scene" "${STASH_ARGS[@]}" \
    > "$WORK/blob.json" 2>"$WORK/runner.log"
RC_RUN=$?
set -e
if [[ $RC_RUN -ne 0 ]]; then
    echo "[grade] ERROR: scene runner crashed (exit $RC_RUN)" >&2
    tail -20 "$WORK/runner.log" >&2 || true
    exit 2
fi

SAVE_ARG=()
[[ -n "$ABS_FRAMES" ]] && SAVE_ARG=(--save-frames "$ABS_FRAMES")

set +e
python3 "$SCRIPT_DIR/check_gates.py" "$WORK/scene" "$WORK/blob.json" \
    --json "$WORK/verdict.json" "${SAVE_ARG[@]}"
RC=$?
set -e

if [[ -n "$ABS_JSON" && -f "$WORK/verdict.json" ]]; then
    T_ELAPSED="$(python3 -c "import sys;print(float(sys.argv[1])-float(sys.argv[2]))" \
                     "$(date +%s.%N)" "$T_START")"
    python3 - "$WORK/verdict.json" "$ABS_JSON" "$SEED" "$T_ELAPSED" <<'PY'
import json, sys
src, dst, seed, secs = sys.argv[1], sys.argv[2], int(sys.argv[3]), float(sys.argv[4])
with open(src) as f:
    v = json.load(f)
v['seed'] = seed
v['timing'] = {'wall_seconds': round(secs, 3)}
with open(dst, 'w') as f:
    json.dump(v, f, indent=2)
    f.write('\n')
PY
fi

# Judge-integrity checksum (after)
SUM_AFTER="$(cd "$SCRIPT_DIR" && find . -type f -not -path './vendor/*' \
    -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)"
if [[ "$SUM_BEFORE" != "$SUM_AFTER" ]]; then
    echo "[grade] ERROR: judge/ contents changed during grading" >&2
    exit 2
fi

echo "[grade] exit code: $RC (0 = all gates passed)"
exit $RC
