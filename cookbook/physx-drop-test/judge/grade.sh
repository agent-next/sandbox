#!/usr/bin/env bash
# judge/grade.sh — run every gate on a USD drop-test scene.
# Usage: judge/grade.sh <scene.usda> [--seed N] [--json out.json]
#
# The artifact is copied to a scratch directory and simulated there; the
# committed scene is never touched.  judge/ is checksummed before and after
# to prove the artifact cannot modify the judge.  Prints one JSON verdict;
# exits 0 only if all gates pass.

set -euo pipefail

SCENE=""
JSON_OUT=""
SEED=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --json) JSON_OUT="$2"; shift 2 ;;
        --seed) SEED="$2"; shift 2 ;;
        *)      SCENE="$1"; shift ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${PHYSX_DROP_TEST_VENV:-$HOME/.venvs/physx-drop-test}"
PY="$VENV/bin/python"

if [[ -z "$SCENE" ]]; then
    echo "Usage: $0 <scene.usda> [--seed N] [--json out.json]" >&2
    exit 2
fi
if [[ ! -f "$SCENE" ]]; then
    echo "[grade] ERROR: no such file: $SCENE" >&2
    exit 2
fi
if [[ ! -x "$PY" ]]; then
    echo "[grade] ERROR: venv python not found at $PY — run judge/setup.sh first" >&2
    exit 2
fi
SCENE="$(cd "$(dirname "$SCENE")" && pwd)/$(basename "$SCENE")"

# Deterministic execution: 1 CPU thread.  The warp kernel cache is kept
# under $HOME so repeat runs skip kernel compilation (contents identical).
WORK="$(mktemp -d /tmp/physx-grade.XXXXXX)"
WARP_CACHE="${WARP_CACHE_PATH:-$HOME/.cache/physx-drop-test/warp}"
mkdir -p "$WARP_CACHE"
trap 'rm -rf "$WORK"' EXIT

# Judge-integrity checksum (before)
SUM_BEFORE="$(cd "$SCRIPT_DIR" && find . -type f -not -path './scratch*' -print0 \
              | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)"

# The artifact is the whole directory the scene came from, not just the
# file: grade.sh copies it verbatim into the scratch artifact dir (an
# artifact that ships forged judge outputs ships them here) and simulates
# the copy.  The scene path is exactly the one that was handed to grade.sh.
mkdir -p "$WORK/artifact"
SCENE_DIR="$(dirname "$SCENE")"
SCENE_BASE="$(basename "$SCENE")"
cp -a "$SCENE_DIR/." "$WORK/artifact/"

T_START="$(date +%s.%N)"

set +e
WARP_CACHE_PATH="$WARP_CACHE" "$PY" -I "$SCRIPT_DIR/simulate.py" \
    "$WORK/artifact/$SCENE_BASE" "$WORK/sim" >"$WORK/simulate.log" 2>&1
SIM_RC=$?
if [[ $SIM_RC -ne 0 ]]; then
    set -e
    echo "[grade] ERROR: simulation failed (exit $SIM_RC):" >&2
    tail -5 "$WORK/simulate.log" >&2
    if [[ -n "$JSON_OUT" ]]; then
        mkdir -p "$(dirname "$JSON_OUT")"
        ABS_JSON="$(cd "$(dirname "$JSON_OUT")" && pwd)/$(basename "$JSON_OUT")"
        printf '{"all_gates_passed": false, "error": "simulation failed", "seed": %s}\n' \
            "$SEED" > "$ABS_JSON"
    fi
    exit 1
fi

JSON_ARG=()
if [[ -n "$JSON_OUT" ]]; then
    mkdir -p "$(dirname "$JSON_OUT")"
    ABS_JSON="$(cd "$(dirname "$JSON_OUT")" && pwd)/$(basename "$JSON_OUT")"
    JSON_ARG=(--json "$ABS_JSON")
fi
# The oracle re-derives every judged quantity from the simulator's own
# output files (traj.npz/meta.json) plus the same scratch copy of the
# scene the simulator stepped — never from anything the artifact can reach.
"$PY" -I "$SCRIPT_DIR/check_gates.py" "$WORK/sim" \
    "$WORK/artifact/$SCENE_BASE" \
    "${JSON_ARG[@]}"
RC=$?
set -e

# Wall time (and seed) live only under 'timing' so the rest of the JSON is
# byte-identical across runs with the same seed.
if [[ -n "$JSON_OUT" && -f "${ABS_JSON:-}" ]]; then
    T_ELAPSED="$(python3 -c "import sys;print(float(sys.argv[1])-float(sys.argv[2]))" \
                     "$(date +%s.%N)" "$T_START")"
    python3 - "$ABS_JSON" "$SEED" "$T_ELAPSED" <<'PY'
import json, sys
path, seed, secs = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
with open(path) as f:
    v = json.load(f)
v["seed"] = seed
v["timing"] = {"wall_seconds": round(secs, 3)}
with open(path, "w") as f:
    json.dump(v, f, indent=2)
    f.write("\n")
PY
fi

# Judge-integrity checksum (after)
SUM_AFTER="$(cd "$SCRIPT_DIR" && find . -type f -not -path './scratch*' -print0 \
             | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)"
if [[ "$SUM_BEFORE" != "$SUM_AFTER" ]]; then
    echo "[grade] ERROR: judge/ contents changed during grading" >&2
    exit 2
fi

echo "[grade] exit code: $RC (0 = all gates passed)"
exit $RC
