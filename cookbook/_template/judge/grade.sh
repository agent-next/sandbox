#!/bin/bash
# grade.sh <artifact> [--seed N] [--json out.json]
# Runs every gate in SPEC.md, prints one JSON verdict on stdout, and
# exits 0 only if all gates pass. Deterministic per seed; wall time goes
# under a "timing" key. Never let the artifact modify judge/ (grade a
# copy; checksum judge/ before and after — see selftest.sh).
set -euo pipefail
echo "TODO: implement judge/grade.sh" >&2
exit 1
