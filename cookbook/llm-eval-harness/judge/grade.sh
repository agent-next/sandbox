#!/usr/bin/env bash
# judge/grade.sh — run every gate on the harness artifact (samples.jsonl + eval.py)
# Usage: judge/grade.sh <samples.jsonl> <eval.py> [--json out.json] [--seed N]
# judge/ is checksummed before and after to prove the artifact cannot modify it.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK="$SCRIPT_DIR/check_gates.py"

SAMPLES=""
EVALPY=""
JSON_OUT=""
SEED=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --json)  JSON_OUT="$2"; shift 2 ;;
        --seed)  SEED="$2"; shift 2 ;;
        *)       if [[ -z "$SAMPLES" ]]; then SAMPLES="$1";
                 elif [[ -z "$EVALPY" ]]; then EVALPY="$1";
                 else echo "[grade] ERROR: unexpected argument $1" >&2; exit 2; fi
                 shift ;;
    esac
done

if [[ -z "$SAMPLES" || -z "$EVALPY" ]]; then
    echo "Usage: grade.sh <samples.jsonl> <eval.py> [--json out.json] [--seed N]" >&2
    exit 2
fi
for f in "$SAMPLES" "$EVALPY"; do
    [[ -f "$f" ]] || { echo "[grade] ERROR: no such file: $f" >&2; exit 2; }
done

# Judge-integrity checksum (before)
SUM_BEFORE="$(cd "$SCRIPT_DIR" && find . -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)"

T_START="$(date +%s.%N)"
set +e
python3 "$CHECK" "$SAMPLES" "$EVALPY" --json "$JSON_OUT" --seed "$SEED"
RC=$?
set -e

# Wall time lives under 'timing' only; the rest of the verdict must be
# byte-identical between two runs at the same seed (DEMO-STANDARD.md).
if [[ -n "$JSON_OUT" && -f "$JSON_OUT" ]]; then
    T_ELAPSED="$(python3 -c "import sys;print(float(sys.argv[1])-float(sys.argv[2]))" \
                     "$(date +%s.%N)" "$T_START")"
    python3 - "$JSON_OUT" "$SEED" "$T_ELAPSED" <<'PY'
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
exit $RC
