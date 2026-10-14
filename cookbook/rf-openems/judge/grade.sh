#!/usr/bin/env bash
# grade.sh <artifact> [--json out.json]
# Thin wrapper: activates the pinned MEEP env and runs judge/grade.py.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_DIR="${ENV_DIR:-$HOME/.rf-openems/env}"
MM_BIN="$HOME/.rf-openems/micromamba"

if [ ! -x "$ENV_DIR/bin/python" ]; then
    echo "judge env missing; run judge/setup.sh first" >&2
    exit 2
fi

# never run the artifact from its own directory with plain "python" — run it
# under -I from a scratch dir with the real interpreter, in the pinned env.
exec "$MM_BIN" run -p "$ENV_DIR" python "$HERE/grade.py" "$@"
