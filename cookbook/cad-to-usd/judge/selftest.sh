#!/usr/bin/env bash
# judge/selftest.sh — prove the judge can fail.
#
#   1. known-good examples/good passes every gate;
#   2. every known-bad mutant from judge/mutants.py fails at least one gate
#      (kill rate must be >= 90 %);
#   3. determinism: two grades of the good artifact with the same --seed
#      give byte-identical verdict JSON, excluding the "timing" key.
#
# Mutant grades run with --no-reconvert (gate 6, the full re-conversion, is
# slow and only the good artifact is expected to have a working convert.sh
# anyway — the garbage_convert mutant is graded WITH gate 6 since that is
# exactly the gate meant to kill it).
#
# Exit 0 only if all three prove out.
#
# Usage: bash judge/selftest.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_BASE="${CAD2USD_VENV_BASE:-$HOME/.venvs}"
JUDGE_PY="$VENV_BASE/cad2usd-judge/bin/python"
GOOD="$DEMO_DIR/examples/good"

[[ -x "$JUDGE_PY" ]] || {
    echo "selftest: judge venv missing — run judge/setup.sh first" >&2; exit 1; }

SEED=42
WORK="$(mktemp -d "${TMPDIR:-/tmp}/cad2usd-selftest.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

failing_gates() {  # failing_gates <verdict.json> -> comma-separated gate names
    "$JUDGE_PY" -I -c '
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("no verdict (judge crashed)"); raise SystemExit
gates = d.get("gates", {})
bad = sorted(k for k, v in gates.items()
             if isinstance(v, dict) and v.get("passed") is False)
print(", ".join(bad) if bad else "(all gates passed)")
' "$1" 2>/dev/null || echo "no verdict file"
}

t0=$(date +%s)
echo "== selftest: known-good artifact =="
if bash "$SCRIPT_DIR/grade.sh" "$GOOD" --seed "$SEED" \
        --json "$WORK/good.json" >/dev/null; then
    echo "known-good: PASS (expected)"
else
    echo "known-good: FAIL (unexpected)" >&2
    bash "$SCRIPT_DIR/grade.sh" "$GOOD" --seed "$SEED" 2>&1 | tail -40
    exit 1
fi

echo "== selftest: generating known-bad mutants =="
"$JUDGE_PY" -I "$SCRIPT_DIR/mutants.py" "$GOOD" "$WORK/mutants"

total=0; killed=0
for d in "$WORK/mutants"/*/; do
    name=$(basename "$d")
    total=$((total + 1))
    # garbage_convert targets gate 6 specifically; grade it with the gate on.
    reconvert="--no-reconvert"
    [[ "$name" == "garbage_convert" ]] && reconvert=""
    if bash "$SCRIPT_DIR/grade.sh" "$d" --seed "$SEED" $reconvert \
            --json "$WORK/$name.json" >/dev/null 2>&1; then
        echo "mutant $name: PASS (unexpected)" >&2
    else
        killed=$((killed + 1))
        echo "mutant $name: FAIL (expected) -- killed by gate: $(failing_gates "$WORK/$name.json")"
    fi
done

kill_rate=$((100 * killed / total))
echo "== selftest summary =="
echo "known-good: passed"
echo "kill rate: $killed/$total ($kill_rate%)"
[[ $kill_rate -ge 90 ]] || { echo "kill rate below 90%" >&2; exit 1; }

echo "== selftest: determinism (grade twice with --seed $SEED) =="
bash "$SCRIPT_DIR/grade.sh" "$GOOD" --seed "$SEED" --json "$WORK/det1.json" >/dev/null
bash "$SCRIPT_DIR/grade.sh" "$GOOD" --seed "$SEED" --json "$WORK/det2.json" >/dev/null
if "$JUDGE_PY" -I -c '
import json, sys
def load(p):
    d = json.load(open(p)); d.pop("timing", None); return d
sys.exit(0 if load(sys.argv[1]) == load(sys.argv[2]) else 1)
' "$WORK/det1.json" "$WORK/det2.json"; then
    echo "determinism: PASS (two --seed $SEED runs identical excluding \"timing\")"
else
    echo "determinism: FAIL (two --seed $SEED runs differ beyond the timing key)" >&2
    exit 1
fi

echo "selftest: PASS ($(($(date +%s) - t0)) s)"
exit 0
