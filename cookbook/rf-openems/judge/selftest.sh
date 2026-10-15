#!/usr/bin/env bash
# Prove the judge can fail, and fail *closed*: the known-good example must
# pass; every generated single-edit mutant must fail — specifically at the
# gate it was built to trip (mutants.py targets). A mutant that passes, a
# missing/unparseable verdict, a grade crash, a wrong-gate kill, a target
# gate that was skipped rather than failed ("not run ..."), a mutant
# generation error, or an unexpected bad_*.py inventory are all selftest
# FAILURES — never counted as kills.
#
# Options forwarded to grade.sh (e.g. --skip-convergence for a faster run;
# mutants then get rc=2 partial verdicts, still counted only if the
# targeted gate actually failed).
set -uo pipefail   # NOT -e: expected failures inside
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "$HERE")"
BASE="${RF_OPENEMS_HOME:-$HOME/.rf-openems}"

source "$HERE/env.sh"

ST_TMP="$(mktemp -d /tmp/rf-selftest.XXXXXX)"

fail() { echo; echo "selftest FAIL: $*" >&2; exit 1; }

cd "$DEMO"

# ---- judge unit tests (no solver) must pass first ----------------------
echo "== judge unit tests (sweep-grid validation) =="
ut="$("$RF_PY" -B judge/test_grid.py 2>&1)" \
    || fail "unit tests failed: $ut"
echo "$ut" | tail -3

# ---- mutant generation must succeed and produce exactly the known set --
gen_out="$("$RF_PY" judge/mutants.py generate 2>&1)" \
    || fail "mutants.py generate rc=$?: $gen_out"
mapfile -t inv < <("$RF_PY" judge/mutants.py targets) \
    || fail "mutants.py targets failed"
[ "${#inv[@]}" -ge 9 ] || fail "mutant inventory too small: ${#inv[@]}"
declare -A target=()
want=()
for line in "${inv[@]}"; do
    name="${line%%$'\t'*}"; gate="${line##*$'\t'}"
    [ -n "$name" ] && [ "$gate" != "$name" ] \
        || fail "unparseable targets line: $line"
    target["$name"]="$gate"; want+=("examples/bad/$name")
done
for f in "${want[@]}"; do
    [ -f "$f" ] || fail "expected mutant $f was not generated"
done
n_on_disk="$(ls examples/bad/bad_*.py 2>/dev/null | wc -l)"
[ "$n_on_disk" -eq "${#want[@]}" ] \
    || fail "unexpected bad_*.py inventory ($n_on_disk != ${#want[@]})"

# ---- good example: rc 0 AND a parseable all_pass verdict ---------------
# (with --skip-convergence a full pass is impossible by design: expect rc 2
# and every gate but G8 green instead)
skip_conv=0
for a in "$@"; do [ "$a" = "--skip-convergence" ] && skip_conv=1; done
echo "== good example (expected PASS) =="
t0=$SECONDS
good_ok=0
grc=0
bash judge/grade.sh examples/good/antenna.py \
    --json "$ST_TMP/st-good.json" "$@" || grc=$?
g="$("$RF_PY" - "$ST_TMP/st-good.json" "$skip_conv" <<'EOF'
import json, sys
skip = sys.argv[2] == "1"
try:
    v = json.load(open(sys.argv[1]))
except Exception:
    print("0"); raise SystemExit
if skip:
    ok = all(g["pass"] or g["gate"] == "G8_convergence"
             for g in v["gates"]) and not v.get("all_pass")
else:
    ok = bool(v.get("all_pass"))
print("1" if ok else "0")
EOF
)"
if [ "$skip_conv" = 1 ]; then
    if [ "$grc" = 2 ] && [ "$g" = 1 ]; then
        echo "  -> partial grade rc=2, all gates but G8 pass (as expected)"
        good_ok=1
    else echo "  -> FAIL (unexpected: rc=$grc)"
    fi
elif [ "$grc" = 0 ] && [ "$g" = 1 ]; then
    echo "  -> PASS (as expected)"; good_ok=1
elif [ "$grc" = 0 ]; then
    echo "  -> rc=0 but verdict not all_pass (unexpected!)"
