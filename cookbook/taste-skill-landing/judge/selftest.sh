#!/usr/bin/env bash
# judge/selftest.sh — prove the judge can fail.
#   - the known-good site passes every gate
#   - the same seed twice gives a byte-identical verdict (except 'timing')
#   - the no-skill baseline exits non-zero AND yields a verdict JSON
#     (the exit-code contract: any failed gate => grade.sh rc != 0)
#   - every scripted mutant declares the check it must trip in
#     examples/bad/manifest.json; a kill needs a non-zero grade AND a
#     readable verdict JSON in which that check failed — a crash, a
#     missing verdict or a kill by the wrong check is a survivor
# Exit non-zero unless good passes, determinism holds, the baseline fails
# the right way, and every mutant is killed (0 survivors allowed).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(dirname "$SCRIPT_DIR")"
GOOD="$BASE_DIR/examples/good/site"
BASELINE="$BASE_DIR/examples/baseline/site"
BAD="$BASE_DIR/examples/bad"

export PLAYWRIGHT_BROWSERS_PATH="$HOME/.cache/ms-playwright"
SEED="${SEED:-42}"
OUT="$(mktemp -d /tmp/taste-selftest.XXXXXX)"
trap 'rm -rf "$OUT"' EXIT

failed_gates() {  # $1 = verdict json — print failed gate/sub-check names
    python3 - "$1" <<'EOF'
import json, sys
try:
    v = json.load(open(sys.argv[1]))
except Exception:
    print("?"); sys.exit(0)
names = []
for g in v.get("gates", []):
    if not g["passed"]:
        if g["gate"] == "taste_rules":
            names += [s["rule"] for s in g["detail"] if not s["passed"]]
        else:
            names.append(g["gate"])
print(",".join(names) or "?")
EOF
}

# $1 = verdict json, $2 = intended check. Prints every failed check name;
# exits 2 if the verdict JSON is unreadable (a crash, not a verdict),
# 0 if the intended check is among the failed, 1 otherwise.
check_failed() {
    python3 - "$1" "$2" <<'EOF'
import json, sys
try:
    v = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(2)
names = []
for g in v.get("gates", []):
    if not g["passed"]:
        if g["gate"] == "taste_rules":
            names += [s["rule"] for s in g["detail"] if not s["passed"]]
        else:
            names.append(g["gate"])
print(",".join(names))
sys.exit(0 if sys.argv[2] in names else 1)
EOF
}

# $1 = verdict json — the remote_asset extra proof: at least one external
# request was route-aborted and none escaped the box.
assert_blocked() {
    python3 - "$1" <<'EOF'
import json, sys
try:
    v = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(2)
d = next((g["detail"] for g in v.get("gates", [])
          if g["gate"] == "clean_load"), {})
blocked = sum(len(e.get("external_requests", [])) for e in d.values())
leaked = sum(len(e.get("external_unblocked", [])) for e in d.values())
print(f"{blocked} external request(s) route-aborted, {leaked} escaped")
sys.exit(0 if blocked > 0 and leaked == 0 else 1)
EOF
}

echo "[selftest] Regenerating mutants..."
python3 "$SCRIPT_DIR/mutants.py"

echo ""
echo "[selftest] Known-good site (must PASS):"
if "$SCRIPT_DIR/grade.sh" "$GOOD" --seed "$SEED" --json "$OUT/good.json" \
        >"$OUT/good.log" 2>&1; then
    echo "[selftest]   good/site  PASS"
else
    echo "[selftest]   good/site  FAIL (unexpected!) — see $OUT/good.log"
    tail -5 "$OUT/good.log" || true
fi

echo ""
echo "[selftest] Determinism (same seed twice, verdict minus 'timing'):"
DET_OK=1
if "$SCRIPT_DIR/grade.sh" "$GOOD" --seed "$SEED" --json "$OUT/good2.json" \
        >"$OUT/det.log" 2>&1; then
    if python3 - "$OUT/good.json" "$OUT/good2.json" <<'EOF'
import json, sys
a = json.load(open(sys.argv[1])); b = json.load(open(sys.argv[2]))
a.pop("timing", None); b.pop("timing", None)
sys.exit(0 if a == b else 1)
EOF
    then
        echo "[selftest]   identical"
    else
        echo "[selftest]   NON-DETERMINISTIC"
        DET_OK=0
    fi
else
    echo "[selftest]   re-run failed — see $OUT/det.log"
    DET_OK=0
fi

