#!/usr/bin/env bash
# judge/selftest.sh -- prove the judge can fail.
# Good artifact passes; each mutant fails at least one gate; kill rate >= 90%.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$HERE/.." && pwd)"
TOOLS_DIR="${TOOLS_DIR:-$HOME/tools/ovui-native-ui}"
VENV="$TOOLS_DIR/venv"
[ -x "$VENV/bin/python" ] || { echo "run judge/setup.sh first" >&2; exit 2; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
"$VENV/bin/python" -I "$HERE/mutants.py" "$DEMO/examples/good/panel.py" "$WORK"

# Known-good must pass, and run twice with the same seed to prove determinism
bash "$HERE/grade.sh" "$DEMO/examples/good/panel.py" --json "$WORK/good1.json" >/dev/null
bash "$HERE/grade.sh" "$DEMO/examples/good/panel.py" --json "$WORK/good2.json" >/dev/null
"$VENV/bin/python" -c "
import json,sys
a=json.load(open('$WORK/good1.json'));b=json.load(open('$WORK/good2.json'))
a.pop('timing',None);b.pop('timing',None)
assert a==b, 'good verdict not deterministic'"
echo "good: PASS (deterministic)"

# Known-bad mutants must each fail at least one gate
total=0; killed=0
for m in "$WORK"/mut_*.py; do
  total=$((total+1))
  if bash "$HERE/grade.sh" "$m" --json "$WORK/mut.json" >/dev/null 2>&1; then
    echo "MUTANT SURVIVED: $(basename "$m")"
  else
    failed_gate=$("$VENV/bin/python" -c "
import json
v=json.load(open('$WORK/mut.json'))
print(next((g['gate'] for g in v['gates'] if not g['ok']), 'unknown'))
" 2>/dev/null || echo run_error)
    echo "mutant $(basename "$m" .py): FAILS ($failed_gate)"
    killed=$((killed+1))
  fi
done
rate=$("$VENV/bin/python" -c "print(int(100*$killed/$total))")
echo "kill rate: $killed/$total = ${rate}%"
[ "$rate" -ge 90 ] || { echo "self-test FAILED: kill rate below 90%"; exit 1; }
echo "self-test OK"
