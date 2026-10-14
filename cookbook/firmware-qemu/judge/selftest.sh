#!/usr/bin/env bash
#
# selftest.sh -- prove the judge can fail.
#
#   judge/grade.sh examples/good            must PASS
#   judge/grade.sh <each mutant>            must FAIL, at least one gate
#
# Prints the kill rate (mutants caught / mutants total) and exits non-zero if
# the known-good artifact does not pass, or the kill rate is under 90 %.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "${HERE}")"
WORK="$(mktemp -d /tmp/fq-self.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

PY="${PYTHON:-python3}"

echo "== selftest =========================================================="
echo "good artifact : ${DEMO}/examples/good"
echo "mutant source : ${HERE}/mutants.py (single-edit mutants)"
echo

# --------------------------------------------------------------------------
# 1. The known-good artifact must pass.  A judge that fails its own reference
#    is not a judge.
# --------------------------------------------------------------------------
echo "--- known-good -------------------------------------------------------"
bash "${HERE}/grade.sh" "${DEMO}/examples/good" \
    --seed 20260814 --json "${WORK}/good.json" > "${WORK}/good.log" 2>&1
GOOD_RC=$?
GOOD_JSON="$(cat "${WORK}/good.json" 2>/dev/null)"

GOOD_PASSED="$(printf '%s' "$GOOD_JSON" | "$PY" -I -c \
    'import json,sys; d=json.load(sys.stdin); print("yes" if d.get("pass") else "no")' \
    2>/dev/null || echo "unreadable")"
GOOD_GATES="$(printf '%s' "$GOOD_JSON" | "$PY" -I -c \
    'import json,sys; d=json.load(sys.stdin); print("%d/%d" % (d["gates_passed"], d["gates_total"]))' \
    2>/dev/null || echo "?/?")"

if [ "$GOOD_RC" -eq 0 ] && [ "$GOOD_PASSED" = "yes" ]; then
    echo "PASS  known-good artifact (${GOOD_GATES} gates)  exit=${GOOD_RC}"
else
    echo "FAIL  known-good artifact (${GOOD_GATES} gates)  exit=${GOOD_RC}"
    echo "      the judge must pass its own reference; aborting"
    sed -n '1,30p' "${WORK}/good.log" >&2
    exit 1
fi
echo

# --------------------------------------------------------------------------
# 1b. Determinism: the same seed must give the same verdict, every time.
#     Everything allowed to differ (wall clock, elapsed time) lives under
#     the `timing` key.
# --------------------------------------------------------------------------
echo "--- determinism ------------------------------------------------------"
bash "${HERE}/grade.sh" "${DEMO}/examples/good" \
    --seed 20260814 --json "${WORK}/det1.json" > "${WORK}/det1.log" 2>&1
DET1_RC=$?
bash "${HERE}/grade.sh" "${DEMO}/examples/good" \
    --seed 20260814 --json "${WORK}/det2.json" > "${WORK}/det2.log" 2>&1
DET2_RC=$?
DET_SAME="$( "$PY" -I - "${WORK}/det1.json" "${WORK}/det2.json" <<'PYDET'
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
    echo "FAIL  determinism check: exits ${DET1_RC}/${DET2_RC}, verdicts ${DET_SAME}"
    exit 1
fi
echo

# --------------------------------------------------------------------------
# 2. Every mutant must fail at least one gate.
# --------------------------------------------------------------------------
MUTDIR="${WORK}/mutants"
"$PY" -I "${HERE}/mutants.py" make-all "$MUTDIR" > /dev/null

NAMES=()
while IFS= read -r name; do
    NAMES+=("$name")
done < <(ls -1 "$MUTDIR" | sort)

echo "--- known-bad mutants -----------------------------------------------"
printf '%-24s %-5s %-12s %s\n' "MUTANT" "EXIT" "KILL CLASS" "GATES FAILED"

