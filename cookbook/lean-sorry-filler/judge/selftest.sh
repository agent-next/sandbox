#!/bin/sh
# Self-test: prove the judge can fail. See SPEC.md.
#
#   judge/selftest.sh [--json out.json]
#
# 1. the known-good example passes grade.sh;
# 2. every scripted mutant of it fails at least one gate;
# 3. grading is deterministic: two runs of the good artifact produce
#    byte-identical verdicts (the `timing` key is excluded — wall times
#    are inherently noisy);
# 4. judge/ checksums are unchanged after everything.
#
# Prints the kill rate; exits non-zero unless good passes, every mutant
# is killed, determinism holds, and judge/ is untouched. With --json,
# writes a machine-readable summary of the same facts.

set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
GOOD="$HERE/../examples/good/exercises"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

JSON_OUT=""
while [ $# -gt 0 ]; do
    case "$1" in
        --json) JSON_OUT=${2:?selftest.sh: --json needs a path}; shift 2 ;;
        *) echo "selftest.sh: unknown argument: $1" >&2; exit 2 ;;
    esac
done

judge_sum() {
    (cd "$HERE" && find . -type f | LC_ALL=C sort | xargs sha256sum | sha256sum)
}
SUM_BEFORE=$(judge_sum)

echo "selftest: generating mutants"
MUT="$WORK/mutants"
python3 "$HERE/mutants.py" "$MUT" > "$WORK/names.txt"

echo "selftest: grading known-good"
if bash "$HERE/grade.sh" "$GOOD" --json "$WORK/good.json" >/dev/null 2>&1; then
    echo "selftest: known-good: PASS"
    echo "good 1" >> "$WORK/results.tsv"
else
    echo "selftest: known-good FAILED (judge broken or good example broken)" >&2
    exit 1
fi

killed=0
total=0
fails=""
while read -r name; do
    total=$((total + 1))
    if bash "$HERE/grade.sh" "$MUT/$name" --json "$WORK/$name.json" >/dev/null 2>&1; then
        fails="$fails $name"
        echo "selftest: mutant $name: SURVIVED (judge did not kill it)" >&2
        echo "$name 0 ?" >> "$WORK/results.tsv"
    else
        killed=$((killed + 1))
        gate=$(python3 - "$WORK/$name.json" <<'EOF'
import json, sys
v = json.load(open(sys.argv[1]))
failed = [k for k, g in v.items()
          if isinstance(g, dict) and k not in ("timing",)
          and "pass" in g and not g["pass"]]
print(",".join(sorted(failed)) or "?")
EOF
)
        echo "selftest: mutant $name: killed (gate: $gate)"
        echo "$name 1 $gate" >> "$WORK/results.tsv"
    fi
done < "$WORK/names.txt"

rate=$(python3 -c "print(f'{$killed / $total * 100:.0f}')")
echo "selftest: kill rate: $killed/$total = ${rate}%"
if [ "$killed" -lt "$total" ]; then
    echo "selftest: SURVIVED mutants:$fails" >&2
fi

echo "selftest: determinism check (two grades of the good artifact)"
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
    DETERMINISM=1
else
    echo "selftest: determinism FAILED (two runs differ beyond timing)" >&2
    exit 1
fi

if [ "$(judge_sum)" != "$SUM_BEFORE" ]; then
    echo "selftest: judge/ checksums changed during the self-test" >&2
    exit 1
fi
echo "selftest: judge/ checksums unchanged"

[ "$rate" -ge 90 ] || { echo "selftest: kill rate below 90%" >&2; exit 1; }

if [ -n "$JSON_OUT" ]; then
    GOOD_JSON="$WORK/good.json" RESULTS="$WORK/results.tsv" \
        KILLED="$killed" TOTAL="$total" DET="$DETERMINISM" \
        python3 - "$JSON_OUT" <<'EOF'
import json, os, sys
out = {"good_pass": True,
       "kill_rate": f'{int(os.environ["KILLED"])}/{int(os.environ["TOTAL"])}',
       "determinism": os.environ["DET"] == "1",
       "mutants": {}}
for line in open(os.environ["RESULTS"]):
    name, killed, gates = line.rstrip("\n").split(" ", 2)
    if name == "good":
        continue
    out["mutants"][name] = {"killed": killed == "1",
                            "gates": gates.split(",")}
v = json.load(open(os.environ["GOOD_JSON"]))
out["good_verdict"] = {k: v[k] for k in
                       ("pass", "judge_intact", "structure", "build",
                        "axioms", "closure")}
with open(sys.argv[1], "w") as f:
    json.dump(out, f, indent=2, sort_keys=True)
    f.write("\n")
EOF
fi

echo "selftest: ok"
