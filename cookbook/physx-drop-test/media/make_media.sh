#!/usr/bin/env bash
# make_media.sh -- regenerate every raw judge output the media is built from,
#                 into media/judge_runs/ (gitignored; regenerated, never hand-edited).

# Usage: bash media/make_media.sh [--seed N]   (default seed 42)
# Exit codes: 0 ok, 1 a judge step failed.

set -euo pipefail

SEED=42
while [[ $# -gt 0 ]]; do
    case "$1" in
        --seed) SEED="$2"; shift 2 ;;
        *) echo "usage: $0 [--seed N]" >&2; exit 2 ;;
    esac
done

MEDIA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$MEDIA/.." && pwd)"
RUNS="$MEDIA/judge_runs"

log() { echo "[make_media] $*"; }

# --- toolchain venv -------------------------------------------------------
VENV="${PHYSX_DROP_TEST_VENV:-$HOME/.venvs/physx-drop-test}"
PY="$VENV/bin/python"
if [[ ! -x "$PY" ]]; then
    log "ERROR: venv python not found at $PY — run judge/setup.sh first"
    exit 1
fi

# --- judge outputs ---------------------------------------------------------
# 1. the known-good verdict (all 6 gates pass, seed 42)
log "grading examples/good/scene.usda --seed $SEED"
if ! bash judge/grade.sh examples/good/scene.usda --seed "$SEED" \
        --json "$RUNS/verdicts/good.json"; then
    log "[make_media] ERROR: known-good scene did not pass every gate"
    exit 1
fi
log "wrote $RUNS/verdicts/good.json"

# 2. every mutant verdict (each must fail at least one gate)
log "generating and grading the known-bad mutants"
MUTDIR="$RUNS/mutants"
rm -rf "$MUTDIR"
mkdir -p "$MUTDIR"
python3 judge/mutants.py examples/good/scene.usda "$MUTDIR/mutants" >/dev/null
SURVIVED=()
for d in "$MUTDIR"/mutants/*/; do
    name="$(basename "$d")"
    if bash judge/grade.sh "$d/scene.usda" --seed "$SEED" \
         --json "$MUTDIR/$name.json" >/dev/null 2>&1; then
        SURVIVED+=("$name")
    fi
done
if (( ${#SURVIVED[@]} > 0 )); then
    log "[make_media] ERROR: mutant(s) survived: ${SURVIVED[*]}"
    exit 1
fi
log "graded $(ls "$MUTDIR"/*.json | wc -l) mutants, all killed"

# 3. the good trajectory (the raw samples the figures plot)
log "simulating examples/good/scene.usda for the per-step trace"
WORK="$(mktemp -d /tmp/physx-media.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT
cp examples/good/scene.usda "$WORK/scene.usda"
WARP_CACHE="${WARP_CACHE_PATH:-$HOME/.cache/physx-drop-test/warp}"
mkdir -p "$WARP_CACHE"
WARP_CACHE_PATH="$WARP_CACHE" \
"$PY" -I judge/simulate.py \
    "$WORK/scene.usda" "$WORK/sim"
mkdir -p "$RUNS/traces/good"
cp "$WORK/sim/traj.npz" "$RUNS/traces/good/traj.npz"
cp "$WORK/sim/meta.json" "$RUNS/traces/good/meta.json"
log "wrote $RUNS/traces/good/{traj.npz,meta.json}"

# 4. record where every file came from (sha256 of the sources, plus the exact
#    commands) so make_figures.py can prove the figures were regenerated from
#    these runs and nothing else.
mkdir -p "$RUNS/paths"
sha256sum "$RUNS/verdicts/good.json" "$RUNS/traces/good/traj.npz" \
    "$RUNS/traces/good/meta.json" > "$RUNS/paths/sha256.txt"
cat > "$RUNS/paths/commands.txt" <<EOF
seed $SEED
judge/grade.sh examples/good/scene.usda --seed $SEED --json judge_runs/verdicts/good.json
judge/mutants.py examples/good/scene.usda judge_runs/mutants/mutants
judge/grade.sh <mutant>/scene.usda --seed $SEED --json judge_runs/mutants/<name>.json   (for each mutant)
judge/simulate.py examples/good/scene.usda <out>     (as grade.sh calls it, WARP_CACHE_PATH=$WARP_CACHE)
EOF
log "wrote $RUNS/paths/{sha256.txt,commands.txt}"

# --- media artifacts -------------------------------------------------------
# 5. figures (result.png, loop.png) from judge_runs output
log "regenerating figures"
python3 "$MEDIA/make_figures.py"

# 6. video (demo.mp4) from judge_runs output
log "regenerating video"
python3 "$MEDIA/make_video.py"

log "done: $(find "$RUNS" -type f | wc -l) files under judge_runs/"
log "media rebuilt: result.png loop.png demo.mp4"