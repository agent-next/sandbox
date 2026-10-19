#!/usr/bin/env bash
# grade.sh <artifact_dir> [--seed S] [--json out.json] [more grade.py flags]
set -euo pipefail
exec python3 "$(dirname "$0")/grade.py" "$@"
