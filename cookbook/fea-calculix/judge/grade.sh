#!/bin/bash
# grade.sh <artifact> [--seed N] [--json out.json]
# <artifact>: directory containing design.json + beam.inp (or path to design.json)
set -euo pipefail
exec python3 "$(dirname "${BASH_SOURCE[0]}")/judge.py" "$@"
