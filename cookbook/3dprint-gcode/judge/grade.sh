#!/bin/bash
# grade.sh <artifact> [--seed N] [--json out.json]
# <artifact>: directory containing profile.ini + part.gcode
set -euo pipefail
exec python3 "$(dirname "${BASH_SOURCE[0]}")/judge.py" "$@"
