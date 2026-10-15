#!/usr/bin/env bash
# Prove the web-scrape-dataset judge can fail.
#
#   bash judge/selftest.sh [--seed N] [--json out.json]
#
# Runs the judge on:
#   * examples/good/scrape.py          -- must pass every gate
#   * every single-edit mutant of it   -- each must fail at least one gate
#   * the good example twice at one seed -- byte-identical verdict JSON minus
#     the `timing` key (determinism)
#
# Prints the kill rate and exits non-zero if the good example fails, any mutant
# survives, the verdicts differ, or the kill rate is below 90 %.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$HERE/.." && pwd)"
GOOD="$DEMO/examples/good/scrape.py"

SEED=""
JSON=""
while [ $# -gt 0 ]; do
    case "$1" in
        --seed) SEED="$2"; shift 2 ;;
        --json) JSON="$2"; shift 2 ;;
        *) echo "selftest: unknown argument: $1" >&2; exit 2 ;;
    esac
done
seed_args=()
[ -n "$SEED" ] && seed_args=(--seed "$SEED")

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# ---- 1. the known-good example must pass ----------------------------------
echo "[selftest] good example"
bash "$HERE/grade.sh" "$GOOD" "${seed_args[@]}" --json "$work/good.json" \
    >"$work/good.log" 2>&1 && good_rc=0 || good_rc=$?
if [ "$good_rc" -ne 0 ]; then
    echo "[selftest] FAIL: examples/good/scrape.py did not pass (exit $good_rc)"
    tail -40 "$work/good.log" >&2
    exit 1
fi
good_gates="$(python3 -c "
import json; v=json.load(open('$work/good.json'))
print(sum(1 for g in v['gates'] if g['pass']), len(v['gates']))")"
echo "[selftest] good example PASS ($good_gates gates)"

# ---- 2. determinism: same seed twice -> identical verdicts ----------------
echo "[selftest] determinism (two runs, same seed)"
bash "$HERE/grade.sh" "$GOOD" "${seed_args[@]}" --json "$work/good2.json" \
    >"$work/good2.log" 2>&1 || true
python3 - "$work/good.json" "$work/good2.json" <<'PY'
import json, sys
def load(p):
    v = json.load(open(p))
    v.pop('timing', None)      # wall time is allowed to differ
    v.pop('base_url', None)    # the port is ephemeral
    return v
a, b = load(sys.argv[1]), load(sys.argv[2])
if a != b:
    print('[selftest] FAIL: two runs at the same seed differ', file=sys.stderr)
    sys.exit(1)
print('[selftest] determinism PASS (verdicts identical minus timing/base_url)')
PY

# ---- 3. every mutant must fail --------------------------------------------
echo "[selftest] generating mutants"
python3 "$HERE/mutate.py" "$GOOD" "$work/mutants" >"$work/mutants.txt"
n_mutants="$(ls "$work"/mutants/*.py | wc -l | tr -d ' ')"

killed=0
survivors=()
details=()
for m in "$work"/mutants/*.py; do
    name="$(basename "$m" .py)"
    bash "$HERE/grade.sh" "$m" "${seed_args[@]}" --json "$work/$name.json" \
        >"$work/$name.log" 2>&1 && rc=0 || rc=$?
    failed="$(python3 -c "
import json
try:
    v = json.load(open('$work/$name.json'))
    print(','.join(g['gate'] for g in v['gates'] if not g['pass']) or 'none')
except Exception:
    print('no-verdict')" 2>/dev/null || echo 'no-verdict')"
    if [ "$rc" -ne 0 ]; then
        killed=$((killed + 1))
        details+=("  $name: killed by $failed")
    else
        survivors+=("$name")
        details+=("  $name: SURVIVED (exit 0)")
    fi
done

echo "[selftest] mutants:"
printf '%s\n' "${details[@]}"

kill_rate="$(python3 -c "print('%.1f' % (100.0 * $killed / $n_mutants))")"
echo "[selftest] kill rate: $killed/$n_mutants = ${kill_rate}%"

status=0
if [ "${#survivors[@]}" -ne 0 ]; then
    echo "[selftest] FAIL: mutants survived: ${survivors[*]}" >&2
    status=1
fi
if ! python3 -c "import sys; sys.exit(0 if $killed * 100 >= 90 * $n_mutants else 1)"; then
    echo "[selftest] FAIL: kill rate ${kill_rate}% is below the 90 % floor" >&2
    status=1
fi

if [ -n "$JSON" ]; then
    python3 - "$JSON" "$killed" "$n_mutants" "$kill_rate" "$work/good.json" <<'PY'
import json, sys
out, killed, total, rate, good = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
json.dump({'good': json.load(open(good)), 'mutants': {'killed': killed, 'total': total, 'kill_rate_pct': rate}},
          open(out, 'w'), indent=2, sort_keys=True)
PY
fi

if [ "$status" -eq 0 ]; then
    echo "[selftest] PASS: good example passes, all $n_mutants mutants killed"
else
    echo "[selftest] FAIL"
fi
exit "$status"