# Gates that observe the firmware running: boot, shell, crc_oracle and
# no_hardfault.  A kill whose build failed never produced an ELF, so the
# runtime gates report "no ELF" rather than observed behaviour -- that is
# a build-only kill.  The classes are counted separately.
KILLED=0
KILLED_BEHAV=0
KILLED_BUILD=0
KILLED_STATIC=0
TOTAL=${#NAMES[@]}
TOTAL_BEHAV=0
for name in "${NAMES[@]}"; do
    OUT="${WORK}/${name}.json"
    bash "${HERE}/grade.sh" "${MUTDIR}/${name}" \
        --seed 20260814 --json "$OUT" > "${WORK}/${name}.log" 2>&1
    RC=$?

    # Emit: "<behav_failed> <build_failed> ; <gate (detail); ...>"
    CLASSIFY="$("$PY" -I - "$OUT" <<'PYCLASS'
import json, sys
BEHAV = {"boot", "shell", "crc_oracle", "no_hardfault"}
try:
    d = json.load(open(sys.argv[1]))
except Exception:
    print("0 1 <no verdict JSON>"); sys.exit(0)
bad = {k: v["detail"] for k, v in d.get("gates", {}).items()
       if v["verdict"] != "pass"}
# A failed build produces no ELF; the runtime gates then fail with
# "no ELF", which is not behavioural evidence.
build_failed = "build_clean" in bad
nb = 0 if build_failed else sum(1 for k in bad if k in BEHAV)
detail = "; ".join("%s (%s)" % kv for kv in sorted(bad.items())) \
    if bad else "NONE -- judge passed a broken artifact"
print("%d %d %s" % (nb, 1 if build_failed else 0, detail))
PYCLASS
)"
    NBEHAV="$(printf '%s' "$CLASSIFY" | awk '{print $1}')"
    NBUILD="$(printf '%s' "$CLASSIFY" | awk '{print $2}')"
    FAILED_GATES="$(printf '%s' "$CLASSIFY" | cut -d' ' -f3-)"

    # A mutant is a "behavioural mutant" when it is meant to be caught by a
    # behavioural gate -- mutants.py's table says which.  Build-broken
    # mutants are deliberately excluded from the behavioural denominator.
    MEANT="$(awk -v n="$name" '$1==n {print $2}' \
        <("$PY" -I -c '
import sys
sys.path.insert(0, sys.argv[1])
import mutants
for n, (f, gates, why) in sorted(mutants.MUTANTS.items()):
    print(n, gates)
' "${HERE}"))"
    if [ "$MEANT" != "build_clean" ]; then
        TOTAL_BEHAV=$((TOTAL_BEHAV + 1))
    fi

    if [ "$RC" -ne 0 ]; then
        KILLED=$((KILLED + 1))
        if [ "${NBEHAV:-0}" -gt 0 ]; then
            VERDICT="behavioural"
            KILLED_BEHAV=$((KILLED_BEHAV + 1))
        elif [ "${NBUILD:-0}" -gt 0 ]; then
            VERDICT="build-only"
            KILLED_BUILD=$((KILLED_BUILD + 1))
        else
            VERDICT="static-only"
            KILLED_STATIC=$((KILLED_STATIC + 1))
        fi
    else
        VERDICT="SURVIVED"
    fi
    printf '%-24s %-5s %-12s %s\n' "$name" "$RC" "$VERDICT" "$FAILED_GATES"
done

echo
KILL_RATE="$(("$PY" -I -c "print(int(100*$KILLED/$TOTAL + 0.5))") 2>/dev/null || \
    "$PY" -c "print(int(100*${KILLED}/${TOTAL} + 0.5))")"
if [ "$TOTAL_BEHAV" -gt 0 ]; then
    BEHAV_RATE="$("$PY" -I -c "print(int(100*$KILLED_BEHAV/$TOTAL_BEHAV + 0.5))")"
else
    BEHAV_RATE=0
fi

echo "== summary ==========================================================="
echo "known-good            : PASS (${GOOD_GATES} gates)"
echo "mutants killed        : ${KILLED}/${TOTAL}"
echo "  behavioural kills   : ${KILLED_BEHAV} (a runtime gate fired)"
echo "  build-only kills    : ${KILLED_BUILD} (build failed, no ELF)"
echo "  static-only kills   : ${KILLED_STATIC} (elf/map/integrity gates only)"
echo "kill rate             : ${KILL_RATE} % overall"
echo "behavioural kill rate : ${BEHAV_RATE} % of ${TOTAL_BEHAV} behavioural mutants"
echo

if [ "${BEHAV_RATE}" -lt 90 ]; then
    echo "SELFTEST FAILED: behavioural kill rate ${BEHAV_RATE} % is below the 90 % floor"
    exit 1
fi
if [ "$KILLED_BEHAV" -lt 5 ]; then
    echo "SELFTEST FAILED: fewer than five mutants were killed by behaviour"
    exit 1
fi

echo "SELFTEST PASSED: judge passes the good artifact and kills ${KILLED} mutants"
exit 0
