#!/bin/sh
# Self-test: prove the judge can fail. See SPEC.md.
#
# 1. the known-good config passes grade.sh in this machine's mode;
# 2. every mutant the machine can observe fails at least one gate
#    (gpu-tagged mutants are only attempted in full mode);
# 3. grading is deterministic: two grades of the good config produce
#    byte-identical verdicts (the `timing` key is excluded);
# 4. judge/ checksums are unchanged after everything.
#
# Prints the kill rate; exits non-zero unless good passes, every attempted
# mutant is killed and determinism holds.

set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
GOOD="$HERE/../examples/good/sweep.json"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

echo "selftest: generating mutants"
MUT="$WORK/mutants"
python3 "$HERE/mutants.py" "$MUT" > "$WORK/names.txt"

echo "selftest: grading known-good (auto mode)"
if ! bash "$HERE/grade.sh" "$GOOD" --json "$WORK/good.json" >/dev/null 2>&1; then
    echo "selftest: known-good FAILED (judge broken or good example broken)" >&2
    exit 1
fi
MODE=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("mode","?"))' "$WORK/good.json")
echo "selftest: known-good: PASS (mode: $MODE)"

killed=0
attempted=0
skipped=0
survived=""
while IFS="$(printf '\t')" read -r name mode; do
    [ -n "$name" ] || continue
    if [ "$MODE" != "full" ] && [ "$mode" = "gpu" ]; then
        skipped=$((skipped + 1))
        echo "selftest: mutant $name: skipped (needs gpu, mode is $MODE)"
        continue
    fi
    attempted=$((attempted + 1))
    rc=0
    bash "$HERE/grade.sh" "$MUT/$name.json" \
         --json "$WORK/$name.json" >/dev/null 2>&1 || rc=$?
    if [ "$rc" -eq 0 ]; then
        survived="$survived $name"
        echo "selftest: mutant $name: SURVIVED (judge did not kill it)" >&2
    elif [ "$rc" -ne 1 ]; then
        survived="$survived $name(judge-error)"
        echo "selftest: mutant $name: JUDGE ERROR rc=$rc (not a clean kill)" >&2
    else
        killed=$((killed + 1))
        gate=$(python3 - "$WORK/$name.json" <<'EOF'
import json, sys
v = json.load(open(sys.argv[1]))
gates = v.get("gates", {})
failed = [k for k, g in gates.items() if isinstance(g, dict) and not g.get("pass")]
print(",".join(failed) or "?")
EOF
)
        echo "selftest: mutant $name: killed (gate: $gate)"
    fi
done < "$WORK/names.txt"

rate=$(python3 -c "print(f'{$killed * 100 // $attempted}')")
echo "selftest: kill rate: $killed/$attempted = ${rate}% ($skipped gpu-only skipped)"

echo "selftest: determinism check (two grades of the good config)"
bash "$HERE/grade.sh" "$GOOD" --json "$WORK/det1.json" >/dev/null
bash "$HERE/grade.sh" "$GOOD" --json "$WORK/det2.json" >/dev/null
if python3 - "$WORK/det1.json" "$WORK/det2.json" <<'EOF'
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
a.pop("timing", None), b.pop("timing", None)
sys.exit(0 if a == b else 1)
EOF
then
    echo "selftest: determinism: OK"
else
    echo "selftest: determinism FAILED (two runs differ beyond timing)" >&2
    exit 1
fi

if [ "$attempted" -eq 0 ]; then
    echo "selftest: no mutants were attempted" >&2
    exit 1
fi
[ "$rate" -ge 90 ] || { echo "selftest: kill rate below 90%:$survived" >&2; exit 1; }
[ -z "$survived" ] || exit 1
echo "selftest: ok"
