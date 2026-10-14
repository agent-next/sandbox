#!/usr/bin/env bash
# Prove the judge can fail: good passes, every mutant fails, kill rate >= 90%.
set -uo pipefail   # NOT -e: expected failures inside
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "$HERE")"
ENV_DIR="${ENV_DIR:-$HOME/.rf-openems/env}"
MM_BIN="$HOME/.rf-openems/micromamba"

cd "$DEMO"
"$MM_BIN" run -p "$ENV_DIR" python judge/mutants.py generate >/dev/null

pass=0; tot=0

echo "== good example (expected PASS) =="
t0=$SECONDS
if bash judge/grade.sh examples/good/antenna.py --json /tmp/st-good.json "$@"; then
    echo "  -> PASS (as expected)"; pass=$((pass+1))
else
    echo "  -> FAIL (unexpected!)"
fi
tot=$((tot+1)); echo "  wall: $((SECONDS-t0)) s"

echo "== known-bad mutants (each expected FAIL) =="
killed=0; mtot=0
for f in examples/bad/bad_*.py; do
    mtot=$((mtot+1))
    t0=$SECONDS
    if bash judge/grade.sh "$f" --json "/tmp/st-$mtot.json" "$@" >/dev/null 2>&1; then
        echo "  $f -> *** PASSED (should have failed) ***"
    else
        echo "  $f -> killed"; killed=$((killed+1))
    fi
    echo "    wall: $((SECONDS-t0)) s"
done
tot=$((tot+mtot)); pass=$((pass+killed))

echo
echo "selftest: good=1/1, mutants_killed=$killed/$mtot"
python3 - "$killed" "$mtot" <<'EOF'
import sys
k, m = int(sys.argv[1]), int(sys.argv[2])
rate = k / m if m else 0.0
print(f"kill rate: {rate*100:.0f}% (required >= 90%)")
sys.exit(0 if rate >= 0.9 else 1)
EOF
