#!/usr/bin/env bash
# judge/grade.sh <artifact-dir> [--seed N] [--json out.json]
#
# Grades a CAD->USD artifact against the independent OpenCASCADE +
# usd-core oracle. Gates (see SPEC.md):
#   file_set  all three <key>.usda present, distinct, parse as USD
#   stage_meta      metersPerUnit=0.001 (±1e-9), upAxis=Z, defaultPrim valid
#   geometry_counts prim count > 0 and mesh count > 0 per part
#   bbox_match      USD world bbox vs oracle, per-axis endpoint deltas
#                   <= 1% of oracle extent (0.1 mm floor)
#   area_match      total triangle area within 3% of oracle face area
#   conversion_script  convert.sh reproduces all three parts from fresh
#                   sources, and each regenerated part passes gates 2-5
#
# The artifact runs in a scratch copy; judge/ is checksummed before and
# after — a mismatch fails the grade (the artifact may not modify the
# judge). Exit 0 only if every gate passes. Verdict JSON on stdout (and
# at --json path). Wall times live under the "timing" key.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_BASE="${CAD2USD_VENV_BASE:-$HOME/.venvs}"
JUDGE_PY="$VENV_BASE/cad2usd-judge/bin/python"
CONV_BIN="$VENV_BASE/cad2usd-convert/bin/usd-convert-cad"

usage() { echo "usage: judge/grade.sh <artifact-dir> [--seed N] [--json out.json]" >&2; exit 64; }

artifact=""
seed="0"
json_out=""
reconvert="1"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --seed) seed="$2"; shift 2 ;;
        --json) json_out="$2"; shift 2 ;;
        --no-reconvert) reconvert="0"; shift ;; # self-test only: skip gate 6
        -h|--help) usage ;;
        -*) echo "grade.sh: unknown flag $1" >&2; usage ;;
        *)  if [[ -n "$artifact" ]]; then echo "grade.sh: one artifact only" >&2; usage; fi
            artifact="$1"; shift ;;
    esac
done
[[ -n "$artifact" ]] || usage
[[ -x "$JUDGE_PY" && -x "$CONV_BIN" ]] || {
    echo "grade.sh: pinned venvs missing — run judge/setup.sh first" >&2; exit 1; }

# judge integrity: record checksums, compare at the end
JUDGE_SUMS="$(mktemp)"
trap 'rm -f "$JUDGE_SUMS"' EXIT
(cd "$SCRIPT_DIR" && find . -type f ! -path './.git/*' ! -path '*__pycache__*' -print0 | sort -z |
 xargs -0 sha256sum) > "$JUDGE_SUMS"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/cad2usd-grade.XXXXXX")"
trap 'rm -rf "$WORK" "$JUDGE_SUMS"' EXIT
# copy artifact; run everything against the copy
cp -r "$artifact" "$WORK/artifact"

echo "[grade] artifact: $artifact  seed: $seed"
set +e
"$JUDGE_PY" -I -B "$SCRIPT_DIR/grade_gates.py" \
    --work "$WORK" --demo "$DEMO_DIR" --seed "$seed" \
    --python "$JUDGE_PY" --converter "$CONV_BIN" \
    --reconvert "$reconvert" 2>&1 | sed 's/^/  /'
rc=${PIPESTATUS[0]}
set -e

# judge integrity check (after the artifact ran in the copy)
(cd "$SCRIPT_DIR" && find . -type f ! -path './.git/*' ! -path '*__pycache__*' -print0 | sort -z |
 xargs -0 sha256sum) | diff -q "$JUDGE_SUMS" - >/dev/null || {
    echo "[grade] ERROR: judge/ changed during grading — failing" >&2
    exit 1
}

verdict="$WORK/verdict.json"
if [[ -f "$verdict" ]]; then
    cat "$verdict"
    [[ -n "$json_out" ]] && cp "$verdict" "$json_out"
else
    echo "[grade] ERROR: no verdict JSON produced" >&2
    exit 1
fi
exit "$rc"
