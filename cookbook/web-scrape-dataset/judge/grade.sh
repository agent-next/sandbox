#!/usr/bin/env bash
# Grade one web-scrape-dataset artifact.
#
#   bash judge/grade.sh <artifact.py> [--seed N] [--json out.json] [--timeout S]
#
# Runs every gate, prints one JSON verdict, exits 0 only if all gates pass.
# The oracle is judge/fixture.py's closed-form ground truth; the robots gate is
# measured from the judge's own HTTP request log, not from the artifact's CSV.
#
# The judge is copied to a temp dir before the artifact runs, so nothing the
# artifact does can modify the gates it is being judged by (grade.py also
# checksums judge/ before and after as gate 10).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$HERE/.." && pwd)"

if [ $# -lt 1 ]; then
    sed -n '2,10p' "${BASH_SOURCE[0]}" >&2
    exit 2
fi

# ---- locate the pinned tools ----------------------------------------------
ROOT="${WSD_HOME:-$HOME/.web-scrape-dataset}"
PY="$ROOT/venv/bin/python"
if [ ! -x "$PY" ]; then
    echo "grade: pinned tools missing -- run 'bash judge/setup.sh' first" >&2
    exit 2
fi

# The browser tree may be the one setup.sh downloaded, or a pre-installed one
# (setup.sh records which). PLAYWRIGHT_BROWSERS_PATH must point at it.
BROWSERS="$ROOT/browsers"
if [ -f "$ROOT/VERSIONS.txt" ]; then
    recorded="$(sed -n 's/^browsers_path: //p' "$ROOT/VERSIONS.txt")"
    [ -n "$recorded" ] && BROWSERS="$recorded"
fi
export PLAYWRIGHT_BROWSERS_PATH="$BROWSERS"

# ---- run the judge in a throwaway copy ------------------------------------
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cp -r "$DEMO/judge" "$work/judge"

set +e
"$PY" "$work/judge/grade.py" "$@" --workdir "$work/run"
rc=$?
exit "$rc"
