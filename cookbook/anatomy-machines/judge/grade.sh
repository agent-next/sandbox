#!/usr/bin/env bash
# judge/grade.sh — run every gate on a figure artifact.
# Usage: judge/grade.sh <figure_dir> [--seed N] [--json out.json] [--shots dir]
#
# The artifact is copied to a scratch directory and served over
# 127.0.0.1 with python3's http.server; the browser the judge drives can
# only reach that copy, so the committed artifact is never modified.
# judge/ is checksummed before and after to prove the artifact cannot
# modify the judge.

set -euo pipefail

ARTIFACT_DIR=""
JSON_OUT=""
SHOTS_DIR=""
SEED=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --json)  JSON_OUT="$2"; shift 2 ;;
        --seed)  SEED="$2"; shift 2 ;;
        --shots) SHOTS_DIR="$2"; shift 2 ;;
        *)       ARTIFACT_DIR="$1"; shift ;;
    esac
done

if [[ -z "$ARTIFACT_DIR" || ! -d "$ARTIFACT_DIR" ]]; then
    echo "Usage: $0 <figure_dir> [--seed N] [--json out.json] [--shots dir]" >&2
    exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ABS_ARTIFACT="$(cd "$ARTIFACT_DIR" && pwd)"

HTML="$(find "$ABS_ARTIFACT" -maxdepth 1 -name '*.html' | sort | head -1)"
if [[ -z "$HTML" ]]; then
    echo "[grade] ERROR: no .html file at the top of $ARTIFACT_DIR — not a figure directory" >&2
    exit 2
fi

VENV="$HOME/.anatomy-judge/venv"
if [[ ! -x "$VENV/bin/python" ]]; then
    echo "[grade] ERROR: $VENV/bin/python missing — run judge/setup.sh first" >&2
    exit 2
fi

# Judge-integrity checksum (before)
SUM_BEFORE="$(cd "$SCRIPT_DIR" && find . -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)"

# Scratch copy + local HTTP server. The port is an environment detail and
# never appears in the verdict JSON.
WORK="$(mktemp -d /tmp/anat-judge.XXXXXX)"
SERVER_PID=""
cleanup() {
    [[ -n "$SERVER_PID" ]] && kill "$SERVER_PID" 2>/dev/null || true
    rm -rf "$WORK"
}
trap cleanup EXIT
cp -a "$ABS_ARTIFACT"/. "$WORK"/figure/
PORT=8642
for _attempt in 1 2 3 4 5; do
    python3 -m http.server "$PORT" --bind 127.0.0.1 \
        --directory "$WORK/figure" >/dev/null 2>&1 &
    SERVER_PID=$!
    sleep 0.7
    if curl -sf -o /dev/null "http://127.0.0.1:$PORT/$(basename "$HTML")"; then
        break
    fi
    kill "$SERVER_PID" 2>/dev/null || true
    SERVER_PID=""
    PORT=$((PORT + 1))
done
if [[ -z "$SERVER_PID" ]]; then
    echo "[grade] ERROR: could not serve the artifact on ports 8642-8646" >&2
    exit 2
fi

JSON_ARG=()
ABS_JSON=""
if [[ -n "$JSON_OUT" ]]; then
    mkdir -p "$(dirname "$JSON_OUT")"
    ABS_JSON="$(cd "$(dirname "$JSON_OUT")" && pwd)/$(basename "$JSON_OUT")"
    JSON_ARG=(--json "$ABS_JSON")
fi
SHOTS_ARG=()
if [[ -n "$SHOTS_DIR" ]]; then
    mkdir -p "$SHOTS_DIR"
    SHOTS_ARG=(--shots "$(cd "$SHOTS_DIR" && pwd)")
fi

echo "[grade] artifact : $ABS_ARTIFACT"
echo "[grade] served   : http://127.0.0.1:$PORT/$(basename "$HTML")"

T_START="$(date +%s.%N)"
set +e
PLAYWRIGHT_BROWSERS_PATH="$HOME/.cache/ms-playwright" \
    "$VENV/bin/python" "$SCRIPT_DIR/check_gates.py" \
    "http://127.0.0.1:$PORT/$(basename "$HTML")" \
    --seed "$SEED" --reference "$SCRIPT_DIR/reference" \
    "${JSON_ARG[@]}" "${SHOTS_ARG[@]}"
RC=$?
set -e

# Wall time lives under 'timing'; nothing else in the JSON may vary between
# runs at the same seed (DEMO-STANDARD.md, "Deterministic").
if [[ -n "$JSON_OUT" && -f "$ABS_JSON" ]]; then
    T_ELAPSED="$(python3 -c "import sys;print(float(sys.argv[1])-float(sys.argv[2]))" \
                     "$(date +%s.%N)" "$T_START")"
    python3 - "$ABS_JSON" "$SEED" "$T_ELAPSED" <<'PY'
import json, sys
path, seed, secs = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
with open(path) as f:
    v = json.load(f)
v['seed'] = seed
v.setdefault('timing', {})['wall_seconds'] = round(secs, 3)
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
exit $RC
