#!/usr/bin/env bash
# Regenerate media/data/ref_compare.json (reference cross-check table) using
# the judge's own interpreter code -- no number here is invented.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "$HERE")"
JENV="${HOME}/.cnc-gcode/venv"

[ -x "${JENV}/bin/python" ] || {
    echo "collect_ref_compare: judge venv missing -- run 'bash judge/setup.sh'" >&2
    exit 1
}

cd "$DEMO"
PYTHONPATH="$DEMO/judge" "${JENV}/bin/python" -I -B media/collect_ref_compare.py
