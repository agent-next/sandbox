#!/usr/bin/env bash
# Prove the judge can fail. The known-good example must pass; every known-bad
# mutant must fail at least one gate. Prints the kill rate; exits non-zero if
# the good example fails, any mutant passes, or the kill rate is below 90 %.
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
echo "== good example =="
if bash "$HERE/grade.sh" "$GOOD" --no-mc >/dev/null 2>&1; then
  echo "PASS (expected pass): $GOOD"
else
  echo "FAIL (expected pass, judge rejected): $GOOD"
  bash "$HERE/grade.sh" "$GOOD" --no-mc >&2 || true
  fail=1
fi

echo "== known-bad mutants =="
total=0; killed=0
for art in "$BADDIR"/*.json; do
  total=$((total+1))
  name="$(basename "$art" .json)"
  if bash "$HERE/grade.sh" "$art" --no-mc >/dev/null 2>&1; then
    echo "FAIL (expected reject, judge accepted): $name"
    fail=1
  else
    killed=$((killed+1))
    echo "PASS (expected reject): $name"
  fi
done

rate=$(( killed * 100 / total ))
echo "== kill rate: $killed/$total = ${rate}% =="
if [ "$rate" -lt 90 ]; then
  echo "selftest: kill rate below 90 %" >&2
  fail=1
fi
exit $fail
