#!/usr/bin/env bash
# cookbook/plc-st judge: build an artifact and run every gate.
#
# Usage:
#   bash judge/grade.sh <tank_ctrl.st> [--seed N] [--json out.json] [--trace DIR]
#
# 1. verifies the artifact is a self-contained Structured Text file
# 2. copies it into a scratch build dir named after the artifact
# 3. compiles it with the pinned MATIEC iec2c into C
# 4. links harness.c + generated C into `engine`
# 5. runs every scenario gate in grade.py
# 6. verifies the judge sources were not modified by the artifact
#
# Exit 0 iff every gate passes.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${HOME}/.plc-st"
BIN="${PREFIX}/bin"
LIBC="${PREFIX}/lib/C"
MATIEC="${BIN}/iec2c"

ARTIFACT="${1:-}"
SEED="20261014"
JSON_OUT=""
TRACE_DIR=""
while [ $# -gt 1 ]; do
    case "$2" in
        --seed) SEED="$3"; shift 2 ;;
        --json) JSON_OUT="$3"; shift 2 ;;
        --trace) TRACE_DIR="$3"; shift 2 ;;
        *) shift ;;
    esac
done

fail() { echo "grade: $*" >&2; exit 1; }

[ -n "$ARTIFACT" ] || fail "usage: grade.sh <tank_ctrl.st> [--seed N] [--json out.json]"
[ -f "$ARTIFACT" ] || fail "artifact not found: $ARTIFACT"
[ -x "$MATIEC" ] || fail "iec2c not installed -- run 'bash judge/setup.sh' first (looks for $MATIEC)"
[ -d "$LIBC" ] || fail "MATIEC runtime headers missing -- run 'bash judge/setup.sh' first"

# validate the artifact is a single self-contained ST program with our interface
grep -q "PROGRAM tank_ctrl" "$ARTIFACT" || fail "artifact has no PROGRAM tank_ctrl"
grep -q "CONFIGURATION tank_cfg" "$ARTIFACT" || fail "artifact has no CONFIGURATION tank_cfg"
for sig in "start" "estop" "high_ls" "low_ls" "level" \
           "pump" "inlet_valve" "outlet_valve" "alarm" "running"; do
    grep -q "$sig" "$ARTIFACT" || fail "artifact missing interface signal '$sig'"
done

# MATIEC passes {{ ... }} blocks through as raw C; the artifact must be plain ST
if grep -q '{{' "$ARTIFACT"; then
    fail "artifact embeds C code ({{ ... }} pragma); only plain Structured Text is graded"
fi

# hash the judge before any artifact code runs
JUDGE_HASH_BEFORE="$(find "$HERE" -type f ! -name 'setup.sh' ! -name 'grade.sh' \
                     ! -name 'selftest.sh' ! -name 'RECEIPT.md' -exec sha256sum {} + | sort | sha256sum)"

# scratch build dir
BASE="$(basename "$ARTIFACT" .st)"
BUILD="$(mktemp -d)/${BASE}"
mkdir -p "$BUILD"
cp "$ARTIFACT" "${BUILD}/tank_ctrl.st"

# compile ST -> C
( cd "$BUILD" && "$MATIEC" tank_ctrl.st -I "${PREFIX}/lib" >/dev/null 2>&1 ) \
    || fail "iec2c failed on $(basename "$ARTIFACT")"

# link harness + generated C into engine
gcc -I "$BUILD" -I "$LIBC" "$HERE/harness.c" -o "$BUILD/engine" \
    || fail "gcc failed linking the scan-cycle engine"

# run every gate
TRACE_FLAG=""
if [ -n "$TRACE_DIR" ]; then
    TRACE_FLAG="--trace $TRACE_DIR"
fi
python3 "${HERE}/grade.py" "$BUILD" --seed "$SEED" ${JSON_OUT:+--json "$JSON_OUT"} ${TRACE_FLAG}

# the artifact must not have touched the judge
JUDGE_HASH_AFTER="$(find "$HERE" -type f ! -name 'setup.sh' ! -name 'grade.sh' \
                    ! -name 'selftest.sh' ! -name 'RECEIPT.md' -exec sha256sum {} + | sort | sha256sum)"
[ "$JUDGE_HASH_BEFORE" = "$JUDGE_HASH_AFTER" ] \
    || fail "judge sources changed during grading (checksum mismatch)"

echo "grade: PASS (all gates; judge integrity verified)"