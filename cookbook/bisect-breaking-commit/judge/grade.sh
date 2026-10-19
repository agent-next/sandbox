#!/usr/bin/env bash
# judge/grade.sh — run every gate on a sweep-report artifact (a JSON file).
# Usage: judge/grade.sh <artifact.json> [--seed N] [--json out.json]
# The artifact is copied to a scratch directory and graded there; the
# committed files are never modified.  judge/ is checksummed before and after
# to prove the artifact under test cannot modify the judge.

set -euo pipefail

ARTIFACT=""
JSON_OUT=""
SEED=20261015
while [[ $# -gt 0 ]]; do
    case "$1" in
        --json)  JSON_OUT="$2"; shift 2 ;;
        --seed)  SEED="$2"; shift 2 ;;
        *)       ARTIFACT="$1"; shift ;;
    esac
done

if [[ -z "$ARTIFACT" || ! -f "$ARTIFACT" ]]; then
    echo "Usage: $0 <artifact.json> [--seed N] [--json out.json]" >&2
    exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ABS_ARTIFACT="$(cd "$(dirname "$ARTIFACT")" && pwd)/$(basename "$ARTIFACT")"

echo "[grade] artifact : $ABS_ARTIFACT"

# Judge-integrity checksum (before)
SUM_BEFORE="$(cd "$SCRIPT_DIR" && find . -type f -print0 | sort -z \
              | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)"

# Work on a scratch copy so the artifact is never written to
WORK="$(mktemp -d /tmp/bisect-judge.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT
cp "$ABS_ARTIFACT" "$WORK/report.json"

JSON_ARG=()
if [[ -n "$JSON_OUT" ]]; then
    mkdir -p "$(dirname "$JSON_OUT")"
    ABS_JSON="$(cd "$(dirname "$JSON_OUT")" && pwd)/$(basename "$JSON_OUT")"
    JSON_ARG=(--json "$ABS_JSON")
fi

T_START="$(date +%s.%N)"

set +e
python3 -I "$SCRIPT_DIR/bisect_judge.py" "$WORK/report.json" --seed "$SEED" \
    "${JSON_ARG[@]}"
RC=$?
set -e

# Wall time goes under 'timing' only: two runs with the same seed must give
# identical verdict JSON apart from the timing key (DEMO-STANDARD.md).
if [[ -n "$JSON_OUT" && -f "${ABS_JSON:-}" ]]; then
    T_ELAPSED="$(python3 -c "import sys;print(float(sys.argv[1])-float(sys.argv[2]))" \
                     "$(date +%s.%N)" "$T_START")"
    python3 - "$ABS_JSON" "$T_ELAPSED" <<'PY'
import json, sys
path, secs = sys.argv[1], float(sys.argv[2])
with open(path) as f:
    v = json.load(f)
v.setdefault('timing', {})['wall_seconds'] = round(secs, 3)
with open(path, 'w') as f:
    json.dump(v, f, indent=2)
    f.write('\n')
PY
fi

# Judge-integrity checksum (after)
SUM_AFTER="$(cd "$SCRIPT_DIR" && find . -type f -print0 | sort -z \
             | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)"
if [[ "$SUM_BEFORE" != "$SUM_AFTER" ]]; then
    echo "[grade] ERROR: judge/ contents changed during grading" >&2
    exit 2
fi

echo "[grade] exit code: $RC (0 = all gates passed)"
exit $RC
