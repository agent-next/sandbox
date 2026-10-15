#!/bin/sh
# Self-test: prove the judge can fail. See SPEC.md.
#
# 1. the known-good bundle passes grade.sh;
# 2. every scripted mutant of it fails at least one gate;
# 3. grading is deterministic: two runs of the good artifact produce
#    byte-identical verdicts (the `timing` key is excluded);
# 4. the .py-artifact lane works: the judge supplies the problems file and
#    the model dir path through the environment it documents, and a .py
#    artifact graded from a copy can pass every gate;
# 5. judge/ checksums are unchanged after everything.
#
# Prints the kill rate; exits non-zero unless good passes, every mutant is
# killed, determinism holds and the kill rate is >= 90 %.

set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
GOOD="$HERE/../examples/good/bundle.json"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

echo "selftest: generating mutants"
MUT="$WORK/mutants"
python3 "$HERE/mutants.py" "$MUT" > "$WORK/names.txt"

echo "selftest: grading known-good"
if bash "$HERE/grade.sh" "$GOOD" --json "$WORK/good.json" >/dev/null 2>&1; then
    echo "selftest: known-good: PASS"
else
    echo "selftest: known-good FAILED (judge broken or good bundle broken)" >&2
    exit 1
fi

killed=0
total=0
fails=""
while read -r name; do
    [ -n "$name" ] || continue
    total=$((total + 1))
    if bash "$HERE/grade.sh" "$MUT/$name.json" \
         --json "$WORK/$name.json" >/dev/null 2>&1; then
        fails="$fails $name"
        echo "selftest: mutant $name: SURVIVED (judge did not kill it)" >&2
    else
        killed=$((killed + 1))
        gate=$(python3 - "$WORK/$name.json" <<'EOF'
import json, sys
v = json.load(open(sys.argv[1]))
gates = v.get("gates", {})
failed = [k for k, g in gates.items()
          if isinstance(g, dict) and not g.get("pass")]
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

echo "selftest: determinism check (two grades of the good bundle)"
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

[ "$rate" -ge 90 ] || { echo "selftest: kill rate below 90%" >&2; exit 1; }

echo "selftest: .py-artifact lane (judge supplies problems + model dir)"
cat > "$WORK/smoke_eval.py" <<'EOF'
"""Plumbing probe: the smallest artifact the judge's documented env supports.

Not a model run — it proves the .py lane only: grade.sh runs this file from
a copy in a fresh dir, hands it the pinned problems through
LLM_EVAL_PROBLEMS and a model directory through LLM_EVAL_MODEL_DIR, and
grades the bundle it writes like any other artifact.
"""
import hashlib
import json
import os

model_dir = os.environ.get("LLM_EVAL_MODEL_DIR")
problems = os.environ.get("LLM_EVAL_PROBLEMS")
assert model_dir and os.path.isdir(model_dir), \
    "judge did not supply LLM_EVAL_MODEL_DIR"
assert problems and os.path.isfile(problems), \
    "judge did not supply LLM_EVAL_PROBLEMS"

doc = json.load(open(problems))
gens = []
tokens = 0
for row in doc["problems"]:
    text = (f"Step 1: add {row['i']} and 1.\n"
            f"Step 2: the result is the answer.\n"
            f"Final answer: {row['gold']}")
    tokens += len(text.split())
    gens.append({"i": row["i"], "question": row["question"],
                 "generation": text, "max_new_tokens": 32})
wall = tokens / 5.0                      # a plausible CPU rate, by construction
correct = sum(1 for g, r in zip(gens, doc["problems"])
              if str(r["gold"]) in g["generation"])
bundle = {
    "model": "smoke", "problems_sha256": hashlib.sha256(
        open(problems, "rb").read()).hexdigest(),
    "n_problems": len(gens), "batch_size": 8, "max_new_tokens": 64,
    "temperature": 0.0, "greedy": True,
    "device": os.environ.get("LLM_EVAL_DEVICE", "cpu"),
    "generated_tokens": tokens, "wall_time_s": round(wall, 3),
    "throughput_tok_s": round(tokens / wall, 3),
    "reported_accuracy": round(correct / len(gens), 6),
    "generations": gens,
}
json.dump(bundle, open("bundle.json", "w"), indent=1, sort_keys=True)
EOF
mkdir -p "$WORK/model"
if LLM_EVAL_MODEL_DIR="$WORK/model" bash "$HERE/grade.sh" "$WORK/smoke_eval.py" \
        --device cpu --json "$WORK/smoke.json" >/dev/null 2>&1; then
    echo "selftest: .py artifact lane: PASS"
else
    echo "selftest: .py artifact lane FAILED (judge no longer supplies the env eval.py documents)" >&2
    python3 - "$WORK/smoke.json" <<'EOF' >&2 || true
import json, sys
try:
    v = json.load(open(sys.argv[1]))
except Exception as exc:
    print(f"selftest: no verdict JSON ({exc})", file=sys.stderr)
    raise SystemExit(0)
for name, g in v.get("gates", {}).items():
    if isinstance(g, dict) and not g.get("pass"):
        print(f"selftest:   gate {name}: {g.get('problems')}", file=sys.stderr)
EOF
    exit 1
fi

echo "selftest: ok"
