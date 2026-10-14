#!/usr/bin/env bash
# judge/grade.sh — run every gate on a site artifact.
# Usage: judge/grade.sh <artifact_dir> [--seed N] [--json out.json] [--trace dir]
# Serves a scratch copy of the artifact over 127.0.0.1 (port derived from the
# seed) and measures it in pinned headless Chromium. The committed artifact is
# never written to, and judge/ is checksummed before and after to prove the
# artifact cannot modify the judge.

set -euo pipefail

ARTIFACT_DIR=""
JSON_OUT=""
SEED=42
TRACE_DIR=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --json)  JSON_OUT="$2"; shift 2 ;;
        --seed)  SEED="$2"; shift 2 ;;
        --trace) TRACE_DIR="$2"; shift 2 ;;
        *)       ARTIFACT_DIR="$1"; shift ;;
    esac
done

if [[ -z "$ARTIFACT_DIR" || ! -f "$ARTIFACT_DIR/index.html" ]]; then
    echo "Usage: $0 <artifact_dir with index.html> [--seed N] [--json out.json] [--trace dir]" >&2
    exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
ABS_ARTIFACT="$(cd "$ARTIFACT_DIR" && pwd)"

export PLAYWRIGHT_BROWSERS_PATH="$HOME/.cache/ms-playwright"

VENV_PY="$HOME/.taste-judge/venv/bin/python"
AXE_JS="$HOME/.taste-judge/axe/axe.min.js"
if [[ ! -x "$VENV_PY" ]]; then
    echo "[grade] ERROR: $VENV_PY missing — run bash judge/setup.sh first" >&2
    exit 2
fi
for f in "$AXE_JS" "$BASE_DIR/brief.md"; do
    [[ -f "$f" ]] || { echo "[grade] ERROR: missing $f" >&2; exit 2; }
done

# judge-integrity checksum (before)
SUM_BEFORE="$(cd "$SCRIPT_DIR" && find . -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)"

echo "[grade] artifact : $ABS_ARTIFACT"
echo "[grade] seed     : $SEED"

# scratch copy; serve over a deterministic localhost port
WORK="$(mktemp -d /tmp/taste-judge.XXXXXX)"
trap 'rm -rf "$WORK"; [[ -n "${SERVER_PID:-}" ]] && kill "$SERVER_PID" 2>/dev/null || true' EXIT
cp -a "$ABS_ARTIFACT"/. "$WORK/site"/
PORT=$((41000 + SEED % 1000))
( cd "$WORK/site" && exec "$VENV_PY" -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1 ) &
SERVER_PID=$!
for _ in $(seq 1 50); do
    curl -sf -o /dev/null "http://127.0.0.1:$PORT/index.html" && break
    sleep 0.1
done
BASE_URL="http://127.0.0.1:$PORT/index.html"

JSON_ARG=() ; SHOTS_ARG=()
ABS_JSON=""
if [[ -n "$JSON_OUT" ]]; then
    mkdir -p "$(dirname "$JSON_OUT")"
    ABS_JSON="$(cd "$(dirname "$JSON_OUT")" && pwd)/$(basename "$JSON_OUT")"
    JSON_ARG=(--json "$ABS_JSON")
fi
if [[ -n "$TRACE_DIR" ]]; then
    mkdir -p "$TRACE_DIR"
    SHOTS_ARG=(--shots "$TRACE_DIR")
fi

T_START="$(date +%s.%N)"
set +e
"$VENV_PY" "$SCRIPT_DIR/check_gates.py" "$WORK/site" "$BASE_URL" \
    --axe "$AXE_JS" --brief "$BASE_DIR/brief.md" \
    "${JSON_ARG[@]}" "${SHOTS_ARG[@]}" >"$WORK/grade_out.json"
RC=$?
set -e
[[ -n "${SERVER_PID:-}" ]] && kill "$SERVER_PID" 2>/dev/null || true
SERVER_PID=""

if [[ -n "$JSON_OUT" && -f "$ABS_JSON" ]]; then
    T_ELAPSED="$(python3 -c "import sys;print(float(sys.argv[1])-float(sys.argv[2]))" \
                     "$(date +%s.%N)" "$T_START")"
    python3 - "$ABS_JSON" "$SEED" "$T_ELAPSED" <<'PY'
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

SUM_AFTER="$(cd "$SCRIPT_DIR" && find . -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)"
if [[ "$SUM_BEFORE" != "$SUM_AFTER" ]]; then
    echo "[grade] ERROR: judge/ contents changed during grading" >&2
    exit 2
fi

echo "[grade] exit code: $RC (0 = all gates passed)"
exit $RC
