#!/usr/bin/env bash
# cookbook/cnc-gcode self-test: prove the judge can fail.
#
# 1. the known-good example passes every gate
# 2. every single-edit mutant of it is killed by at least one NAMED gate
#    (a crash, parse error or timeout without a failing gate is not a kill
#    and fails the self-test outright)
# 3. determinism: same seed -> identical verdict JSON (except timing)
# 4. prints the kill rate; exits non-zero if kill rate < 90 %
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GOOD="${HERE}/../examples/good/cam.py"
MUTDIR="$(mktemp -d)/mutants"
LOGDIR="$(mktemp -d)"

# --- 1. known-good must pass -------------------------------------------
if ! bash "$HERE/grade.sh" "$GOOD" --json "$LOGDIR/good.json" >"$LOGDIR/good.log" 2>&1; then
    echo "selftest: known-good example FAILED the judge:" >&2
    cat "$LOGDIR/good.log" >&2
    exit 1
fi
echo "selftest: known-good PASS"

# --- 2. every mutant must fail -----------------------------------------
python3 "$HERE/mutate.py" "$GOOD" "$MUTDIR"

nmut=0
killed=0
unnamed=0
for m in "$MUTDIR"/*.py; do
    name="$(basename "$m" .py)"
    nmut=$((nmut + 1))
    if bash "$HERE/grade.sh" "$m" --json "$LOGDIR/${name}.json" >"$LOGDIR/${name}.log" 2>&1; then
        echo "selftest: mutant ESCAPED: $name (judge passed on a bad artifact)" >&2
    else
        # name the gates that caught it; a kill only counts when a named gate
        # failed -- a crash, parse error or timeout with no verdict gate is
        # NOT a kill of the judge's making and fails the self-test outright.
        caught="$(python3 - "$LOGDIR/${name}.json" <<'EOF'
import json, sys
try:
    v = json.load(open(sys.argv[1]))
    failed = [n for n, g in v.get("gates", {}).items() if not g.get("pass")]
    print(", ".join(failed) if failed else "no gate flagged")
except Exception:
    print("(no verdict JSON)")
EOF
)"
        if [ "$caught" = "no gate flagged" ] || [ "$caught" = "(no verdict JSON)" ]; then
            echo "selftest: mutant $name was rejected with NO named gate " \
                 "(crash/parse error/timeout is not a kill):" >&2
            tail -5 "$LOGDIR/${name}.log" >&2
            unnamed=$((unnamed + 1))
        else
            echo "selftest: mutant KILLED: $name  (caught by: $caught)"
            killed=$((killed + 1))
        fi
    fi
done

if [ "$unnamed" -gt 0 ]; then
    echo "selftest: $unnamed mutant(s) rejected without a named gate" >&2
    exit 1
fi

rate=0
if [ "$nmut" -gt 0 ]; then
    rate=$(awk -v k="$killed" -v n="$nmut" 'BEGIN{printf "%.0f", 100*k/n}')
fi
echo "selftest: kill rate ${killed}/${nmut} (${rate}%)"

if [ "$nmut" -lt 5 ]; then
    echo "selftest: need >= 5 known-bad examples; only $nmut present" >&2
    exit 1
fi
if [ "$rate" -lt 90 ]; then
    echo "selftest: kill rate ${rate}% < 90%" >&2
    exit 1
fi

# --- 3. determinism: same seed -> identical verdict (except timing) -----
SEED=999999
bash "$HERE/grade.sh" "$GOOD" --seed "$SEED" --json "$LOGDIR/det1.json" >"$LOGDIR/det1.log" 2>&1
bash "$HERE/grade.sh" "$GOOD" --seed "$SEED" --json "$LOGDIR/det2.json" >"$LOGDIR/det2.log" 2>&1

python3 - "$LOGDIR/det1.json" "$LOGDIR/det2.json" <<'EOF' || exit 1
import json, sys
with open(sys.argv[1]) as f:
    v1 = json.load(f)
with open(sys.argv[2]) as f:
    v2 = json.load(f)
v1.pop("timing", None)
v2.pop("timing", None)
if v1 != v2:
    print("selftest: determinism FAILED: verdicts differ for same seed", file=sys.stderr)
    sys.exit(1)
print("selftest: determinism PASS (same seed -> identical verdict)")
EOF

echo "selftest: PASS"
