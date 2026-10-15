#!/usr/bin/env bash
# judge/selftest.sh -- prove the judge can fail.
#
# The known-good artifact passes, and its verdict is byte-identical across
# two runs with the same seed (excluding the timing key). Every known-bad
# mutant must fail at least one judge gate: the kill rate counts only
# mutants that reached the gates and failed one. A mutant that merely
# crashes the build (the run dies before the verdict, e.g. "render 1
# failed") proves nothing about the judge, so it is reported separately
# and does not count as a kill. Prints the kill rate and exits non-zero
# if it is below 90%.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$HERE/.." && pwd)"
TOOLS_DIR="${TOOLS_DIR:-$HOME/tools/ovui-native-ui}"
VENV="$TOOLS_DIR/venv"
[ -x "$VENV/bin/python" ] || { echo "run judge/setup.sh first" >&2; exit 2; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
"$VENV/bin/python" -I "$HERE/mutants.py" "$DEMO/examples/good/panel.py" "$WORK"

# -- known-good must pass, and be deterministic across two graded runs ----
bash "$HERE/grade.sh" "$DEMO/examples/good/panel.py" --json "$WORK/good1.json" >/dev/null
bash "$HERE/grade.sh" "$DEMO/examples/good/panel.py" --json "$WORK/good2.json" >/dev/null
"$VENV/bin/python" -I -c "
import json, sys
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
a.pop('timing', None); b.pop('timing', None)
assert a == b, 'known-good verdict is not deterministic across runs'
assert a['pass'], 'known-good did not pass'
" "$WORK/good1.json" "$WORK/good2.json"
echo "good: PASS (verdict byte-identical across 2 runs)"

# -- every mutant must fail at least one judge gate -----------------------
# rm the verdict file first: a stale verdict from the previous mutant would
# misattribute a build crash to its gates.
total=0; killed=0
for m in "$WORK"/mut_*.py; do
  total=$((total+1))
  name="$(basename "$m" .py)"
  rm -f "$WORK/mut.json"
  if bash "$HERE/grade.sh" "$m" --json "$WORK/mut.json" >/dev/null 2>&1; then
    echo "MUTANT SURVIVED: $name"
  else
    failed_gate="$("$VENV/bin/python" -I -c "
import json, sys
try:
    v = json.load(open(sys.argv[1]))
except Exception:
    print('run_error'); raise SystemExit
gates = v.get('gates', [])
if not gates:
    # the run died before the gates (render error): not a judge kill
    print('NO GATES REACHED: ' + v.get('error', 'unknown'))
    raise SystemExit
bad = [g['gate'] for g in gates if not g['ok']]
print(','.join(bad) if bad else v.get('error', 'unknown'))
" "$WORK/mut.json" 2>/dev/null || echo run_error)"
    case "$failed_gate" in
      "NO GATES REACHED:"*)
        echo "mutant ${name#mut_}: RUN ERROR, no gate reached ($failed_gate) -- not counted as a kill"
        ;;
      *)
        echo "mutant ${name#mut_}: FAILS ($failed_gate)"
        killed=$((killed+1))
        ;;
    esac
  fi
done

rate=$("$VENV/bin/python" -I -c "print(int(100*$killed/$total))")
echo "kill rate: $killed/$total = ${rate}% (counting only mutants a judge gate failed)"
[ "$rate" -ge 90 ] || { echo "self-test FAILED: kill rate below 90%"; exit 1; }
if [ "$killed" -lt "$total" ]; then
  echo "self-test FAILED: $((total-killed)) mutant(s) died before the gates"
  exit 1
fi
echo "self-test OK"
