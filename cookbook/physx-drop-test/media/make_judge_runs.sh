#!/usr/bin/env bash
# make_judge_runs.sh — regenerate every raw judge output the media is built
# from, into media/judge_runs/ (gitignored; regenerated, never hand-edited).
#
# Nothing is drawn that the judge did not produce: each file below is the
# stdout verdict JSON of judge/grade.sh, or the trajectory that
# judge/simulate.py wrote, or judge/mutants.py's own description index.
#
#   judge_runs/verdicts/good.json              grade.sh examples/good/scene.usda
#   judge_runs/mutants/<name>.json             grade.sh on each mutant scene
#   judge_runs/mutants/mutants/mutants.json    mutants.py descriptions
#   judge_runs/traces/good/traj.npz            simulate.py per-step y / vy
#   judge_runs/traces/good/meta.json           simulate.py run metadata
#   judge_runs/selftest.log                    one timed bash judge/selftest.sh
#   judge_runs/selftest.time                   its measured wall seconds
#   judge_runs/paths/*.txt                     sha256 of each input trace
#
# Usage: bash media/make_judge_runs.sh [--seed N]   (default seed 42)
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
REPO="$(cd "$DEMO/../.." && pwd)"
RUNS="$MEDIA/judge_runs"
SIM_PY="$DEMO/judge/simulate.py"
PHYSX_PY="${PHYSX_DROP_TEST_VENV:-$HOME/.venvs/physx-drop-test}/bin/python"

# The demo lives at cookbook/<name>/ and clones to <repo>/cookbook/<name>/;
# allow being run from either the repo root or the demo dir.
if [[ ! -f "$SIM_PY" ]]; then
    echo "[judge_runs] ERROR: judge/simulate.py not found at $SIM_PY" >&2
    exit 1
fi
if [[ ! -x "$PHYSX_PY" ]]; then
    echo "[judge_runs] ERROR: venv python not found at $PHYSX_PY — run judge/setup.sh first" >&2
    exit 1
fi

cd "$DEMO"   # grade.sh resolves the scene path relative to the caller
mkdir -p "$RUNS"

log() { echo "[judge_runs] $*"; }

# 1. the known-good verdict (all 7 gates pass, seed 42) -----------------------
log "grading examples/good/scene.usda --seed $SEED"
if ! bash judge/grade.sh examples/good/scene.usda --seed "$SEED" \
        --json "$RUNS/verdicts/good.json"; then
    echo "[judge_runs] ERROR: the known-good scene did not pass every gate" >&2
    exit 1
fi
log "wrote $RUNS/verdicts/good.json"

# 2. every mutant verdict (each must fail at least one gate) -------------------
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
    echo "[judge_runs] ERROR: mutant(s) survived the judge: ${SURVIVED[*]}" >&2
    exit 1
fi
log "graded $(ls "$MUTDIR"/*.json | wc -l) mutants, all killed"

# 3. the good trajectory (the raw samples the figures plot) -------------------
#    simulate.py is invoked exactly as grade.sh invokes it, so the npz holds
#    the same 2400 steps the gates above judged.
log "simulating examples/good/scene.usda for the per-step trace"
WORK="$(mktemp -d /tmp/physx-media.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT
cp examples/good/scene.usda "$WORK/scene.usda"
WARP_CACHE="${WARP_CACHE_PATH:-$HOME/.cache/physx-drop-test/warp}"
mkdir -p "$WARP_CACHE"
WARP_CACHE_PATH="$WARP_CACHE" "$PHYSX_PY" -I "$SIM_PY" \
    "$WORK/scene.usda" "$WORK/sim"
mkdir -p "$RUNS/traces/good"
cp "$WORK/sim/traj.npz" "$RUNS/traces/good/traj.npz"
cp "$WORK/sim/meta.json" "$RUNS/traces/good/meta.json"
log "wrote $RUNS/traces/good/{traj.npz,meta.json}"

# 4. one timed self-test run: the terminal capture the video scrolls and the
#    measured wall time its "Nx speed" label is computed from.  A fresh
#    sandbox run of the same command appears verbatim in RECEIPT.md.
log "running bash judge/selftest.sh, timed, for the terminal capture"
SELFTEST_START="$(date +%s.%N)"
bash judge/selftest.sh > "$RUNS/selftest.log" 2>&1
SELFTEST_RC=$?
SELFTEST_END="$(date +%s.%N)"
if [[ $SELFTEST_RC -ne 0 ]]; then
    echo "[judge_runs] ERROR: judge/selftest.sh failed (exit $SELFTEST_RC)" >&2
    tail -20 "$RUNS/selftest.log" >&2
    exit 1
fi
python3 -c "import sys; print(round(float(sys.argv[1]) - float(sys.argv[2]), 3))" \
    "$SELFTEST_END" "$SELFTEST_START" > "$RUNS/selftest.time"
log "wrote $RUNS/selftest.log and selftest.time ($(cat "$RUNS/selftest.time") s)"

# 5. record where every file came from (sha256 of the sources, plus the exact
#    commands) so make_figures.py can prove the figures were regenerated from
#    these runs and nothing else.
mkdir -p "$RUNS/paths"
sha256sum "$RUNS/verdicts/good.json" "$RUNS/traces/good/traj.npz" \
    "$RUNS/traces/good/meta.json" "$RUNS/selftest.log" \
    > "$RUNS/paths/sha256.txt"
cat > "$RUNS/paths/commands.txt" <<EOF
seed $SEED
judge/grade.sh examples/good/scene.usda --seed $SEED --json judge_runs/verdicts/good.json
judge/mutants.py examples/good/scene.usda judge_runs/mutants/mutants
judge/grade.sh <mutant>/scene.usda --seed $SEED --json judge_runs/mutants/<name>.json   (for each mutant)
judge/simulate.py examples/good/scene.usda <out>     (as grade.sh calls it, WARP_CACHE_PATH=$WARP_CACHE)
bash judge/selftest.sh                               (timed, -> judge_runs/selftest.log + selftest.time)
EOF
log "wrote $RUNS/paths/{sha256.txt,commands.txt}"

log "done: $(find "$RUNS" -type f | wc -l) files under judge_runs/"
