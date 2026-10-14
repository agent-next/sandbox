#!/usr/bin/env bash
# judge/grade.sh — run all gates on a sim.py + params.json artifact
# Usage: judge/grade.sh <artifact_dir> [--json out.json] [--seed N]
# The artifact is run in a scratch output dir; judge/ is checksummed
# before and after so the artifact cannot modify the judge.

set -euo pipefail

ARTIFACT_DIR=""
JSON_OUT=""
SEED=0
STEPS=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --json)  JSON_OUT="$2"; shift 2 ;;
        --seed)  SEED="$2"; shift 2 ;;
        --steps) STEPS="$2"; shift 2 ;;
        *)       ARTIFACT_DIR="$1"; shift ;;
    esac
done

if [[ -z "$ARTIFACT_DIR" || ! -d "$ARTIFACT_DIR" ]]; then
    echo "Usage: $0 <artifact_dir> [--json out.json] [--seed N]" >&2
    exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ABS_ARTIFACT="$(cd "$ARTIFACT_DIR" && pwd)"

for f in sim.py params.json; do
    if [[ ! -f "$ABS_ARTIFACT/$f" ]]; then
        echo "[grade] ERROR: missing $f — not a taichi-mpm-snow artifact" >&2
        exit 2
    fi
done

echo "[grade] artifact  : $ABS_ARTIFACT"
echo "[grade] seed      : $SEED"

# Judge-integrity checksum (before)
SUM_BEFORE="$(cd "$SCRIPT_DIR" && find . -type f ! -name 'VERSIONS.txt' -print0 | \
              sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)"

WORK="$(mktemp -d /tmp/mpm-judge.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

JSON_ARG=(--json "$WORK/verdict.json")
[[ -n "$STEPS" ]] && STEPS_ARG=(--steps "$STEPS") || STEPS_ARG=()

T_START="$(date +%s.%N)"

set +e
python3 "$SCRIPT_DIR/check_gates.py" "$ABS_ARTIFACT" "${JSON_ARG[@]}" \
    --seed "$SEED" "${STEPS_ARG[@]}"
RC=$?
set -e

if [[ -n "$JSON_OUT" ]]; then
    mkdir -p "$(dirname "$JSON_OUT")"
    ABS_JSON="$(cd "$(dirname "$JSON_OUT")" && pwd)/$(basename "$JSON_OUT")"
    # attach seed + timing under 'timing' so verdicts are byte-identical
    # for a fixed seed apart from that key
    T_ELAPSED="$(python3 -c "import sys;print(float(sys.argv[1])-float(sys.argv[2]))" \
                     "$(date +%s.%N)" "$T_START")"
    python3 - "$WORK/verdict.json" "$ABS_JSON" "$SEED" "$T_ELAPSED" <<'PY'
import json, sys
src, dst, seed, secs = sys.argv[1], sys.argv[2], int(sys.argv[3]), float(sys.argv[4])
v = json.load(open(src))
v['seed'] = seed
v['timing'] = {'wall_seconds': round(secs, 3)}
with open(dst, 'w') as f:
    json.dump(v, f, indent=2)
    f.write('\n')
print(open(dst).read())
PY
fi

# Judge-integrity checksum (after)
SUM_AFTER="$(cd "$SCRIPT_DIR" && find . -type f ! -name 'VERSIONS.txt' -print0 | \
             sort -z | xargs -0 sha256sum | sha256sum | cut -d' ' -f1)"
if [[ "$SUM_BEFORE" != "$SUM_AFTER" ]]; then
    echo "[grade] ERROR: judge/ contents changed during grading" >&2
    exit 2
fi

echo "[grade] exit code: $RC (0 = all gates passed)"
exit $RC
