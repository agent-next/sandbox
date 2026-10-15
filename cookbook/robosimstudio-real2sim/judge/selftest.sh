#!/usr/bin/env bash
# Prove the judge can fail. The good artifact passes every gate; every mutant
# fails at least one. Prints the kill rate and exits non-zero if it is not 100 %.
#
#   judge/selftest.sh [--seed N] [--device cuda:0]
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/.." && pwd)"
seed=0
device=cuda:0
while [ $# -gt 0 ]; do
    case "$1" in
        --seed) seed="$2"; shift 2 ;;
        --device) device="$2"; shift 2 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

echo "== good artifact =="
if "$here/grade.sh" "$root/examples/good/params.json" --seed "$seed" --device "$device" \
        --json "$work/good.json" >/dev/null; then
    echo "good: PASS"
else
    echo "good: FAIL (the judge rejects the known-good artifact)" >&2
    cat "$work/good.json" >&2
    exit 1
fi

echo "== mutants =="
python3 "$here/mutants.py" --good "$root/examples/good/params.json" --out "$work/mutants" >/dev/null

killed=0
total=0
while read -r name expected path; do
    total=$((total + 1))
    if "$here/grade.sh" "$path" --seed "$seed" --device "$device" --json "$work/$name.json" >/dev/null 2>&1; then
        echo "  $name: SURVIVED (expected to fail $expected)"
    else
        failed="$(python3 -c "import json,sys; print(','.join(json.load(open(sys.argv[1]))['failed']))" "$work/$name.json")"
        if [ -z "$failed" ]; then
            echo "  $name: exited non-zero but named no failed gate"
        else
            killed=$((killed + 1))
            echo "  $name: killed by $failed (expected $expected)"
        fi
    fi
done < <(python3 -c "
import json, sys
for row in json.load(open(sys.argv[1])):
    print(row['name'], row['expected_fail'], row['path'])
" "$work/mutants/manifest.json")

echo "== determinism =="
"$here/grade.sh" "$root/examples/good/params.json" --seed "$seed" --device "$device" \
    --json "$work/det1.json" >/dev/null
"$here/grade.sh" "$root/examples/good/params.json" --seed "$seed" --device "$device" \
    --json "$work/det2.json" >/dev/null
if python3 - "$work/det1.json" "$work/det2.json" <<'PY'
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
for v in (a, b):
    v.pop("timing", None)
sys.exit(0 if a == b else 1)
PY
then
    echo "determinism: identical verdicts (timing excluded)"
else
    echo "determinism: the two verdicts differ" >&2
    exit 1
fi

rate=$((killed * 100 / total))
echo "kill rate: $killed/$total = $rate %"
[ "$rate" -ge 90 ] || { echo "kill rate below 90 %" >&2; exit 1; }
echo "selftest: PASS"
