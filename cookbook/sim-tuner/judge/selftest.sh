#!/usr/bin/env bash
# Self-test: prove the judge can fail. See SPEC.md.
#
# 1. the known-good example passes grade.sh (G1-G4: on a real GPU lease, or on
#    the local GPU stack when SIM_TUNER_GPU_LOCAL=1 — the mode run.py sets when
#    the judge itself runs inside the demo's lease, which has no outbound net).
#    The full verdict must say PASS with G4 green, not merely exit 0.
# 2. every scripted mutant is killed by a real CPU gate. Mutants are graded
#    --cpu-only: each one must exit 1 with a verdict that has an actual failing
#    gate among G1/G2/G3 (G1 structure/ranges, G2 train error or G3 held-out
#    error), so no mutant ever leases a GPU — only artifacts that pass every
#    CPU gate reach G4. An infrastructure error (exit 2, no verdict, or a
#    verdict with every gate green) is a self-test failure, never a "kill".
# 3. determinism: two grades of the good artifact with the same seed produce
#    byte-identical verdict JSON except the `timing` key;
# 4. judge/ checksums are compared before and after (inside grade.sh).
#
# Every grade is passed the same seed the mutants were generated with.
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

# one seed for mutant generation and every grade of this run
SEED="${SIM_TUNER_SEED:-7}"
export SIM_TUNER_SEED="$SEED"

echo "selftest: generating mutants (seed $SEED)"
MUT="$WORK/mutants"
"$PY" "$HERE/mutants.py" "$MUT" > "$WORK/names.txt"

# Read one verdict and print the verdict label plus its failing gate names.
# Exits non-zero (with a message on stderr) when the verdict is missing, not
# JSON, claims a full pass, or has no failing gate: none of those is a kill.
verdict_fail_gates() {
    "$PY" - "$1" <<'EOF'
import json, sys
try:
    v = json.load(open(sys.argv[1]))
except Exception as e:
    print(f"unreadable verdict: {e}", file=sys.stderr)
    sys.exit(2)
if not isinstance(v, dict):
    print("verdict is not an object", file=sys.stderr)
    sys.exit(2)
gates = v.get("gates") or {}
failed = [k for k, g in gates.items()
          if k in ("G1_ranges", "G2_train", "G3_heldout")
          and isinstance(g, dict) and g.get("pass") is False]
if not failed:
    print(f"no failing gate (verdict {v.get('verdict')!r})", file=sys.stderr)
    sys.exit(3)
if v.get("pass"):
    print(f"verdict claims pass while {failed} failed", file=sys.stderr)
    sys.exit(4)
print(",".join(failed))
EOF
}

echo "selftest: grading known-good (full judge, G1-G4)"
if bash "$HERE/grade.sh" "$GOOD" --seed "$SEED" --json "$WORK/good.json" \
        >"$WORK/good.log" 2>&1; then
    if "$PY" - "$WORK/good.json" <<'EOF'
import json, sys
v = json.load(open(sys.argv[1]))
g4 = (v.get("gates") or {}).get("G4_gpu_cpu_agree") or {}
ok = v.get("pass") is True and v.get("complete") is True \
     and (v.get("gates") or {}).get("G1_ranges", {}).get("pass") is True \
     and (v.get("gates") or {}).get("G3_heldout", {}).get("pass") is True \
     and g4.get("pass") is True
sys.exit(0 if ok else 1)
EOF
    then
        echo "selftest: known-good: PASS (G1-G4)"
    else
        echo "selftest: known-good exited 0 but its verdict is not a full PASS" >&2
        tail -40 "$WORK/good.json" >&2 || true
        exit 1
    fi
else
    echo "selftest: known-good FAILED (judge broken, lease stack mismatch, or the good example is broken)" >&2
    tail -40 "$WORK/good.log" >&2
    exit 1
fi

killed=0
total=0
fails=""
infra=""
while read -r name; do
    total=$((total + 1))
    # --cpu-only: mutants are killed by CPU gates; no GPU lease per mutant.
    set +e
    bash "$HERE/grade.sh" "$MUT/$name.json" --seed "$SEED" --cpu-only \
        --json "$WORK/$name.json" >"$WORK/$name.log" 2>&1
    rc=$?
    set -e
    if [ "$rc" -ne 1 ]; then
        # rc=0 survived, rc=2/anything else is an infrastructure error, not a kill
        infra="$infra $name(rc=$rc)"
        echo "selftest: mutant $name: NOT KILLED (grade exit code $rc; a kill is exit 1)" >&2
        continue
    fi
    if ! gate=$(verdict_fail_gates "$WORK/$name.json" 2>"$WORK/$name.reason"); then
        infra="$infra $name(no-failing-gate)"
        echo "selftest: mutant $name: NOT KILLED ($(cat "$WORK/$name.reason"))" >&2
        continue
    fi
    killed=$((killed + 1))
    echo "selftest: mutant $name: killed (gate: $gate)"
done < "$WORK/names.txt"

rate=$("$PY" -c "print(f'{$killed / $total * 100:.0f}')")
echo "selftest: kill rate: $killed/$total = ${rate}%"
if [ "$killed" -lt "$total" ]; then
    echo "selftest: NOT every mutant was killed:$infra$fails" >&2
    exit 1
fi

echo "selftest: determinism check (two CPU-path grades of the good artifact;"
echo "          the GPU engine agreement is compared against fixed tolerances)"
bash "$HERE/grade.sh" "$GOOD" --seed "$SEED" --cpu-only --json "$WORK/det1.json" >/dev/null 2>&1
bash "$HERE/grade.sh" "$GOOD" --seed "$SEED" --cpu-only --json "$WORK/det2.json" >/dev/null 2>&1
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

# every mutant killed is the rule; the 90 % floor is the standard's floor and
# is recorded, but a survivor fails the self-test even above it
[ "$rate" -ge 90 ] || { echo "selftest: kill rate below 90%" >&2; exit 1; }
echo "selftest: ok ($killed/$total mutants killed, seed $SEED)"
