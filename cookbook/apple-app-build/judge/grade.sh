#!/usr/bin/env bash
# grade.sh <artifact> <ios-sim|ios|mac> [--json out.json]: one JSON verdict, exit 0 only on PASS.
set -euo pipefail
exec python3 "$(cd "$(dirname "$0")" && pwd)/apple_judge.py" "$@"
