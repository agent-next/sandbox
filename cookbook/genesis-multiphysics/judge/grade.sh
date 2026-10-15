#!/usr/bin/env bash
# judge/grade.sh — run every gate on a scenario artifact.
# Usage: judge/grade.sh <scenario.py> [--seed N] [--json out.json]
#
# The scenario file is only ever *parsed* (imported as a data declaration)
# by the runner. The runner and gate checker live in judge/; judge/ is
# sha256-checksummed before and after the grade and the run happens in a
# mktemp scratch dir, so the artifact cannot modify the judge or smuggle
# results past it.

set -euo pipefail

ARTIFACT=""
JSON_OUT=""
SEED=""
SAVE_FRAMES=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --json)        JSON_OUT="$2"; shift 2 ;;
        --seed)        SEED="$2"; shift 2 ;;
        --save-frames) SAVE_FRAMES="$2"; shift 2 ;;
        *)             ARTIFACT="$1"; shift ;;
    esac
done

if [[ -z "$ARTIFACT" || ! -f "$ARTIFACT" ]]; then
    echo "Usage: $0 <scenario.py> [--seed N] [--json out.json]" >&2
    exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ABS_ARTIFACT="$(cd "$(dirname "$ARTIFACT")" && pwd)/$(basename "$ARTIFACT")"

# The toolchain lives in the venv created by judge/setup.sh; fall back to
# PATH python3 so the script is still usable in an activated venv.
VENV_PY="$HOME/.genesis-demo-venv/bin/python"
if [[ -x "$VENV_PY" ]]; then
    PY="$VENV_PY"
else
    PY="$(command -v python3)"
fi

echo "[grade] scenario   : $ABS_ARTIFACT"

# Judge-integrity checksum (before)
SUM_BEFORE="$(cd "$SCRIPT_DIR" && find . -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)"

WORK="$(mktemp -d /tmp/gen-judge.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

SEED_ARG=()
if [[ -n "$SEED" ]]; then SEED_ARG=(--seed "$SEED"); fi
FRAMES_ARG=()
if [[ -n "$SAVE_FRAMES" ]]; then
    mkdir -p "$SAVE_FRAMES"
    FRAMES_ARG=(--save-frames "$(cd "$SAVE_FRAMES" && pwd)")
fi

T_START="$(date +%s.%N)"

set +e
"$PY" -I "$SCRIPT_DIR/run_scenario.py" "$ABS_ARTIFACT" "${SEED_ARG[@]}" \
    --out "$WORK/run1.npz" "${FRAMES_ARG[@]}" >"$WORK/run1.log" 2>&1
RC1=$?
"$PY" -I "$SCRIPT_DIR/run_scenario.py" "$ABS_ARTIFACT" "${SEED_ARG[@]}" \
    --out "$WORK/run2.npz" >"$WORK/run2.log" 2>&1
RC2=$?
set -e

if [[ $RC1 -ne 0 ]]; then
    echo "[grade] runner failed on run 1 (exit $RC1):" >&2
    tail -20 "$WORK/run1.log" >&2
    RC=2
fi
if [[ $RC2 -ne 0 ]]; then
    echo "[grade] runner failed on run 2 (exit $RC2):" >&2
    tail -20 "$WORK/run2.log" >&2
    RC=2
fi

if [[ $RC1 -eq 0 && $RC2 -eq 0 ]]; then
    JSON_ARG=()
    if [[ -n "$JSON_OUT" ]]; then
        mkdir -p "$(dirname "$JSON_OUT")"
        ABS_JSON="$(cd "$(dirname "$JSON_OUT")" && pwd)/$(basename "$JSON_OUT")"
        JSON_ARG=(--json "$ABS_JSON")
    fi
    set +e
    "$PY" -I "$SCRIPT_DIR/check_gates.py" "$ABS_ARTIFACT" \
        --run1 "$WORK/run1.npz" --run2 "$WORK/run2.npz" "${JSON_ARG[@]}"
    RC=$?
    set -e
fi

# wall time under 'timing' only (determinism compares the rest byte-wise)
if [[ -n "${JSON_OUT:-}" && -f "${ABS_JSON:-}" ]]; then
    T_ELAPSED="$(python3 -c "import sys;print(float(sys.argv[1])-float(sys.argv[2]))" \
                     "$(date +%s.%N)" "$T_START")"
    python3 - "${ABS_JSON}" "${SEED:-0}" "$T_ELAPSED" <<'PY'
import json, sys
path, seed, secs = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
with open(path) as f:
    v = json.load(f)
v['seed'] = seed
v['timing'] = {'wall_seconds': round(secs, 3)}
with open(path, 'w') as f:
    json.dump(v, f, indent=2)
    f.write('\n')
PY
fi

# Judge-integrity checksum (after)
SUM_AFTER="$(cd "$SCRIPT_DIR" && find . -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)"
if [[ "$SUM_BEFORE" != "$SUM_AFTER" ]]; then
    echo "[grade] ERROR: judge/ contents changed during grading" >&2
    exit 2
fi

echo "[grade] exit code: $RC (0 = all gates passed)"
exit "$RC"
