#!/usr/bin/env bash
#
# selftest.sh -- prove the judge can fail.
#
#   judge/grade.sh examples/good        must PASS
#   judge/grade.sh <each mutant>        must FAIL, at least one gate
#
# Prints the kill rate (mutants caught / mutants total) and exits non-zero if
# the known-good artifact does not pass, if two same-seed runs are not
# byte-identical apart from `timing`, or if the kill rate is under 90 %.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "${HERE}")"
WORK="$(mktemp -d /tmp/rl-self.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

# The same pinned interpreter grade.sh uses.
if [ -f "${HOME}/.rl-code-env-rollouts/env.sh" ]; then
    # shellcheck disable=SC1090
    . "${HOME}/.rl-code-env-rollouts/env.sh"
fi
PY="${RL_CODE_ENV_PY:-python3}"
if [ ! -x "$PY" ]; then
    PY="python3"
fi

echo "== selftest =========================================================="
echo "good artifact : ${DEMO}/examples/good"
echo "mutant source : ${HERE}/mutants.py (single-edit mutants)"
echo "python        : $("$PY" --version 2>&1)"
echo

# --------------------------------------------------------------------------
# 1. The known-good artifact must pass.
# --------------------------------------------------------------------------
echo "--- known-good -------------------------------------------------------"
bash "${HERE}/grade.sh" "${DEMO}/examples/good" \
    --seed 20261015 --json "${WORK}/good.json" > "${WORK}/good.log" 2>&1
GOOD_RC=$?
GOOD_GATES="$("$PY" -I -c '
import json,sys
try:
    d=json.load(open(sys.argv[1]))
except Exception:
    print("?/?"); sys.exit()
print("%d/%d" % (d.get("gates_passed",0), d.get("gates_total",0)))
' "${WORK}/good.json" 2>/dev/null || echo "?/?")"
GOOD_PASS="$("$PY" -I -c '
import json,sys
try:
    d=json.load(open(sys.argv[1]))
except Exception:
    print("no"); sys.exit()
print("yes" if d.get("pass") else "no")
' "${WORK}/good.json" 2>/dev/null || echo "no")"

if [ "$GOOD_RC" -eq 0 ] && [ "$GOOD_PASS" = "yes" ]; then
    echo "PASS  known-good artifact (${GOOD_GATES} gates)  exit=${GOOD_RC}"
else
    echo "FAIL  known-good artifact (${GOOD_GATES} gates)  exit=${GOOD_RC}"
    echo "      the judge must pass its own reference; aborting"
    sed -n '1,25p' "${WORK}/good.log" >&2
    exit 1
fi
echo

# --------------------------------------------------------------------------
# 2. Determinism: the same seed must give the same verdict.  Everything
#    allowed to differ lives under the `timing` key.
# --------------------------------------------------------------------------
echo "--- determinism ------------------------------------------------------"
bash "${HERE}/grade.sh" "${DEMO}/examples/good" \
    --seed 20261015 --json "${WORK}/det1.json" > /dev/null 2>&1
DET1_RC=$?
bash "${HERE}/grade.sh" "${DEMO}/examples/good" \
    --seed 20261015 --json "${WORK}/det2.json" > /dev/null 2>&1
DET2_RC=$?
DET_SAME="$("$PY" -I - "${WORK}/det1.json" "${WORK}/det2.json" <<'PYDET'
import json, sys
try:
    a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
except Exception:
    print("unreadable"); sys.exit(0)
a.pop("timing", None); b.pop("timing", None)
print("identical" if a == b else "DIFFERENT")
PYDET
)"
if [ "$DET1_RC" -eq 0 ] && [ "$DET2_RC" -eq 0 ] && [ "$DET_SAME" = "identical" ]; then
    echo "PASS  two same-seed runs give identical verdict JSON (minus timing)"
else
    echo "FAIL  determinism: exits ${DET1_RC}/${DET2_RC}, verdicts ${DET_SAME}"
    exit 1
fi
echo

# --------------------------------------------------------------------------
# 3. Every mutant must fail at least one gate.
# --------------------------------------------------------------------------
MUTDIR="${WORK}/mutants"
"$PY" -I "${HERE}/mutants.py" make-all "$MUTDIR" > /dev/null

NAMES=()
while IFS= read -r name; do NAMES+=("$name"); done < <(ls -1 "$MUTDIR" | sort)

echo "--- known-bad mutants -----------------------------------------------"
printf '%-22s %-5s %s\n' "MUTANT" "EXIT" "GATES FAILED"
KILLED=0
TOTAL=${#NAMES[@]}
for name in "${NAMES[@]}"; do
    OUT="${WORK}/${name}.json"
    bash "${HERE}/grade.sh" "${MUTDIR}/${name}" \
        --seed 20261015 --json "$OUT" > "${WORK}/${name}.log" 2>&1
    RC=$?
    FAILED="$("$PY" -I - "$OUT" <<'PYCLASS'
import json, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("<no verdict JSON>"); sys.exit(0)
bad = sorted(k for k, g in d.get("gates", {}).items() if g["verdict"] != "pass")
print("; ".join(bad) if bad else "NONE -- judge passed a broken artifact")
PYCLASS
)"
    if [ "$RC" -ne 0 ]; then
        KILLED=$((KILLED + 1))
        VERDICT=""
    else
        VERDICT=" SURVIVED"
    fi
    printf '%-22s %-5s %s%s\n' "$name" "$RC" "$FAILED" "$VERDICT"
done

echo
if [ "$TOTAL" -eq 0 ]; then
    echo "SELFTEST FAILED: no mutants were generated"
    exit 1
fi
KILL_RATE="$("$PY" -I -c "print(int(100*${KILLED}/${TOTAL} + 0.5))")"

echo "== summary ==========================================================="
echo "known-good      : PASS (${GOOD_GATES} gates)"
echo "mutants killed  : ${KILLED}/${TOTAL}"
echo "kill rate       : ${KILL_RATE} %"
echo

if [ "$KILL_RATE" -lt 90 ]; then
    echo "SELFTEST FAILED: kill rate ${KILL_RATE} % is below the 90 % floor"
    exit 1
fi

echo "SELFTEST PASSED: judge passes the good artifact and kills ${KILLED} mutants"
exit 0
