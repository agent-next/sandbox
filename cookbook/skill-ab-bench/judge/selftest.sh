#!/usr/bin/env bash
# skill-ab-bench self-test: prove the judge can fail.
#
#   1. the known-good record passes every gate
#   2. every scripted mutant fails at least one gate -- and, where the mutant
#      names a gate, fails *that* gate (a mutant that dies at the wrong gate
#      means the gate under test is not doing its job)
#   3. kill rate >= 90 %, else exit non-zero
#   4. the statistics engine matches published values (judge/tests/test_stats.py)
#   5. same seed twice -> byte-identical verdict JSON except `timing`
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$JDIR/.." && pwd)"
GOOD="$DEMO/examples/good"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# --- 0. the statistics engine is right before anything is graded ----------
echo "selftest: statistics engine"
python3 -I "$JDIR/tests/test_stats.py" || {
    echo "selftest: statistics engine FAILED its own tests" >&2
    exit 1
}

# --- 1. known-good --------------------------------------------------------
echo "selftest: grading known-good $GOOD"
if bash "$JDIR/grade.sh" "$GOOD" --json "$work/good.json" > "$work/good.out"; then
    echo "selftest: known-good PASSED all gates"
else
    echo "selftest: known-good FAILED -- the judge or the example is broken" >&2
    cat "$work/good.out" >&2
    exit 1
fi

# --- 2. mutants -----------------------------------------------------------
python3 -I "$JDIR/mutants.py" "$GOOD" "$work/mutants" > "$work/mutants.log"
cat "$work/mutants.log"

gate_of() {   # gate_of <verdict.json> -> failed gate name, or '?'
    python3 -I -c 'import json,sys;print(json.load(open(sys.argv[1])).get(
        "failed_gate") or "?")' "$1" 2>/dev/null || echo '?'
}

total=0
killed=0
for m in "$work"/mutants/records/*/; do
    name="$(basename "$m")"
    total=$((total + 1))
    if bash "$JDIR/grade.sh" "$m" --json "$work/$name.json" \
         > /dev/null 2>&1; then
        echo "selftest: SURVIVED  records/$name (judge let it pass!)"
        continue
    fi
    killed=$((killed + 1))
    gate="$(gate_of "$work/$name.json")"
    want="$(sed -n "s/.*records\/$name\/results.json  \[\([^]]*\)\].*/\1/p" \
            "$work/mutants.log" | head -1)"
    if [ -n "$want" ] && [ "$gate" != "$want" ]; then
        echo "selftest: WRONG GATE records/$name: died at $gate, wanted $want"
    else
        echo "selftest: killed    records/$name (gate: $gate)"
    fi
done

# Judge mutants: a mutated judge must fail closed on the *good* artifact.
for m in "$work"/mutants/judge/*/; do
    name="$(basename "$m")"
    total=$((total + 1))
    if bash "$JDIR/grade.sh" "$GOOD" --judge-dir "$m" \
         --json "$work/judge-$name.json" > /dev/null 2>&1; then
        echo "selftest: SURVIVED  judge/$name (mutated judge passed the good record!)"
        continue
    fi
    killed=$((killed + 1))
    gate="$(gate_of "$work/judge-$name.json")"
    want="$(sed -n "s/.*judge\/$name\/  \[\([^]]*\)\].*/\1/p" \
            "$work/mutants.log" | head -1)"
    if [ -n "$want" ] && [ "$gate" != "$want" ]; then
        echo "selftest: WRONG GATE judge/$name: died at $gate, wanted $want"
    else
        echo "selftest: killed    judge/$name (gate: $gate)"
    fi
done

rate="$(python3 -I -c "print(f'{$killed/$total:.0%}' if $total else 'n/a')")"
echo "selftest: kill rate $killed/$total = $rate"
if [ "$total" -lt 8 ]; then
    echo "selftest: fewer than 8 mutants" >&2
    exit 1
fi
if [ $((killed * 10)) -lt $((total * 9)) ]; then
    echo "selftest: kill rate below 90%" >&2
    exit 1
fi

# --- 4. determinism: same seed twice -> identical verdict JSON ------------
bash "$JDIR/grade.sh" "$GOOD" --seed 1 --json "$work/det1.json" > /dev/null
bash "$JDIR/grade.sh" "$GOOD" --seed 1 --json "$work/det2.json" > /dev/null
if ! python3 -I - "$work/det1.json" "$work/det2.json" <<'EOF'
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
a.pop("timing", None)
b.pop("timing", None)
sys.exit(0 if a == b else 1)
EOF
then
    echo "selftest: DETERMINISM FAILED (two --seed 1 runs differ)" >&2
    exit 1
fi
echo "selftest: determinism OK (two --seed 1 runs byte-identical)"

# A different seed must change the bootstrap bounds, or --seed is a lie.
bash "$JDIR/grade.sh" "$GOOD" --seed 7 --json "$work/seed7.json" > /dev/null
if cmp -s "$work/det1.json" "$work/seed7.json"; then
    echo "selftest: --seed has no effect on the verdict" >&2
    exit 1
fi
echo "selftest: --seed changes the bootstrap CI as expected"
echo "selftest: OK"
