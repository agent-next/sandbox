#!/bin/bash
# doc-extract-convert — prove the judge can fail.
#
#   judge/selftest.sh
#
# 1. the known-good artifact passes every gate;
# 2. every known-bad mutant (judge/mutants.py, single edits of the good
#    one) fails at least one gate;
# 3. one judge-guard mutant: the ink check deliberately weakened (a fixed
#    128 threshold that cannot see ink on the low-contrast pages) must
#    make the *good* artifact fail -- otherwise the grounding gate is not
#    really testing anything;
# 4. determinism: grading the good artifact twice at the same seed gives
#    byte-identical verdict JSON apart from the "timing" key.
#
# Prints the kill rate; exits non-zero if it is below 100% or the good
# artifact does not pass.

set -euo pipefail

# Keep judge/ free of byte-code caches: grade.sh checksums it, and a .pyc
# appearing mid-run would look like tampering.
export PYTHONDONTWRITEBYTECODE=1

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
demo="$(cd "$here/.." && pwd)"
good="$demo/examples/good"
bad="$demo/examples/bad"
work="$(mktemp -d /tmp/docselftest.XXXXXX)"
trap 'rm -rf "$work"' EXIT

# -- 0. build the mutants ---------------------------------------------------
python3 "$here/mutants.py" --src "$good" --out "$bad" >/dev/null

# -- 1. known-good must pass ------------------------------------------------
echo "[selftest] grading known-good artifact"
python3 "$here/check_gates.py" "$good" --json "$work/good.json" \
    --work "$work/case-good" >/dev/null
python3 - "$work/good.json" <<'PY'
import json, sys
v = json.load(open(sys.argv[1]))
if not v["all_gates_passed"]:
    for g in v["gates"]:
        if not g["passed"]:
            print("[selftest] FAIL: good artifact fails %s: %s"
                  % (g["gate"], g["detail"]), file=sys.stderr)
    sys.exit(1)
PY
echo "[selftest] known-good: all gates passed"

# -- 2. every mutant must fail ----------------------------------------------
mutants=($(ls "$bad"))
killed=0
for m in "${mutants[@]}"; do
    echo "[selftest] grading mutant $m"
    rc=0
    python3 "$here/check_gates.py" "$bad/$m" --json "$work/$m.json" \
        --work "$work/case-$m" >/dev/null || rc=$?
    if [ "$rc" -eq 0 ]; then
        echo "[selftest] FAIL: mutant $m PASSED the judge" >&2
    else
        killed=$((killed + 1))
        gates=$(python3 - "$work/$m.json" <<'PY'
import json, sys
v = json.load(open(sys.argv[1]))
print(",".join(g["gate"] for g in v["gates"] if not g["passed"]))
PY
)
        echo "[selftest] killed $m (failed: $gates)"
    fi
done

# -- 3. judge-guard: a weakened judge must fail the good artifact -----------
cat > "$work/weakened_check_gates.py" <<'PY'
# Judge-guard mutant: the ink threshold re-hardcoded to 128, which cannot
# see ink on the low-contrast pages (ink ~156 there).  If the grounding
# gate still passes with this, it was never really checking grounding.
import sys, os
src = open(sys.argv[1]).read()
old = """    hist = im.histogram()
    mode = max(range(len(hist)), key=lambda v: hist[v])
    return max(0, mode - 40)"""
new = """    return 128"""
assert src.count(old) == 1, "ink-threshold anchor not found"
open(sys.argv[2], "w").write(src.replace(old, new))
PY
cp "$here/check_gates.py" "$here/corrupt.py" "$here/fixtures.py" "$work/"
python3 "$work/weakened_check_gates.py" "$here/check_gates.py" \
    "$work/check_gates_weak.py"
judge_killed=0
rc=0
python3 "$work/check_gates_weak.py" "$good" --json "$work/weak.json" \
    --work "$work/case-weak" >/dev/null || rc=$?
# (the weakened judge copy imports corrupt/fixtures from next to itself,
# which is why the judge modules were copied into $work)
if [ "$rc" -eq 0 ]; then
    echo "[selftest] FAIL: judge-guard mutant (fixed ink threshold) accepted the good artifact" >&2
else
    judge_killed=1
    echo "[selftest] judge-guard: weakened ink check fails the good artifact (as it must)"
fi

# -- 4. determinism ---------------------------------------------------------
python3 "$here/check_gates.py" "$good" --json "$work/good2.json" \
    --work "$work/case-good2" >/dev/null
python3 - "$work/good.json" "$work/good2.json" <<'PY'
import json, sys
a = json.load(open(sys.argv[1]))
b = json.load(open(sys.argv[2]))
del a["timing"], b["timing"]
if a != b:
    print("[selftest] FAIL: verdict JSON differs between two runs at the same seed",
          file=sys.stderr)
    sys.exit(1)
PY
echo "[selftest] determinism: two runs at seed 42 identical (apart from timing)"

# -- kill rate --------------------------------------------------------------
n=${#mutants[@]}
rate=$((100 * killed / n))
echo "[selftest] kill rate: $killed/$n mutants killed ($rate%)"
if [ "$rate" -lt 90 ]; then
    echo "[selftest] FAIL: kill rate below 90%" >&2
    exit 1
fi
if [ "$judge_killed" -ne 1 ]; then
    exit 1
fi
echo "[selftest] OK"
exit 0
