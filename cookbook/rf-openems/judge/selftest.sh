#!/usr/bin/env bash
# Prove the judge can fail: the known-good example passes; every generated
# single-edit mutant fails at least one gate. Prints the kill rate; exits
# non-zero below 90 %.
#
# Options forwarded to grade.sh (e.g. --skip-convergence for a faster run).
set -uo pipefail   # NOT -e: expected failures inside
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "$HERE")"
BASE="${RF_OPENEMS_HOME:-$HOME/.rf-openems}"

source "$HERE/env.sh"

ST_TMP="$(mktemp -d /tmp/rf-selftest.XXXXXX)"

cd "$DEMO"
"$RF_PY" judge/mutants.py generate >/dev/null

killed=0; mtot=0

echo "== good example (expected PASS) =="
t0=$SECONDS
if bash judge/grade.sh examples/good/antenna.py --json "$ST_TMP/st-good.json" "$@"; then
    echo "  -> PASS (as expected)"; good_ok=1
else
    echo "  -> FAIL (unexpected!)"; good_ok=0
fi
echo "  wall: $((SECONDS-t0)) s"

echo "== known-bad mutants (each expected FAIL) =="
for f in examples/bad/bad_*.py; do
    mtot=$((mtot+1))
    t0=$SECONDS
    if bash judge/grade.sh "$f" --json "$ST_TMP/st-$mtot.json" "$@" >/dev/null 2>&1; then
        echo "  $f -> *** PASSED (should have failed) ***"
    else
        kg=$("$RF_PY" - "$f" "$ST_TMP/st-$mtot.json" <<'EOF'
import json, sys
v = json.load(open(sys.argv[2]))
print(",".join(g["gate"] for g in v["gates"] if not g["pass"]))
EOF
)
        echo "  $f -> killed by: $kg"; killed=$((killed+1))
    fi
    echo "    wall: $((SECONDS-t0)) s"
done

# ---- determinism: two quick grades must give identical verdicts --------
echo "== determinism check (two runs, timing stripped) =="
bash judge/grade.sh examples/good/antenna.py --skip-convergence \
    --json "$ST_TMP/st-det1.json" >/dev/null 2>&1 || true
bash judge/grade.sh examples/good/antenna.py --skip-convergence \
    --json "$ST_TMP/st-det2.json" >/dev/null 2>&1 || true
det_ok=$("$RF_PY" - "$ST_TMP/st-det1.json" "$ST_TMP/st-det2.json" <<'EOF'
import json, sys
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
a.pop("timing", None); b.pop("timing", None)
print("1" if a == b else "0")
EOF
)
[ "$det_ok" = "1" ] && echo "  deterministic: yes" || echo "  deterministic: NO"

echo
echo "selftest: good=${good_ok}/1, mutants_killed=${killed}/${mtot}, deterministic=${det_ok}"
"$RF_PY" - "$killed" "$mtot" "$good_ok" "$det_ok" <<'EOF'
import sys
k, m, g, d = map(int, sys.argv[1:5])
rate = k / m if m else 0.0
print(f"kill rate: {rate*100:.0f}% (required >= 90%)")
sys.exit(0 if (rate >= 0.9 and g == 1 and d == 1) else 1)
EOF