else
    echo "  -> FAIL (unexpected: rc=$grc)"
fi
echo "  wall: $((SECONDS-t0)) s"

# ---- mutants: kill = nonzero rc AND parseable failing verdict AND the --
# ---- targeted gate actually failed (a "not run ..." gate is NOT a kill) -
echo "== known-bad mutants (each must fail its targeted gate) =="
printf "  %-26s %-22s %s\n" mutant targeted_gate first_failed_gate
killed=0; mtot=0; bad=0
for f in examples/bad/bad_*.py; do
    base="$(basename "$f")"
    tgt="${target[$base]:-}"
    [ -n "$tgt" ] || fail "mutant $base has no targeted gate"
    mtot=$((mtot+1))
    t0=$SECONDS
    if bash judge/grade.sh "$f" --json "$ST_TMP/st-$base.json" "$@" \
            >/dev/null 2>&1; then
        printf "  %-26s %-22s *** PASSED (should have failed) ***\n" \
            "$base" "$tgt"
        bad=$((bad+1))
    else
        res="$("$RF_PY" - "$ST_TMP/st-$base.json" "$tgt" <<'EOF'
import json, sys
tgt = sys.argv[2]
try:
    v = json.load(open(sys.argv[1]))
    gates = v["gates"]
except Exception:
    print("INVALID_VERDICT"); raise SystemExit
# a gate recorded as "not run ..." did not test anything: it is a skip,
# not a failure — counting it as a kill would let --skip-convergence
# "kill" both G8 mutants without ever running convergence
def skipped(g):
    return not g["pass"] and g["detail"].startswith("not run")
failed = [g["gate"] for g in gates if not g["pass"] and not skipped(g)]
skipped = [g["gate"] for g in gates if skipped(g)]
if v.get("all_pass") or not (failed or skipped):
    print("INVALID_VERDICT")
elif tgt not in {g["gate"] for g in gates}:
    print("TARGET_NEVER_RAN")
elif tgt in skipped:
    print("TARGET_SKIPPED")
elif tgt in failed:
    print("KILL\t" + failed[0])
else:
    print("WRONG_GATE\t" + ",".join(failed + skipped))
EOF
)"
        case "$res" in
            KILL*)
                printf "  %-26s %-22s %s\n" "$base" "$tgt" "${res#*$'\t'}"
                killed=$((killed+1));;
            *)
                printf "  %-26s %-22s !!! %s\n" "$base" "$tgt" "$res"
                bad=$((bad+1));;
        esac
    fi
    echo "    wall: $((SECONDS-t0)) s"
done
# undo anything a mutant may have planted in the judge tree
find judge -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
find judge -name '*.pyc' -delete 2>/dev/null || true

# ---- determinism: two quick grades must give identical verdicts --------
echo "== determinism check (two runs, timing stripped) =="
bash judge/grade.sh examples/good/antenna.py --skip-convergence \
    --json "$ST_TMP/st-det1.json" >/dev/null 2>&1 || true
bash judge/grade.sh examples/good/antenna.py --skip-convergence \
    --json "$ST_TMP/st-det2.json" >/dev/null 2>&1 || true
det_ok="$("$RF_PY" - "$ST_TMP/st-det1.json" "$ST_TMP/st-det2.json" <<'EOF'
import json, sys
try:
    a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
except Exception:
    print("0"); raise SystemExit
a.pop("timing", None); b.pop("timing", None)
print("1" if a == b else "0")
EOF
)"
[ "$det_ok" = "1" ] && echo "  deterministic: yes" || echo "  deterministic: NO"

echo
echo "selftest: good=${good_ok}/1, mutants_killed=${killed}/${mtot}, invalid_or_wrong=${bad}, deterministic=${det_ok}"
"$RF_PY" - "$killed" "$mtot" "$good_ok" "$det_ok" "$bad" <<'EOF'
import sys
k, m, g, d, b = map(int, sys.argv[1:6])
rate = k / m if m else 0.0
print(f"kill rate: {rate*100:.0f}% "
      "(100% required — every mutant must fail its targeted gate)")
sys.exit(0 if (k == m and m > 0 and g == 1 and d == 1 and b == 0) else 1)
EOF
