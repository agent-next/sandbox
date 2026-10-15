#!/usr/bin/env bash
# judge/selftest.sh — prove the judge can fail before trusting it can pass.
#
# 1. the known-good example passes every gate (grade.sh exits 0);
# 2. every single-edit mutant of it fails at least one gate;
# 3. the kill rate is >= 90% (SPEC.md);
# 4. grading is deterministic: two runs with the same seed produce
#    byte-identical verdict JSON once wall-time fields ("timing") are
#    removed.
#
# Exits non-zero (and says which check failed) otherwise.

set -euo pipefail

JUDGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(dirname "$JUDGE_DIR")"
GOOD="$DEMO_DIR/examples/good/server.py"
VENV="$HOME/.venvs/mcp-tools-host"
SEED="${SELFTEST_SEED:-20261015}"

if [ ! -x "$VENV/bin/python" ]; then
    echo "selftest: $VENV/bin/python missing — run judge/setup.sh first" >&2
    exit 2
fi
PY="$VENV/bin/python"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "== selftest 1/4: known-good example passes every gate =="
if bash "$JUDGE_DIR/grade.sh" "$GOOD" --seed "$SEED" \
        --json "$TMP/good.json" >"$TMP/good.log" 2>&1; then
    echo "selftest: good example passed (exit 0)"
else
    rc=$?
    echo "selftest: FAIL — known-good example exit $rc" >&2
    tail -n 30 "$TMP/good.log" >&2
    exit 1
fi

echo "== selftest 2/4: every mutant fails at least one gate =="
"$PY" "$JUDGE_DIR/mutants.py" --out "$TMP/mutants" >"$TMP/mutants.log" 2>&1 || {
    echo "selftest: FAIL — mutant generation failed" >&2
    cat "$TMP/mutants.log" >&2
    exit 1
}

killed=0
total=0
for m in "$TMP/mutants"/*/; do
    name="$(basename "$m")"
    total=$((total + 1))
    if bash "$JUDGE_DIR/grade.sh" "$m/server.py" --seed "$SEED" \
            --json "$TMP/$name.json" >"$TMP/$name.log" 2>&1; then
        echo "selftest: SURVIVOR — mutant $name passed every gate" >&2
    else
        failed_gates="$("$PY" - "$TMP/$name.json" <<'PYEOF'
import json, sys
try:
    v = json.load(open(sys.argv[1]))
    gates = [n for n, g in v.get("gates", {}).items() if not g["passed"]]
    print(", ".join(gates) or "exit-nonzero")
except Exception:
    print("no-verdict")
PYEOF
)"
        echo "selftest: killed $name (failed: $failed_gates)"
        killed=$((killed + 1))
    fi
done

echo "== selftest 3/4: kill rate =="
rate="$(awk -v k="$killed" -v t="$total" 'BEGIN { printf "%.1f", (t ? 100.0*k/t : 0) }')"
echo "selftest: kill rate ${killed}/${total} (${rate}%)"
if ! awk -v k="$killed" -v t="$total" \
        'BEGIN { if (t < 5) exit 1; exit (100.0*k/t >= 90) ? 0 : 1 }'; then
    echo "selftest: FAIL — need >= 5 mutants and a kill rate >= 90%" >&2
    exit 1
fi

echo "== selftest 4/4: deterministic verdict (same seed, two runs) =="
bash "$JUDGE_DIR/grade.sh" "$GOOD" --seed "$SEED" \
    --json "$TMP/good2.json" >"$TMP/good2.log" 2>&1 || {
    echo "selftest: FAIL — second good run failed" >&2
    tail -n 30 "$TMP/good2.log" >&2
    exit 1
}
if "$PY" - "$TMP/good.json" "$TMP/good2.json" <<'PYEOF'
import json, sys

def canon(path):
    v = json.load(open(path))
    v.pop("timing", None)
    return json.dumps(v, sort_keys=True, indent=2)

sys.exit(0 if canon(sys.argv[1]) == canon(sys.argv[2]) else 1)
PYEOF
then
    echo "selftest: verdicts byte-identical after removing timing"
else
    echo "selftest: FAIL — verdicts differ between identical runs" >&2
    exit 1
fi

echo "selftest: OK (good passes, ${killed}/${total} mutants killed, deterministic)"