echo ""
echo "[selftest] No-skill baseline (MUST exit non-zero — the grader's"
echo "[selftest] exit-code contract: any failed gate => grade.sh rc != 0):"
BASE_OK=0
if [[ -d "$BASELINE" ]]; then
    if "$SCRIPT_DIR/grade.sh" "$BASELINE" --seed "$SEED" --json "$OUT/baseline.json" \
            >"$OUT/baseline.log" 2>&1; then
        echo "[selftest]   baseline/site  exit 0 (CONTRACT BROKEN: a failing site must exit non-zero)"
    else
        FAILS="$(failed_gates "$OUT/baseline.json")"
        if [[ "$FAILS" == "?" ]]; then
            echo "[selftest]   baseline/site  exit non-zero but no verdict JSON"
        else
            echo "[selftest]   baseline/site  exit != 0, fails: $FAILS"
            BASE_OK=1
        fi
    fi
else
    echo "[selftest]   baseline/site  missing — skipped (not asserted)"
    BASE_OK=1
fi

echo ""
echo "[selftest] Known-bad mutants (must FAIL their declared check):"
KILLED=0; TOTAL=0; SURVIVED=()
if [[ ! -f "$BAD/manifest.json" ]]; then
    echo "[selftest]   $BAD/manifest.json missing — mutants.py did not"
    echo "[selftest]   declare each mutant's intended check"
    TOTAL=1  # forces the final assertion to fail
else
    while IFS=$'\t' read -r m want; do
        [[ -n "$m" ]] || continue
        TOTAL=$((TOTAL + 1))
        d="$BAD/$m"
        if [[ ! -d "$d" ]]; then
            echo "[selftest]   $m  missing — mutant dir not generated"
            SURVIVED+=("$m (missing)")
            continue
        fi
        if "$SCRIPT_DIR/grade.sh" "$d" --seed "$SEED" --json "$OUT/$m.json" \
                >"$OUT/$m.log" 2>&1; then
            echo "[selftest]   $m  PASSED (missed kill — wanted $want)"
            SURVIVED+=("$m")
            continue
        fi
        fails=""; rc=0
        fails="$(check_failed "$OUT/$m.json" "$want")" || rc=$?
        if [[ $rc -eq 2 ]]; then
            echo "[selftest]   $m  rc != 0 but no verdict JSON (crash, not a kill)"
            SURVIVED+=("$m (no verdict)")
            continue
        fi
        if [[ $rc -eq 1 ]]; then
            echo "[selftest]   $m  wrong kill — wanted $want, failed: ${fails:-none}"
            SURVIVED+=("$m (wrong gates: ${fails:-none})")
            continue
        fi
        extra=""
        if [[ "$m" == "remote_asset" ]]; then
            if extra="$(assert_blocked "$OUT/$m.json")"; then
                extra=" ($extra; nothing left the box)"
            else
                echo "[selftest]   $m  clean_load failed but a request"
                echo "[selftest]      escaped the box — not a kill"
                SURVIVED+=("$m (request escaped)")
                continue
            fi
        fi
        KILLED=$((KILLED + 1))
        echo "[selftest]   $m  killed ($want; failed: $fails)$extra"
    done < <(python3 - "$BAD/manifest.json" <<'EOF'
import json, sys
m = json.load(open(sys.argv[1]))
for k in sorted(m):
    print(f"{k}\t{m[k]}")
EOF
    )
fi

RATE=0
[[ $TOTAL -gt 0 ]] && RATE=$((KILLED * 100 / TOTAL))

GOOD_OK=0
python3 - "$OUT/good.json" <<'EOF' && GOOD_OK=1
import json, sys
sys.exit(0 if json.load(open(sys.argv[1])).get("all_gates_passed") else 1)
EOF

echo ""
echo "[selftest] ============================================"
echo "[selftest] good passed     : $GOOD_OK"
echo "[selftest] determinism     : $DET_OK"
echo "[selftest] baseline fails  : $BASE_OK (contract: rc != 0 + verdict JSON)"
echo "[selftest] mutants killed  : $KILLED/$TOTAL ($RATE%)"
[[ ${#SURVIVED[@]} -gt 0 ]] && echo "[selftest] survived       : ${SURVIVED[*]}"
echo "[selftest] ============================================"

[[ $GOOD_OK -eq 1 && $DET_OK -eq 1 && $BASE_OK -eq 1 \
   && $TOTAL -gt 0 && $KILLED -eq $TOTAL ]] && {
    echo "[selftest] SUCCESS"; exit 0; }
echo "[selftest] FAILURE"
exit 1
