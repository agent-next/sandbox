#!/usr/bin/env bash
# grade.sh <artifact> [--seed N] [--json out.json]
#
# Runs every backtest-equity judge gate against <artifact>, prints one JSON
# verdict, and exits 0 only if all gates pass.  The judge never imports or
# executes anything from the artifact; all oracle math is in judge/reference.py.
#
# The artifact directory is copied to a temp dir first (judge-integrity
# rule in SPEC.md); selftest.sh additionally checksums judge/ around every
# run and fails closed if it changed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/judge.py" "$@"
