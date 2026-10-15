#!/usr/bin/env bash
# judge/grade.sh <artifact.py> [--seed N] [--json out.json]
#
# Runs every gate for the ovui-native-ui demo; prints one JSON verdict and
# exits 0 only if all gates pass. The artifact is copied to a scratch dir
# and rendered twice (fresh process each time) by judge/render.py; the
# judge tree is checksummed before and after so the artifact cannot modify
# it.
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
    -h|--help) grep '^#' "$0" | head -4; exit 0;;
    *) ARTIFACT="$1"; shift;;
  esac
done
[ -n "$ARTIFACT" ] || { echo "usage: grade.sh <artifact.py> [--seed N] [--json out.json]" >&2; exit 2; }
[ -f "$ARTIFACT" ] || { echo "no such artifact: $ARTIFACT" >&2; exit 2; }
[ -x "$VENV/bin/python" ] || { echo "run judge/setup.sh first" >&2; exit 2; }

SCRATCH="$(mktemp -d)"
trap 'rm -rf "$SCRATCH"' EXIT
cp "$ARTIFACT" "$SCRATCH/panel.py"

judge_checksum() {
  (cd "$HERE" && find . -type f ! -name '*.pyc' -print0 | sort -z | xargs -0 sha256sum)
}
JUDGE_BEFORE="$(judge_checksum)"

# A grade that dies before the gates still writes its verdict to --json: a
# missing file would let a caller read a previous run's stale verdict.
error_verdict() {
  python3 -c '
import json, sys
kind, log_path = sys.argv[1], sys.argv[2]
v = {"pass": False, "error": kind}
try:
    v["log"] = open(log_path).read()[-2000:]
except OSError:
    pass
print(json.dumps(v, indent=2, sort_keys=True))' "$1" "${2:-}"
}
write_verdict() {
  echo "$1" >&2
  if [ -n "$JSON_OUT" ]; then
    printf '%s\n' "$1" >"$JSON_OUT"
  fi
}

export OMNIUI_HEADLESS=1
export OMNIUI_LAVAPIPE=1
export OMNIUI_BACKEND=vulkan
export LD_LIBRARY_PATH="${STUB}:${LD_LIBRARY_PATH:-}"
# --seed is accepted for the standard's interface and recorded in the
# verdict's seed field. The render takes no random input: it is a fixed
# layout rasterised on a CPU device, so it is byte-identical for any seed.
export OVUI_SEED="$SEED"  # informational; ovui does not read it

# Render with the scratch dir as CWD: ovui/ImGui writes its window-state
# file (imgui.ini) into the CWD, which must not be the repo. RENDER_LIMIT is
# the per-render wall limit from SPEC.md gate 0.
RENDER_LIMIT=90
t0=$(date +%s)
(cd "$SCRATCH" && timeout "$RENDER_LIMIT" "$VENV/bin/python" -I "$HERE/render.py" \
    "$SCRATCH/panel.py" "$SCRATCH/shot1.png" "$SCRATCH/facts1.json") \
    >"$SCRATCH/render1.log" 2>&1 || {
        write_verdict "$(error_verdict "render 1 failed" "$SCRATCH/render1.log")"
        exit 1
    }
(cd "$SCRATCH" && timeout "$RENDER_LIMIT" "$VENV/bin/python" -I "$HERE/render.py" \
    "$SCRATCH/panel.py" "$SCRATCH/shot2.png" "$SCRATCH/facts2.json") \
    >"$SCRATCH/render2.log" 2>&1 || {
        write_verdict "$(error_verdict "render 2 failed" "$SCRATCH/render2.log")"
        exit 1
    }
t1=$(date +%s)

set +e
"$VENV/bin/python" -I "$HERE/check_gates.py" \
    "$SCRATCH/facts1.json" "$SCRATCH/shot1.png" \
    "$HERE/reference.json" \
    "$SCRATCH/facts2.json" "$SCRATCH/shot2.png" \
    ${JSON_OUT:+--json "$JSON_OUT"}
RC=$?
set -e

if [ "$JUDGE_BEFORE" != "$(judge_checksum)" ]; then
  echo '{"pass": false, "error": "judge/ changed during grade"}' >&2
  exit 1
fi

# timing lives under its own key so the determinism check can ignore it
if [ -n "$JSON_OUT" ] && [ -f "$JSON_OUT" ]; then
  "$VENV/bin/python" -I -c "
import json, sys
v = json.load(open(sys.argv[1]))
v['seed'] = int(sys.argv[3])
v['timing'] = {'render_wall_s': int(sys.argv[2])}
json.dump(v, open(sys.argv[1], 'w'), indent=2, sort_keys=True)" "$JSON_OUT" "$((t1 - t0))" "$SEED"
fi

exit "$RC"
