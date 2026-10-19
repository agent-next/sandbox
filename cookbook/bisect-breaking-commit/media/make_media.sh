#!/usr/bin/env bash
# media/make_media.sh [RESULTS_DIR] — regenerate every media file from the
# real judge outputs, never by hand (DEMO-STANDARD.md "Media").
#
# RESULTS_DIR (default: <demo>/media/data) must hold the outputs of one
# fresh-sandbox run.py run:
#   sweep_report.json   the artifact run.py wrote (bars, speedup, culprit)
#   bisect_verdict.json the judge's verdict (gates, timing)
#   selftest.log        judge/selftest.sh output (kill rate, gates)
#   run.log             run.py output (per-step walls, per-commit receipts)
#
# Pinned Python deps in media/requirements.txt; ffmpeg (>= 4) from the
# system.  Writes result.png loop.png demo.mp4 MANIFEST.json plus a
# lossless master under media/master/ (git-ignored).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RESULTS="${1:-$SCRIPT_DIR/data}"
VENV="$SCRIPT_DIR/.venv"

for f in sweep_report.json bisect_verdict.json selftest.log run.log; do
    [[ -f "$RESULTS/$f" ]] || { echo "make_media.sh: $RESULTS/$f missing" >&2; exit 2; }
done

if [[ ! -x "$VENV/bin/python" ]]; then
    python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q --disable-pip-version-check -r "$SCRIPT_DIR/requirements.txt"

"$VENV/bin/python" "$SCRIPT_DIR/gen_media.py" --results "$RESULTS" --out "$SCRIPT_DIR"
echo "make_media.sh: wrote result.png loop.png demo.mp4 MANIFEST.json in $SCRIPT_DIR"
