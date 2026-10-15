#!/usr/bin/env bash
# media/regen_data.sh — regenerate every committed judge output under
# media/data/ with the judge as it exists in this tree:
#
#   selftest.log                     judge/selftest.sh output, verbatim
#                                    (the kill table make_loop.py parses)
#   <candidate>/verdict.json         full grade (all gates, seed 20260101)
#   <candidate>/{s1,s2}_trace.csv    deterministic-scenario traces
#   <candidate>/margins_{force,torque}.csv   margin-gate sweeps
#   <candidate>/mc_samples.csv       Monte-Carlo robustness samples
#   <name>_verdict.json              validation-error verdicts (gate 1)
#
# Every number the media shows comes from these files. Run from anywhere
# after judge/setup.sh. Nothing is edited: grade.sh grades against a
# checksummed copy of judge/ exactly as a submission would be graded.
set -euo pipefail

MEDIA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$MEDIA/.." && pwd)"
JUDGE="$DEMO/judge"
DATA="$MEDIA/data"
PY="$HOME/ct-judge-venv/bin/python3"
if [ ! -x "$PY" ]; then
  echo "regen_data: judge venv not found; run judge/setup.sh first" >&2
  exit 2
fi

die() { echo "regen_data: $*" >&2; exit 1; }

mkdir -p "$DATA"

# --- 1. the self-test, captured verbatim (this is a media input) --------
echo "== judge/selftest.sh (captured to media/data/selftest.log) =="
bash "$JUDGE/selftest.sh" 2>&1 | tee "$DATA/selftest.log"
[ "${PIPESTATUS[0]}" -eq 0 ] || die "selftest failed; not regenerating data"

# --- 2. replay candidates: full grade + traces --------------------------
# good must pass (exit 0); the mutants must be rejected (exit 1)
grade() {  # grade <artifact> <canddir-or-verdictpath> <expected-rc> <trace?>
  local art="$1" dest="$2" want_rc="$3" trace="$4" rc=0
  local j="$dest/verdict.json"
  if [ "$trace" = yes ]; then
    bash "$JUDGE/grade.sh" "$art" --json "$j" --trace "$dest" >/dev/null \
      || rc=$?
  else
    bash "$JUDGE/grade.sh" "$art" --json "$j" >/dev/null || rc=$?
  fi
  [ "$rc" -eq "$want_rc" ] \
    || die "$(basename "$art"): expected exit $want_rc, judge exited $rc"
}

for cand in good too-aggressive too-sluggish mc-marginal; do
  art="$DEMO/examples/good/controller.json"
  want=0
  if [ "$cand" != good ]; then
    art="$DEMO/examples/bad/$cand.json"
    want=1
  fi
  echo "== $cand: full grade, traces to media/data/$cand/ =="
  mkdir -p "$DATA/$cand"
  grade "$art" "$DATA/$cand" "$want" yes
done

# --- 3. validation-error verdicts (gate 1 rejections, no simulation) -----
for name in degenerate-r-force sign-flip wrong-type; do
  echo "== $name: validation verdict to media/data/${name}_verdict.json =="
  bash "$JUDGE/grade.sh" "$DEMO/examples/bad/$name.json" \
    --json "$DATA/${name}_verdict.json" >/dev/null || rc=$?
  [ "${rc:-0}" -eq 1 ] || die "$name: expected exit 1, got ${rc:-0}"
  rc=0
done

echo "== media/data regenerated =="
find "$DATA" -type f | sort | sed "s|$DATA|data|"
