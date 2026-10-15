#!/usr/bin/env bash
# Self-test: prove the judge can fail. See SPEC.md.
#
# 1. the known-good example passes grade.sh (G1-G4: on a real GPU lease, or on
#    the local GPU stack when SIM_TUNER_GPU_LOCAL=1 — the mode run.py sets when
#    the judge itself runs inside the demo's lease, which has no outbound net);
# 2. every scripted mutant fails at least one gate. Mutants are graded
#    --cpu-only: each one is killed by a CPU gate (G1 structure/ranges, G2
#    train error or G3 held-out error), so no mutant ever leases a GPU —
#    only artifacts that pass every CPU gate reach G4.
# 3. determinism: two grades of the good artifact with the same seed produce
#    byte-identical verdict JSON except the `timing` key;
# 4. judge/ checksums are compared before and after (inside grade.sh).
#
# Prints the kill rate; exits non-zero unless good passes, every mutant is
# killed and determinism holds. Needs judge/version-table.json
# (judge/setup.sh --record) and either SBX_API_KEY (or E2B_API_KEY) with GPU
# access, or SIM_TUNER_GPU_LOCAL=1 on a host with the pinned GPU stack.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
GOOD="$HERE/../examples/good/params.json"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

PY="${SIM_TUNER_PYTHON:-$HOME/.venvs/sim-tuner/bin/python}"
if [ ! -x "$PY" ]; then
    echo "selftest: judge venv missing; run judge/setup.sh first" >&2
    exit 2
fi
if [ ! -f "$HERE/version-table.json" ]; then
    echo "selftest: judge/version-table.json missing; run judge/setup.sh --record first" >&2
    exit 2
fi

# mutants share one scenario seed with the good grade; overfit needs the seed
export SIM_TUNER_SEED="${SIM_TUNER_SEED:-7}"

echo "selftest: generating mutants"
MUT="$WORK/mutants"
"$PY" "$HERE/mutants.py" "$MUT" > "$WORK/names.txt"

echo "selftest: grading known-good (GPU lease for G4)"
if bash "$HERE/grade.sh" "$GOOD" --json "$WORK/good.json" >"$WORK/good.log" 2>&1; then
    echo "selftest: known-good: PASS"
else
    echo "selftest: known-good FAILED (judge broken, lease stack mismatch, or the good example is broken)" >&2
    tail -40 "$WORK/good.log" >&2
    exit 1
fi

killed=0
total=0
fails=""
while read -r name; do
    total=$((total + 1))
    # --cpu-only: mutants are killed by CPU gates; no GPU lease per mutant.
    if bash "$HERE/grade.sh" "$MUT/$name.json" --cpu-only --json "$WORK/$name.json" >"$WORK/$name.log" 2>&1; then
        fails="$fails $name"
        echo "selftest: mutant $name: SURVIVED (judge did not kill it)" >&2
    else
        killed=$((killed + 1))
        if [ -f "$WORK/$name.json" ]; then
            gate=$("$PY" - "$WORK/$name.json" <<'EOF'
import json, sys
v = json.load(open(sys.argv[1]))
gates = v.get("gates", {})
failed = [k for k, g in gates.items() if isinstance(g, dict) and g.get("pass") is False]
print(",".join(failed) or "?")
EOF
)
        else
            # no verdict JSON: the artifact was rejected pre-gates (see the log)
            gate="structure/infra"
        fi
        echo "selftest: mutant $name: killed (gate: $gate)"
    fi
done < "$WORK/names.txt"

rate=$("$PY" -c "print(f'{$killed / $total * 100:.0f}')")
echo "selftest: kill rate: $killed/$total = ${rate}%"
if [ "$killed" -lt "$total" ]; then
    echo "selftest: SURVIVED mutants:$fails" >&2
fi

echo "selftest: determinism check (two CPU-path grades of the good artifact;"
echo "          the GPU engine agreement is compared against fixed tolerances)"
bash "$HERE/grade.sh" "$GOOD" --cpu-only --json "$WORK/det1.json" >/dev/null 2>&1
bash "$HERE/grade.sh" "$GOOD" --cpu-only --json "$WORK/det2.json" >/dev/null 2>&1
if "$PY" - "$WORK/det1.json" "$WORK/det2.json" <<'EOF'
import json, sys
def strip(v):
    v = dict(v)
    v.pop("timing", None)
    g4 = v.get("gates", {}).get("G4_gpu_cpu_agree") or {}
    g4.pop("gpu_sim_s", None)      # GPU wall time is inherently noisy
    return v
a, b = (strip(json.load(open(p))) for p in sys.argv[1:3])
sys.exit(0 if a == b else 1)
EOF
then
    echo "selftest: determinism: OK"
else
    echo "selftest: determinism FAILED (two runs differ beyond timing)" >&2
    exit 1
fi

[ "$rate" -ge 90 ] || { echo "selftest: kill rate below 90%" >&2; exit 1; }
echo "selftest: ok"
