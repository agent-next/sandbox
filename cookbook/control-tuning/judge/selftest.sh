#!/usr/bin/env bash
# Prove the judge can fail — including its Monte-Carlo robustness gate.
#
# The known-good example must pass; every known-bad mutant must fail at
# least one gate. Most mutants are killed by the deterministic gates and
# are graded with --no-mc for speed. The mc-marginal mutant passes every
# deterministic gate and is killed by the Monte-Carlo gate alone; it gets
# a dedicated section that also proves the Monte-Carlo gate can fail.
# Grading the good example twice with the same seed (full gates, both
# runs) must give byte-identical verdict JSON — the determinism check.
#
# Prints the kill rate; exits non-zero if any check fails or the kill rate
# is below 90 %.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DEMO="$(cd "$HERE/.." && pwd)"
PY="$HOME/ct-judge-venv/bin/python3"
if [ ! -x "$PY" ]; then
  echo "selftest: judge venv not found; run judge/setup.sh first" >&2
  exit 2
fi

GOOD="$DEMO/examples/good/controller.json"
BADDIR="$DEMO/examples/bad"

# regenerate mutants from the good example so the two cannot drift
"$PY" -I "$HERE/mutants.py" "$GOOD" "$BADDIR" >/dev/null

fail=0
echo "== good example (deterministic gates, --no-mc) =="
if bash "$HERE/grade.sh" "$GOOD" --no-mc >/dev/null 2>&1; then
  echo "PASS (expected pass): $GOOD"
else
  echo "FAIL (expected pass, judge rejected): $GOOD"
  bash "$HERE/grade.sh" "$GOOD" --no-mc >&2 || true
  fail=1
fi

echo "== known-bad mutants (deterministic gates, --no-mc) =="
total=0; killed=0
for art in "$BADDIR"/*.json; do
  total=$((total+1))
  name="$(basename "$art" .json)"
  if [ "$name" = "mc-marginal" ]; then
    # killed (or not) by the Monte-Carlo section below
    continue
  fi
  if bash "$HERE/grade.sh" "$art" --no-mc >/dev/null 2>&1; then
    echo "FAIL (expected reject, judge accepted): $name"
    fail=1
  else
    killed=$((killed+1))
    echo "PASS (expected reject): $name"
  fi
done

# --- good example, full gates, twice: MC gate passes + determinism ---
echo "== good example (full gates, graded twice with the same seed) =="
D1="$(mktemp)"; D2="$(mktemp)"
bash "$HERE/grade.sh" "$GOOD" --json "$D1" >/dev/null 2>&1
bash "$HERE/grade.sh" "$GOOD" --json "$D2" >/dev/null 2>&1
if "$PY" -I -c '
import json, sys
v = json.load(open(sys.argv[1]))
g = v["gates"]["mc_pass_fraction"]
sys.exit(0 if (v["passed"] and g["pass"]) else 1)
' "$D1"; then
  echo "PASS (expected pass): full grade of the good example, \
Monte-Carlo $("$PY" -I -c 'import json,sys; v=json.load(open(sys.argv[1])); print(f"{v[\"mc_pass\"]}/{v[\"mc_n\"]}")' "$D1")"
else
  echo "FAIL (expected pass): full grade rejected the good example" >&2
  fail=1
fi
if cmp -s "$D1" "$D2"; then
  echo "PASS: verdict JSON byte-identical across the two gradings (seed 20260101)"
else
  echo "FAIL: verdict JSON differs between two gradings with the same seed" >&2
  diff "$D1" "$D2" | head -20 >&2 || true
  fail=1
fi

# --- mc-marginal: passes every deterministic gate, killed by MC alone ---
echo "== mc-marginal mutant (killed by the Monte-Carlo gate alone) =="
if bash "$HERE/grade.sh" "$BADDIR/mc-marginal.json" --no-mc >/dev/null 2>&1; then
  echo "PASS (setup ok): mc-marginal passes every deterministic gate"
else
  echo "FAIL (unexpected): mc-marginal failed a deterministic gate, so the \
Monte-Carlo kill below would not isolate the MC gate" >&2
  fail=1
fi
MCJSON="$(mktemp)"
if bash "$HERE/grade.sh" "$BADDIR/mc-marginal.json" --json "$MCJSON" \
    >/dev/null 2>&1; then
  echo "FAIL (expected reject): full grade accepted mc-marginal" >&2
  fail=1
else
  if "$PY" -I -c '
import json, sys
v = json.load(open(sys.argv[1]))
mc = v["gates"]["mc_pass_fraction"]
others = all(g["pass"] for k, g in v["gates"].items()
             if k != "mc_pass_fraction")
sys.exit(0 if (not mc["pass"] and others) else 1)
' "$MCJSON"; then
    killed=$((killed+1))
    echo "PASS (expected reject): Monte-Carlo gate kills mc-marginal alone: \
$("$PY" -I -c 'import json,sys; v=json.load(open(sys.argv[1])); print(f"mc_pass_fraction {v[\"gates\"][\"mc_pass_fraction\"][\"value\"]:.3f} < 0.95 ({v[\"mc_pass\"]}/{v[\"mc_n\"]})")' "$MCJSON")"
  else
    echo "FAIL (expected a pure Monte-Carlo kill, another gate fired)" >&2
    fail=1
  fi
fi
rm -f "$D1" "$D2" "$MCJSON"

rate=$(( killed * 100 / total ))
echo "== kill rate: $killed/$total = ${rate}% =="
if [ "$rate" -lt 90 ]; then
  echo "selftest: kill rate below 90 %" >&2
  fail=1
fi
exit $fail
