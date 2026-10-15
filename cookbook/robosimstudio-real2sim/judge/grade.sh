#!/usr/bin/env bash
# Grade one params.json against the hidden reference. One JSON verdict on stdout;
# exit 0 only if all five gates pass.
#
#   judge/grade.sh examples/good/params.json [--seed N] [--json out.json]
#                  [--reference judge/reference] [--device cuda:0]
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$here/grade.py" "$@"
