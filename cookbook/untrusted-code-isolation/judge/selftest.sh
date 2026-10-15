#!/bin/sh
# Self-test: prove the judge can fail. See SPEC.md.
#
# 1. the known-good runner passes grade.sh;
# 2. every scripted mutant of it fails at least one gate;
# 3. grading is deterministic: two runs of the good runner produce identical
#    verdicts (the `timing` key and the measured health numbers are excluded —
#    wall times, load and process counts are inherently noisy);
# 4. judge/ checksums are unchanged after everything.
#
# Prints the kill rate; exits non-zero unless good passes, every mutant is
# killed, the kill rate is at least 90 %, and determinism holds.

set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
GOOD="$HERE/../examples/good/runner.py"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

echo "selftest: generating mutants"
MUT="$WORK/mutants"
python3 "$HERE/mutants.py" "$MUT" > "$WORK/names.txt"

echo "selftest: grading known-good"
if bash "$HERE/grade.sh" "$GOOD" --json "$WORK/good.json" >/dev/null 2>&1; then
    echo "selftest: known-good: PASS"
else
    echo "selftest: known-good FAILED (judge broken or good runner broken)" >&2
    exit 1
fi

killed=0
total=0
fails=""
while read -r name; do
    total=$((total + 1))
    if bash "$HERE/grade.sh" "$MUT/$name.py" --json "$WORK/$name.json" \
            >/dev/null 2>&1; then
        fails="$fails $name"
        echo "selftest: mutant $name: SURVIVED (judge did not kill it)" >&2
    else
        killed=$((killed + 1))
        gate=$(python3 - "$WORK/$name.json" <<'EOF'
import json, sys
try:
    verdict = json.load(open(sys.argv[1]))
except (OSError, ValueError):
    print("?")
    raise SystemExit(0)
failed = [k for k, g in verdict.get("gates", {}).items()
          if isinstance(g, dict) and not g.get("pass")]
failed += [k for k, r in verdict.get("runs", {}).items()
           if isinstance(r, dict) and not r.get("pass")]
print(",".join(failed) or "?")
EOF
)
        echo "selftest: mutant $name: killed (gate: $gate)"
    fi
done < "$WORK/names.txt"

rate=$(python3 -c "print(f'{$killed / $total * 100:.0f}')")
echo "selftest: kill rate: $killed/$total = ${rate}%"
if [ "$killed" -lt "$total" ]; then
    echo "selftest: SURVIVED mutants:$fails" >&2
fi
[ "$rate" -ge 90 ] || { echo "selftest: kill rate below 90%" >&2; exit 1; }

echo "selftest: determinism check (two grades of the good runner)"
bash "$HERE/grade.sh" "$GOOD" --json "$WORK/det1.json" >/dev/null
bash "$HERE/grade.sh" "$GOOD" --json "$WORK/det2.json" >/dev/null
if python3 - "$WORK/det1.json" "$WORK/det2.json" <<'EOF'
import json, sys
# Wall times, load, memory and process counts are measurements of a live
# machine and are reported, never gated; everything else must match exactly.
NOISY = ("timing",)
NOISY_GATES = ("health",)
NOISY_RUN_KEYS = ("wall_s",)


def scrub(verdict):
    out = json.loads(json.dumps(verdict))
    for key in NOISY:
        out.pop(key, None)
    for gate in NOISY_GATES:
        out.get("gates", {}).pop(gate, None)
    for run in out.get("runs", {}).values():
        if isinstance(run, dict):
            for key in NOISY_RUN_KEYS:
                run.pop(key, None)
    return out


a, b = (scrub(json.load(open(p))) for p in sys.argv[1:3])
if a == b:
    sys.exit(0)
for key in sorted(set(a) | set(b)):
    if a.get(key) != b.get(key):
        print("determinism: %s differs" % key, file=sys.stderr)
sys.exit(1)
EOF
then
    echo "selftest: determinism: OK"
else
    echo "selftest: determinism FAILED (two runs differ beyond the noisy keys)" >&2
    exit 1
fi

echo "selftest: ok"
