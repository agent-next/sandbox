#!/usr/bin/env bash
# judge/grade.sh — run every gate on one part artifact.
#
#   judge/grade.sh <part_dir> [--seed N] [--json out.json]
#
# <part_dir> must contain spec.txt, model.py and the DELIVERED model.step +
# model.stl (run `python3 model.py` with the pinned tool first — the judge
# grades the delivered files, then proves the tool regenerates them
# byte-for-byte).  Prints exactly one verdict JSON; exit 0 only if every
# gate passes.  The artifact runs in a scratch copy; judge/ is checksummed
# before and after (gate 10: judge_intact).

set -euo pipefail

ARTIFACT_DIR=""
JSON_OUT=""
SEED=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --json) JSON_OUT="$2"; shift 2 ;;
        --seed) SEED="$2"; shift 2 ;;
        -h|--help)
            sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *)      ARTIFACT_DIR="$1"; shift ;;
    esac
done

if [[ -z "$ARTIFACT_DIR" || ! -d "$ARTIFACT_DIR" ]]; then
    echo "Usage: $0 <part_dir> [--seed N] [--json out.json]" >&2
    exit 2
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ABS_ARTIFACT="$(cd "$ARTIFACT_DIR" && pwd)"

for f in spec.txt model.py model.step model.stl; do
    if [[ ! -f "$ABS_ARTIFACT/$f" ]]; then
        echo "[grade] ERROR: missing $f in $ARTIFACT_DIR" >&2
        echo "[grade]   (the judge grades DELIVERED files; build them with the" >&2
        echo "[grade]    pinned tool first:  ~/.venvs/aicad-judge/bin/python model.py)" >&2
        exit 2
    fi
done

if [[ ! -x "${AICAD_JUDGE_VENV:-$HOME/.venvs/aicad-judge}/bin/python" ]]; then
    echo "[grade] ERROR: judge venv missing — run bash judge/setup.sh first" >&2
    exit 2
fi

# scratch copy: the artifact (and the tool executing its model.py) can
# never touch the checked-in example or the judge itself
SCRATCH="$(mktemp -d /tmp/aicad-grade.XXXXXX)"
trap 'rm -rf "$SCRATCH"' EXIT
# the scratch copy keeps the artifact's dir name: check_gates.py reads the
# part identity (bushing / adapter_plate / bracket) from it
cp -r "$ABS_ARTIFACT" "$SCRATCH/$(basename "$ABS_ARTIFACT")"

VENV="${AICAD_JUDGE_VENV:-$HOME/.venvs/aicad-judge}"
GATE_PY="$VENV/bin/python"   # check_gates imports OCP/trimesh/manifold3d
if [[ -n "$JSON_OUT" ]]; then
    "$GATE_PY" "$SCRIPT_DIR/check_gates.py" "$SCRATCH/$(basename "$ABS_ARTIFACT")" \
        --seed "$SEED" --json "$JSON_OUT"
else
    "$GATE_PY" "$SCRIPT_DIR/check_gates.py" "$SCRATCH/$(basename "$ABS_ARTIFACT")" --seed "$SEED"
fi
