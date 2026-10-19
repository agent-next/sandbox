#!/usr/bin/env bash
# Grade a params.json artifact. See SPEC.md for the gates.
#
#   judge/grade.sh <params.json> [--seed N] [--json out.json] [--cpu-only]
#
# Exits 0 only if every gate passes; prints one JSON verdict on stdout.
# Delegates to judge/_grade.py, which regenerates the hidden scenario from
# the seed, re-simulates on CPU MuJoCo and (unless --cpu-only) re-scores the
# artifact on a fresh 4 GiB GPU slice lease for the G4 agreement check.
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PY="${SIM_TUNER_PYTHON:-$HOME/.venvs/sim-tuner/bin/python}"

if [ ! -x "$PY" ]; then
    echo "grade.sh: judge venv missing (tried $PY); run judge/setup.sh first" >&2
    exit 2
fi

exec "$PY" "$HERE/_grade.py" "$@"
