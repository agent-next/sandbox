#!/usr/bin/env bash
# grade.sh <artifact.py> [--json out.json] [--seed N] [--skip-convergence]
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="${RF_OPENEMS_HOME:-$HOME/.rf-openems}"

if [ ! -f "$BASE/sysroot/.debs_done" ]; then
    echo "judge env missing; run judge/setup.sh first" >&2
    exit 2
fi
source "$HERE/env.sh"
exec "$RF_PY" "$HERE/grade.py" "$@"
