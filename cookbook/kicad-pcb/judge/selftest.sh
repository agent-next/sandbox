#!/usr/bin/env bash
# judge/selftest.sh — verify the judge itself.
#
#  1. checksum judge/ before and after (artifact must not modify judge)
#  2. known-good project passes, graded twice -> identical verdict JSON
#     (determinism; no volatile fields in the verdict)
#  3. every scripted mutant fails at least one gate; kill rate >= 90%
#
# Exit 0 iff all checks hold.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(dirname "$SCRIPT_DIR")"
GOOD_DIR="$DEMO_DIR/examples/good/555-blinker"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

judge_sum() {
    find "$SCRIPT_DIR" -type f \( -name '*.sh' -o -name '*.py' \) \
        | sort | xargs sha256sum
}

BEFORE=$(judge_sum)
SEED="${SEED:-42}"

echo "=== selftest: grade known-good (run 1, seed $SEED)"
bash "$SCRIPT_DIR/grade.sh" "$GOOD_DIR" --seed "$SEED" \
    --json "$WORK/good1.json" || {
    echo "FAIL: good project did not pass"; exit 1; }

echo "=== selftest: grade known-good (run 2, determinism)"
bash "$SCRIPT_DIR/grade.sh" "$GOOD_DIR" --seed "$SEED" \
    --json "$WORK/good2.json" || {
    echo "FAIL: good project did not pass on rerun"; exit 1; }
# Same seed twice -> identical verdict JSON except the timing key
# (DEMO-STANDARD.md, "Deterministic").
if python3 - "$WORK/good1.json" "$WORK/good2.json" <<'PY'
import json, sys
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
a.pop("timing", None); b.pop("timing", None)
sys.exit(0 if a == b else 1)
PY
then
    echo "    determinism: identical verdict JSON (excluding timing)"
else
    echo "FAIL: verdict JSON differs between identical runs"; exit 1
fi

echo "=== selftest: oracle unit tests"
(cd "$DEMO_DIR" && python3 -m unittest judge/test_oracle.py) || {
    echo "FAIL: oracle unit tests failed"; exit 1; }

echo "=== selftest: mutants"
# Fail closed: a generator crash or an empty mutant set is a selftest
# failure, never a kill.
python3 "$SCRIPT_DIR/mutants.py" "$GOOD_DIR" "$WORK/mutants" \
    || { echo "FAIL: mutant generation failed"; exit 1; }
shopt -s nullglob
mutdirs=("$WORK/mutants"/*/)
[[ ${#mutdirs[@]} -gt 0 ]] || { echo "FAIL: no mutants generated"; exit 1; }
EXPECTED=$(PYTHONPATH="$SCRIPT_DIR" \
    python3 -c 'import mutants; print(len(mutants.MUTANTS))')
[[ ${#mutdirs[@]} -eq $EXPECTED ]] || {
    echo "FAIL: expected $EXPECTED mutants, got ${#mutdirs[@]}"; exit 1; }

TOTAL=0
KILLED=0
INFRA=0
for mdir in "${mutdirs[@]}"; do
    name=$(basename "$mdir")
    TOTAL=$((TOTAL + 1))
    if bash "$SCRIPT_DIR/grade.sh" "$mdir" --json "$WORK/$name.json" \
            >"$WORK/$name.log" 2>&1; then
        echo "    $name: SURVIVED (bad)"; cat "$WORK/$name.log"
        continue
    fi
    # A kill needs a real failing verdict: a grade crash, missing JSON
    # or a verdict that shows no failed gate is a selftest failure.
    if failed=$(python3 - "$WORK/$name.json" <<'PY'
import json, sys
try:
    v = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
bad = [k for k, g in v.get("gates", {}).items() if not g["pass"]]
if v.get("overall_pass") is False and bad:
    print(" ".join(sorted(bad)))
else:
    sys.exit(1)
PY
    ); then
        echo "    $name: killed (failed: $failed)"
        KILLED=$((KILLED + 1))
    else
        echo "    $name: ERROR — non-zero exit but no valid failing verdict"
        cat "$WORK/$name.log"
        INFRA=$((INFRA + 1))
    fi
done

RATE=$((KILLED * 100 / TOTAL))
echo "=== selftest: kill rate $KILLED/$TOTAL = ${RATE}%"

AFTER=$(judge_sum)
[[ "$BEFORE" == "$AFTER" ]] || { echo "FAIL: judge/ changed during grading"; exit 1; }
echo "=== selftest: judge/ checksum unchanged"

if [[ $INFRA -gt 0 ]]; then
    echo "SELFTEST FAIL ($INFRA mutant(s) produced no valid failing verdict)"
    exit 1
fi
if [[ $RATE -ge 90 ]]; then
    echo "SELFTEST PASS"
    exit 0
fi
echo "SELFTEST FAIL (kill rate < 90%)"
exit 1
