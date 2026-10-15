#!/usr/bin/env bash
# judge/grade.sh <artifact.py> [--seed N] [--json out.json]
# Runs all gates for the ovui-native-ui demo; exits 0 only if all pass.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="${TOOLS_DIR:-$HOME/tools/ovui-native-ui}"
VENV="$TOOLS_DIR/venv"
STUB="$TOOLS_DIR/cuda-stub"
SEED="1234"

ARTIFACT=""
JSON_OUT=""
while [ $# -gt 0 ]; do
  case "$1" in
    --seed) SEED="$2"; shift 2;;
    --json) JSON_OUT="$2"; shift 2;;
    -h|--help) grep '^#' "$0" | head -3; exit 0;;
    *) ARTIFACT="$1"; shift;;
  esac
done
[ -n "$ARTIFACT" ] || { echo "usage: grade.sh <artifact.py> [--seed N] [--json out.json]" >&2; exit 2; }
[ -x "$VENV/bin/python" ] || { echo "run judge/setup.sh first" >&2; exit 2; }

SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT
cp "$ARTIFACT" "$SCRATCH/panel.py"

JUDGE_BEFORE="$(cd "$HERE" && find . -type f ! -name '*.pyc' -print0 | sort -z | xargs -0 sha256sum)"

export OMNIUI_HEADLESS=1
export LD_LIBRARY_PATH="${STUB}:${LD_LIBRARY_PATH:-}"
export OVUI_SEED="$SEED"

t0=$(date +%s)
"$VENV/bin/python" -I "$HERE/render.py" "$SCRATCH/panel.py" "$SCRATCH/shot1.png" "$SCRATCH/facts1.json"
"$VENV/bin/python" -I "$HERE/render.py" "$SCRATCH/panel.py" "$SCRATCH/shot2.png" "$SCRATCH/facts2.json"
t1=$(date +%s)

"$VENV/bin/python" -I "$HERE/check_gates.py" \
  "$SCRATCH/facts1.json" "$SCRATCH/shot1.png" \
  "$HERE/reference.json" \
  "$SCRATCH/facts2.json" "$SCRATCH/shot2.png" \
  ${JSON_OUT:+--json "$JSON_OUT"}

JUDGE_AFTER="$(cd "$HERE" && find . -type f ! -name '*.pyc' -print0 | sort -z | xargs -0 sha256sum)"
if [ "$JUDGE_BEFORE" != "$JUDGE_AFTER" ]; then
  echo '{"pass":false,"error":"judge/ changed during grade"}' >&2
  exit 1
fi

# timing goes under its own key so self-test determinism ignores it
if [ -n "$JSON_OUT" ]; then
  "$VENV/bin/python" -c "
import json,sys
v=json.load(open('$JSON_OUT'))
v['timing']={'wall_s': $((t1-t0))}
json.dump(v, open('$JSON_OUT','w'), indent=2)"
fi
