#!/usr/bin/env bash
# judge/selftest.sh — prove the judge can fail.
#
# 1. the known-good scene passes every gate;
# 2. every single-edit mutant fails at least one gate;
# 3. the kill rate is printed and must be >= 90 %;
# 4. determinism: grading the good scene twice with the same seed gives
#    byte-identical verdict JSON (ignoring 'timing').
#
# Exits non-zero if any of these do not hold.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
GOOD="$DEMO_DIR/examples/good/scene.usda"
WORK="$(mktemp -d /tmp/physx-selftest.XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

echo "[selftest] 1/4 known-good scene must pass"
if ! bash "$SCRIPT_DIR/grade.sh" "$GOOD" --json "$WORK/good.json" >"$WORK/good.log" 2>&1; then
    echo "[selftest] FAIL: known-good scene did not pass" >&2
    tail -20 "$WORK/good.log" >&2
    exit 1
fi
echo "[selftest]   ok (all gates passed)"

echo "[selftest] 2/4 known-bad mutants must each fail"
python3 "$SCRIPT_DIR/mutants.py" "$GOOD" "$WORK/mutants"

declare -a KILLED=() SURVIVED=()
for d in "$WORK"/mutants/*/; do
    name="$(basename "$d")"
    if bash "$SCRIPT_DIR/grade.sh" "$d/scene.usda" --json "$WORK/$name.json" \
         >"$WORK/$name.log" 2>&1; then
        SURVIVED+=("$name")
        echo "[selftest]   SURVIVED: $name"
    else
        KILLED+=("$name")
        failed_gates="$(python3 - "$WORK/$name.json" <<'PY'
import json, sys
try:
    v = json.load(open(sys.argv[1]))
    gates = v.get("gates", {})
    failed = [g for g, r in gates.items() if not r.get("passed", False)]
    print(", ".join(failed) if failed else "simulation error")
except Exception:
    print("simulation error")
PY
)"
        echo "[selftest]   killed:   $name  (failed: $failed_gates)"
    fi
done

total=$(( ${#KILLED[@]} + ${#SURVIVED[@]} ))
kill_rate=$(( 100 * ${#KILLED[@]} / total ))
echo "[selftest] 3/4 kill rate: ${#KILLED[@]}/$total = ${kill_rate}%"
if (( kill_rate < 90 )); then
    echo "[selftest] FAIL: kill rate below 90 %" >&2
    exit 1
fi
if (( ${#SURVIVED[@]} > 0 )); then
    echo "[selftest] FAIL: surviving mutants: ${SURVIVED[*]}" >&2
    exit 1
fi

echo "[selftest] 4/4 determinism (same seed, byte-identical JSON excl timing)"
bash "$SCRIPT_DIR/grade.sh" "$GOOD" --json "$WORK/good2.json" >/dev/null 2>&1
python3 - "$WORK/good.json" "$WORK/good2.json" <<'PY'
import json, sys
a = json.load(open(sys.argv[1]))
b = json.load(open(sys.argv[2]))
a.pop("timing", None); a.pop("seed", None)
b.pop("timing", None); b.pop("seed", None)
if json.dumps(a, sort_keys=True) != json.dumps(b, sort_keys=True):
    print("[selftest] FAIL: verdict JSON differs between runs", file=sys.stderr)
    sys.exit(1)
print("  identical")
PY

echo "[selftest] PASS: judge kills ${#KILLED[@]}/$total mutants, good passes, deterministic"
