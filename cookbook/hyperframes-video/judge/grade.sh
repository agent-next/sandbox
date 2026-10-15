#!/usr/bin/env bash
# judge/grade.sh — run all gates on an artifact directory
# Usage: judge/grade.sh <artifact_dir> [--json out.json] [--seed N]
#
# The artifact (spec.json + composition/) is copied to a scratch dir; the
# committed files are never modified.  judge/ is checksummed before and
# after to prove the artifact cannot modify the judge.

set -euo pipefail

ARTIFACT_DIR=""
JSON_OUT=""
SEED=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --json)  JSON_OUT="$2"; shift 2 ;;
        --seed)  SEED="$2"; shift 2 ;;
        *)       ARTIFACT_DIR="$1"; shift ;;
    esac
done

if [[ -z "$ARTIFACT_DIR" || ! -d "$ARTIFACT_DIR" ]]; then
    echo "Usage: $0 <artifact_dir> [--json out.json] [--seed N]" >&2
    exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ABS_ARTIFACT="$(cd "$ARTIFACT_DIR" && pwd)"
ENV_FILE="$HOME/.hyperframes-judge/env.sh"
if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$ENV_FILE"
fi

for f in spec.json composition/index.html; do
    if [[ ! -f "$ABS_ARTIFACT/$f" ]]; then
        echo "[grade] ERROR: missing $f — not a hyperframes-video artifact" >&2
        exit 2
    fi
done

echo "[grade] artifact  : $ABS_ARTIFACT"

# Judge-integrity checksum (before)
SUM_BEFORE="$(cd "$SCRIPT_DIR" && find . -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)"

# Work on a scratch copy so the artifact is never written to
WORK="$(mktemp -d /tmp/hf-judge.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/case"
cp -a "$ABS_ARTIFACT"/. "$WORK/case/"

JSON_ARG=()
ABS_JSON=""
if [[ -n "$JSON_OUT" ]]; then
    mkdir -p "$(dirname "$JSON_OUT")"
    ABS_JSON="$(cd "$(dirname "$JSON_OUT")" && pwd)/$(basename "$JSON_OUT")"
    JSON_ARG=(--json "$ABS_JSON")
fi

T_START="$(date +%s.%N)"

set +e
python3 "$SCRIPT_DIR/check_gates.py" "$WORK/case" "${JSON_ARG[@]}"
RC=$?
set -e

# Seed and wall time live under 'timing': two runs with the same seed must
# give byte-identical verdict JSON outside this key (DEMO-STANDARD.md).
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

# Judge-integrity checksum (after)
SUM_AFTER="$(cd "$SCRIPT_DIR" && find . -type f -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)"
if [[ "$SUM_BEFORE" != "$SUM_AFTER" ]]; then
    echo "[grade] ERROR: judge/ contents changed during grading" >&2
    exit 2
fi

echo "[grade] exit code: $RC (0 = all gates passed)"
exit $RC
