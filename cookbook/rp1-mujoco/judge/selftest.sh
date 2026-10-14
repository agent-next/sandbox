#!/usr/bin/env bash
# cookbook/rp1-mujoco self-test: prove the judge can fail.
#
# 1. the known-good example must pass every gate
# 2. every single-edit mutant of it must fail at least one gate
#    (zero_torque must specifically fail the stand gate -- the physics oracle)
# 3. determinism: same seed -> identical verdict JSON (except timing)
# 4. prints the kill rate; exits non-zero if it is below 90 %
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GOOD="${HERE}/../examples/good/controller.py"
MUTDIR="$(mktemp -d)/mutants"
LOGDIR="$(mktemp -d)"
trap 'rm -rf "${LOGDIR}"' EXIT

fail_banner() { echo "selftest: FAIL: $*" >&2; }

# --- 1. known-good must pass -------------------------------------------
if ! bash "$HERE/grade.sh" "$GOOD" --json "$LOGDIR/good.json" >"$LOGDIR/good.log" 2>&1; then
    fail_banner "known-good example FAILED the judge:"
    cat "$LOGDIR/good.log" >&2
    exit 1
fi
echo "selftest: known-good PASS"

# --- 2. every mutant must fail -----------------------------------------
python3 "$HERE/mutants.py" --list >/dev/null
python3 "$HERE/mutants.py" "$GOOD" "$MUTDIR" >/dev/null

nmut=0
killed=0
phys_killed=0
for m in "$MUTDIR"/controller_*.py; do
    name="$(basename "$m" .py)"
    nmut=$((nmut + 1))
    if bash "$HERE/grade.sh" "$m" --json "$LOGDIR/${name}.json" >"$LOGDIR/${name}.log" 2>&1; then
        fail_banner "mutant ESCAPED: ${name} (judge passed on a bad artifact)"
        killed=$((killed + 0))
    elif [ ! -f "$LOGDIR/${name}.json" ]; then
        echo "selftest: mutant KILLED: ${name} (no verdict: artifact crashed or was rejected)"
        killed=$((killed + 1))
    else
        # which gates fired?  physics gates count separately
        gates=$(python3 - "$LOGDIR/${name}.json" <<'PY'
import json, sys
v = json.load(open(sys.argv[1]))
failed = [g for g, d in v["gates"].items() if d["verdict"] == "fail"]
print(" ".join(failed))
PY
)
        case " $gates " in
            *" stand "*|*" push "*|*" limits "*) phys_killed=$((phys_killed + 1)) ;;
        esac
        echo "selftest: mutant KILLED: ${name} (failed: ${gates})"
        killed=$((killed + 1))
    fi
done

rate=0
phys_rate=0
if [ "$nmut" -gt 0 ]; then
    rate=$((100 * killed / nmut))
    phys_rate=$((100 * phys_killed / nmut))
fi
echo "selftest: kill rate ${killed}/${nmut} (${rate}%), physics kills ${phys_killed}/${nmut} (${phys_rate}%)"

if [ "$nmut" -lt 5 ]; then
    fail_banner "need >= 5 known-bad examples; only $nmut generated"
    exit 1
fi
if [ "$rate" -lt 90 ]; then
    fail_banner "kill rate ${rate}% < 90%"
    exit 1
fi
if [ "$phys_rate" -lt 90 ]; then
    fail_banner "physics kill rate ${phys_rate}% < 90%"
    exit 1
fi

# zero_torque is the physics oracle: no torque at all must topple the robot
zt_gates=$(python3 - "$LOGDIR/controller_zero_torque.json" <<'PY'
import json, sys
v = json.load(open(sys.argv[1]))
print(" ".join(g for g, d in v["gates"].items() if d["verdict"] == "fail"))
PY
)
case " $zt_gates " in
    *" stand "*) echo "selftest: zero-torque oracle fails the stand gate (as it must)" ;;
    *) fail_banner "zero_torque mutant did not fail the stand gate: ${zt_gates}"
       exit 1 ;;
esac

# --- 3. determinism: same seed -> identical verdict (except timing) -----
bash "$HERE/grade.sh" "$GOOD" --json "$LOGDIR/good2.json" >/dev/null 2>&1
for f in good good2; do
    python3 - "$LOGDIR/$f.json" <<'PY'
import json, sys
v = json.load(open(sys.argv[1]))
v.pop("timing", None)
json.dump(v, open(sys.argv[1] + ".strip", "w"), indent=1, sort_keys=True)
PY
done
if ! cmp -s "$LOGDIR/good.json.strip" "$LOGDIR/good2.json.strip"; then
    fail_banner "verdict JSON differs between two runs with the same seed"
    diff "$LOGDIR/good.json.strip" "$LOGDIR/good2.json.strip" >&2 || true
    exit 1
fi
echo "selftest: determinism OK (same seed -> identical verdict)"

echo "selftest: PASS"
