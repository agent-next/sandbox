#!/usr/bin/env bash
# terminal-task-bench self-test: prove the judge can fail.
#
#   1. the known-good agent passes every gate
#   2. every pristine (unrepaired) tree fails its own verifier      (G2)
#   3. the negative control scores exactly 0/10                     (G3)
#   4. every scripted single-edit mutant is killed on the task it targets
#      -- kill rate must be >= 90 %
#   5. two --seed 1 runs of grade.sh are byte-identical without `timing`
#   6. a second seed (--seed 7) still passes G1..G4 with the good agent
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$JDIR/.." && pwd)"
GOOD="$DEMO/examples/good"
TASKS="$(python3 -I -c "
import sys; sys.path.insert(0, '$JDIR')
from bench_judge import TASKS; print(','.join(TASKS))")"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

fail=0
note() { echo "selftest: $*"; }

# --- 1. known-good passes -------------------------------------------------
note "grading the known-good agent ($GOOD)"
if bash "$JDIR/grade.sh" "$GOOD" --json "$work/good.json" --quiet >/dev/null; then
    note "known-good PASSED every gate"
    solved="$(python3 -I -c "
import json; v=json.load(open('$work/good.json'))
print(v['gates']['G1_solve_count']['solved'])")"
    note "  solved $solved/10, negative control scored \
$(python3 -I -c "
import json; v=json.load(open('$work/good.json'))
print(v['gates']['G3_negative_control']['negctl_solved'])")/10"
else
    note "known-good FAILED -- the judge or the example is broken"
    cat "$work/good.json" >&2
    exit 1
fi

# --- 2. pristine trees fail ----------------------------------------------
note "G2: every pristine tree must fail its own verifier"
fx="$work/fixtures"
python3 -I "$DEMO/fixtures/make_fixtures.py" --seed 20261015 --out "$fx" \
    >/dev/null
pristine_bad=0
for t in ${TASKS//,/ }; do
    if bash "$DEMO/fixtures/$t/verify.sh" "$fx/$t/work" >/dev/null 2>&1; then
        note "  UNREPAIRED $t PASSED its verifier -- bench is worthless"
        pristine_bad=$((pristine_bad + 1))
    else
        note "  pristine $t fails, as it must"
    fi
done
if [ "$pristine_bad" -ne 0 ]; then
    note "G2 FAILED: $pristine_bad pristine tree(s) accepted"
    fail=1
else
    note "G2 OK: all 10 pristine trees rejected"
fi

# --- 3. negative control scores 0/10 -------------------------------------
neg="$(python3 -I -c "
import json; v=json.load(open('$work/good.json'))
print(v['gates']['G3_negative_control']['negctl_solved'])")"
if [ "$neg" -eq 0 ]; then
    note "G3 OK: the negative control (runs \`true\` only) scored 0/10"
else
    note "G3 FAILED: the negative control scored $neg/10"
    fail=1
fi

# --- 4. mutants -----------------------------------------------------------
note "building single-edit mutants of the known-good agent"
python3 -I "$JDIR/mutants.py" "$GOOD" "$work/mutants" > "$work/mutants.log"
cat "$work/mutants.log"

total=0
killed=0
for m in "$work"/mutants/*/; do
    name="$(basename "$m")"
    task="$(python3 -I -c "
import json,sys
for line in open('$work/mutants.log'):
    if line.startswith('mutants: $name '):
        print(line.split('(')[1].split(')')[0]); break")"
    total=$((total + 1))
    if bash "$JDIR/grade.sh" "$m" --tasks "$task" --json "$work/$name.json" \
            --quiet >/dev/null 2>&1; then
        note "  SURVIVED  $name (task $task still passed -- judge let it by)"
    else
        detail="$(python3 -I -c "
import json
try:
    v = json.load(open('$work/$name.json'))
    row = next(r for r in v['tasks'] if r['task'] == '$task')
    print(f\"gate {v.get('failed_gate')}, verify exit {row['verify_exit']}, \"
          f\"pristine exit {row['pristine_verify_exit']}\")
except Exception as exc:
    print(f'? ({exc})')" 2>/dev/null || echo '?')"
        note "  killed    $name (task $task: $detail)"
        killed=$((killed + 1))
    fi
done

rate="$(python3 -I -c "print(f'{$killed/$total:.0%}' if $total else 'n/a')")"
note "kill rate $killed/$total = $rate"
if [ "$total" -lt 5 ]; then
    note "fewer than 5 mutants -- not enough to show the judge can fail"
    fail=1
fi
if [ $((killed * 10)) -lt $((total * 9)) ]; then
    note "kill rate below 90%"
    fail=1
fi

# --- 5. determinism -------------------------------------------------------
note "determinism: two --seed 1 runs must agree byte for byte"
bash "$JDIR/grade.sh" "$GOOD" --seed 1 --strip --json "$work/det1.json" \
    --quiet >/dev/null
bash "$JDIR/grade.sh" "$GOOD" --seed 1 --strip --json "$work/det2.json" \
    --quiet >/dev/null
if cmp -s "$work/det1.json" "$work/det2.json"; then
    note "determinism OK (two --seed 1 runs byte-identical, timing stripped)"
else
    note "DETERMINISM FAILED: grade.sh --seed 1 differs between runs"
    diff "$work/det1.json" "$work/det2.json" >&2 || true
    fail=1
fi

# --- 6. a second seed -----------------------------------------------------
note "second seed: the verifiers must not be tuned to one fixture instance"
if bash "$JDIR/grade.sh" "$GOOD" --seed 7 --json "$work/seed7.json" \
        --quiet >/dev/null; then
    note "seed 7 OK: known-good still passes every gate"
else
    note "seed 7 FAILED: the known-good agent does not pass a second seed"
    cat "$work/seed7.json" >&2
    fail=1
fi

if [ "$fail" -ne 0 ]; then
    note "FAILED"
    exit 1
fi
note "OK"
