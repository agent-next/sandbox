#!/usr/bin/env bash
# judge/selftest.sh — prove the judge can fail.
#
# 1. the known-good scene passes every gate;
# 2. every single-edit mutant fails at least one gate;
# 3. the kill rate counts a mutant as killed ONLY when the verdict JSON
#    shows a failed gate — a scene that crashes the simulator before the
#    gates run is an error (and a broken mutant), not a kill;
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

echo "[selftest] 2/4 known-bad mutants must each be killed by a gate"
python3 "$SCRIPT_DIR/mutants.py" "$GOOD" "$WORK/mutants"

declare -a KILLED=() SURVIVED=() ERRORED=()
for d in "$WORK"/mutants/*/; do
    name="$(basename "$d")"
    bash "$SCRIPT_DIR/grade.sh" "$d/scene.usda" --json "$WORK/$name.json" \
         >"$WORK/$name.log" 2>&1 || true
    read -r verdict failed_gates <<<"$(python3 - "$WORK/$name.json" <<'PY'
import json, sys
try:
    v = json.load(open(sys.argv[1]))
except Exception:
    print("error", "no verdict JSON produced")
    raise SystemExit
gates = v.get("gates", {})
failed = sorted(g for g, r in gates.items() if not r.get("passed", False))
if v.get("error") or not gates:
    print("error", v.get("error") or "no gates in verdict")
elif failed:
    print("killed", ", ".join(failed))
else:
    print("survived", "all gates passed")
PY
)"
    case "$verdict" in
        killed)
            KILLED+=("$name")
            echo "[selftest]   killed:   $name  (failed: $failed_gates)"
            ;;
        survived)
            SURVIVED+=("$name")
            echo "[selftest]   SURVIVED: $name  ($failed_gates)"
            ;;
        *)
            ERRORED+=("$name")
            echo "[selftest]   ERROR:    $name  never reached the gates " \
                 "($failed_gates) — a mutant must fail a gate, not crash" >&2
            ;;
    esac
done

total=$(( ${#KILLED[@]} + ${#SURVIVED[@]} + ${#ERRORED[@]} ))
kill_rate=$(( 100 * ${#KILLED[@]} / total ))
echo "[selftest] 3/4 kill rate (killed by a gate / total): ${#KILLED[@]}/$total = ${kill_rate}%"
if (( ${#SURVIVED[@]} > 0 )); then
    echo "[selftest] FAIL: surviving mutants: ${SURVIVED[*]}" >&2
    exit 1
fi
if (( ${#ERRORED[@]} > 0 )); then
    echo "[selftest] FAIL: mutants that never reached the gates: ${ERRORED[*]}" >&2
    exit 1
fi
if (( kill_rate < 90 )); then
    echo "[selftest] FAIL: kill rate below 90 %" >&2
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

echo "[selftest] PASS: judge kills ${#KILLED[@]}/$total mutants by a gate, good passes, deterministic"
