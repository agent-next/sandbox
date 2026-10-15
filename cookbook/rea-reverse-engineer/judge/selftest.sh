#!/usr/bin/env bash
#
# selftest.sh -- prove the judge can fail.
#
#   judge/grade.sh examples/good      must PASS
#   two same-seed grades              must be byte-identical minus `timing`
#   judge/grade.sh <each mutant>      must FAIL, at least one gate
#
# Prints the kill rate; exits non-zero if the good artifact fails, if the
# runs are not deterministic, or the kill rate is under 90 %.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "${HERE}")"
WORK="$(mktemp -d /tmp/rea-self.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT
PY="${PYTHON:-python3}"
SEED=20261014

echo "== selftest =========================================================="
echo "good artifact : ${DEMO}/examples/good"
echo "mutant source : ${HERE}/mutants.py (single-edit mutants)"
echo

echo "--- known-good -------------------------------------------------------"
bash "${HERE}/grade.sh" "${DEMO}/examples/good" \
    --seed "$SEED" --json "${WORK}/good.json" > "${WORK}/good.log" 2>&1
GOOD_RC=$?
GOOD_GATES="$("$PY" -I - "${WORK}/good.json" <<'PYG' 2>/dev/null || echo "?/?"
import json, sys
d = json.load(open(sys.argv[1]))
print("%d/%d" % (d["gates_passed"], d["gates_total"]))
PYG
)"
if [ "$GOOD_RC" -eq 0 ]; then
    echo "PASS  known-good artifact (${GOOD_GATES} gates)  exit=${GOOD_RC}"
else
    echo "FAIL  known-good artifact (${GOOD_GATES} gates)  exit=${GOOD_RC}"
    echo "      the judge must pass its own reference; aborting"
    tail -30 "${WORK}/good.log" >&2
    exit 1
fi
echo

echo "--- determinism ------------------------------------------------------"
bash "${HERE}/grade.sh" "${DEMO}/examples/good" \
    --seed "$SEED" --json "${WORK}/det1.json" > /dev/null 2>&1
DET1_RC=$?
bash "${HERE}/grade.sh" "${DEMO}/examples/good" \
    --seed "$SEED" --json "${WORK}/det2.json" > /dev/null 2>&1
DET2_RC=$?
DET_SAME="$("$PY" -I - "${WORK}/det1.json" "${WORK}/det2.json" <<'PYD'
import json, sys
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
a.pop("timing", None); b.pop("timing", None)
print("identical" if a == b else "DIFFERENT")
PYD
)"
if [ "$DET1_RC" -eq 0 ] && [ "$DET2_RC" -eq 0 ] && [ "$DET_SAME" = "identical" ]; then
    echo "PASS  two same-seed runs give identical verdict JSON (minus timing)"
else
    echo "FAIL  determinism: exits ${DET1_RC}/${DET2_RC}, verdicts ${DET_SAME}"
    exit 1
fi
echo

MUTDIR="${WORK}/mutants"
"$PY" -I "${HERE}/mutants.py" make-all "$MUTDIR" > /dev/null

echo "--- known-bad mutants -----------------------------------------------"
printf '%-22s %-5s %s\n' "MUTANT" "EXIT" "GATES FAILED"
KILLED=0; TOTAL=0
for name in $(ls -1 "$MUTDIR" | sort); do
    TOTAL=$((TOTAL + 1))
    OUT="${WORK}/${name}.json"
    bash "${HERE}/grade.sh" "${MUTDIR}/${name}" \
        --seed "$SEED" --json "$OUT" > "${WORK}/${name}.log" 2>&1
    RC=$?
    FAILED="$("$PY" -I - "$OUT" <<'PYC' 2>/dev/null || echo "<no verdict>"
import json, sys
d = json.load(open(sys.argv[1]))
bad = sorted(k for k, v in d.get("gates", {}).items()
             if v["verdict"] != "pass")
print(",".join(bad) if bad else "NONE -- judge passed a broken artifact")
PYC
)"
    if [ "$RC" -ne 0 ]; then
        KILLED=$((KILLED + 1))
    fi
    printf '%-22s %-5s %s\n' "$name" "$RC" "$FAILED"
done

echo
KILL_RATE="$("$PY" -I -c "print(int(100*${KILLED}/${TOTAL} + 0.5))")"
echo "== summary ==========================================================="
echo "known-good     : PASS (${GOOD_GATES} gates)"
echo "mutants killed : ${KILLED}/${TOTAL}"
echo "kill rate      : ${KILL_RATE} %"
echo
if [ "$KILL_RATE" -lt 90 ]; then
    echo "SELFTEST FAILED: kill rate ${KILL_RATE} % is below the 90 % floor"
    exit 1
fi
echo "SELFTEST PASSED: judge passes the good artifact and kills ${KILLED} mutants"
exit 0
