#!/usr/bin/env bash
# grade.sh <artifact> [--seed N] [--json out.json]
# <artifact>: a directory holding pipeline.sh, or the pipeline.sh itself.
# Runs every gate in judge/vtp_judge.py, prints one JSON verdict and exits 0
# only if all gates pass.
set -euo pipefail
exec python3 -I "$(dirname "${BASH_SOURCE[0]}")/vtp_judge.py" "$@"
