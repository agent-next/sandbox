#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2026 agent-next contributors
# SPDX-License-Identifier: Apache-2.0
#
# selftest.sh — prove the judge can fail. Runs judge/grade.sh on the
# known-good example and on every known-bad mutant from judge/mutants.py,
# prints the kill rate, and checks that two identical grade runs produce
# byte-identical verdict JSON (determinism).
#
# A mutant counts as KILLED only when a JUDGE GATE failed: grade.sh exits
# non-zero AND the verdict JSON parses AND at least one gate has
# pass: false. A non-zero exit with no parsable gate verdict is a CRASH
# (the artifact broke the judge itself, or the judge broke itself) -- it
# is NOT a kill and fails the self-test. The kill rate is counted that
# way, and every mutant must also fail the gate mutants.py says it
# targets. Exits non-zero if the good example fails, if any mutant
# survives or crashes, if a mutant fails the wrong gate, or if the two
# verdict JSONs differ.
#
# Usage: bash judge/selftest.sh [--json <combined.json>]
set -uo pipefail

DEMO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JUDGE_DIR="$DEMO_DIR/judge"
PREFIX="${NANOUSD_RENDER_PREFIX:-$HOME/.nanousd-render}"
WORK="${SELFTEST_WORK:-$(mktemp -d)}"
SUMMARY_JSON=""

while [ $# -gt 0 ]; do
    case "$1" in
        --json) SUMMARY_JSON="$2"; shift 2 ;;
        *) printf 'usage: selftest.sh [--json <out.json>]\n' >&2; exit 2 ;;
    esac
done

GOOD="$DEMO_DIR/examples/good/scene.usda"
MUT_DIR="$WORK/mutants"

log() { printf '[selftest] %s\n' "$*"; }

# ---------------------------------------------------------------- helpers
# gates_failed <verdict.json> -> comma-separated gate names with pass:false,
# "none" if every gate passed, "unparseable" if the JSON cannot be read
gates_failed() {
    python3 - "$1" <<'PY'
import json, sys
try:
    v = json.load(open(sys.argv[1]))
except Exception:
    print("unparseable")
    raise SystemExit
gates = v.get("gates", {})
print(",".join(sorted(k for k, g in gates.items() if not g.get("pass"))) or "none")
PY
}

# verdict_is_gate_failure <verdict.json> -> 0 iff the JSON parses and at
# least one named gate failed (the only honest kind of kill)
verdict_is_gate_failure() {
    python3 - "$1" <<'PY'
import json, sys
try:
    v = json.load(open(sys.argv[1]))
except Exception:
    sys.exit(1)
gates = v.get("gates", {})
sys.exit(0 if any(not g.get("pass") for g in gates.values()) else 1)
PY
}

# master counters
killed=0
total=0
bad=0
declare -a rows=()

log "generating mutants"
# mutants.py prints one line per mutant: "<name> <gate it must fail> <path>"
if ! python3 "$JUDGE_DIR/mutants.py" --out "$MUT_DIR" --good "$GOOD" \
        > "$WORK/mutant_list.txt"; then
    log "mutant generation FAILED"
    exit 1
fi
cat "$WORK/mutant_list.txt"

# ---------------------------------------------------------------- known good
log "grading known-good example: examples/good/scene.usda"
gb="$WORK/good.json"
if bash "$JUDGE_DIR/grade.sh" "$GOOD" --json "$gb" >"$WORK/good.stdout" 2>"$WORK/good.stderr"; then
    gf="none"
    good_pass=1
else
    gf="$(gates_failed "$gb")"
    good_pass=0
fi
log "  known-good -> $([ "$good_pass" = 1 ] && echo PASS || echo "FAIL ($gf)")"
if [ "$good_pass" = 0 ]; then
    bad=1
fi

# ------------------------------------------------------------- determinism
log "determinism: re-running grade on the known-good example"
g2="$WORK/good2.json"
if bash "$JUDGE_DIR/grade.sh" "$GOOD" --json "$g2" >/dev/null 2>&1; then
    det_rc=0
else
    det_rc=1
fi
if [ "$det_rc" -ne 0 ]; then
    log "  determinism re-run FAILED"
    determinism_ok=0
elif python3 - "$gb" "$g2" <<'PY'
import json, sys
strip = lambda p: {k: v for k, v in json.load(open(p)).items() if k != "timing"}
sys.exit(0 if strip(sys.argv[1]) == strip(sys.argv[2]) else 1)
PY
then
    determinism_ok=1
    log "  two verdicts byte-identical (excluding timing): OK"
else
    determinism_ok=0
    log "  VERDICT JSON NOT IDENTICAL ACROSS RUNS"
    diff <(python3 -c 'import json,sys;print(json.dumps(json.load(open(sys.argv[1])),indent=1,sort_keys=True))' "$gb") \
         <(python3 -c 'import json,sys;print(json.dumps(json.load(open(sys.argv[1])),indent=1,sort_keys=True))' "$g2") | head -20
    bad=1
fi

# ------------------------------------------------------------------ mutants
log "grading known-bad mutants"
while read -r name expect path; do
    [ -n "$name" ] || continue
    mb="$WORK/$name.json"
    total=$((total + 1))
    if bash "$JUDGE_DIR/grade.sh" "$path" --seed 0 --json "$mb" \
            >"$WORK/$name.stdout" 2>&1; then
        verdict="SURVIVED"
        killed_this=0
        bad=1
    elif verdict_is_gate_failure "$mb"; then
        gtot="$(gates_failed "$mb")"
        if [ "$expect" != "any" ] && [[ ",$gtot," != *",$expect,"* ]]; then
            verdict="WRONG GATE (needs $expect)"
            killed_this=0
            bad=1
        else
            verdict="KILLED"
            killed_this=1
            killed=$((killed + 1))
        fi
    else
        verdict="CRASHED (no gate verdict)"
        killed_this=0
        bad=1
    fi
    gtot="$(gates_failed "$mb")"
    log "  $(printf '%-22s' "$name") $verdict  (failed gates: $gtot)"
    rows+=("$name|$verdict|$gtot|$expect")
done < "$WORK/mutant_list.txt"

kill_rate="$(python3 -c "
k, n = $killed, $total
print(f'{100.0*k/n:.1f}%' if n else 'n/a')")"

# ------------------------------------------------------------------ verdict
rc=1
[ "$good_pass" = 1 ] && [ "$killed" = "$total" ] && [ "$determinism_ok" = 1 ] \
    && [ "$total" -ge 5 ] && [ "$bad" = 0 ] && rc=0

log "-------------------------------------------------------------"
log "known-good          : $([ "$good_pass" = 1 ] && echo PASS || echo FAIL)"
log "mutants killed      : $killed / $total (killed BY a judge gate)"
log "kill rate           : $kill_rate (need >= 90%)"
log "verdict determinism : $([ "$determinism_ok" = 1 ] && echo OK || echo FAIL)"

if [ -n "$SUMMARY_JSON" ]; then
    python3 - "$SUMMARY_JSON" "$good_pass" "$killed" "$total" "$kill_rate" "$determinism_ok" "$gb" "${rows[@]}" <<'PY'
import json, os, sys
out = sys.argv[1]
good_pass, killed, total = (int(x) for x in sys.argv[2:5])
kill_rate, determinism_ok = sys.argv[5], int(sys.argv[6])
good_json = sys.argv[7]
rows = [r.split("|") for r in sys.argv[8:]]
doc = {
    "good_pass": bool(good_pass),
    "mutants_killed": killed,
    "mutants_total": total,
    "kill_rate": kill_rate,
    "determinism_ok": bool(determinism_ok),
    "good_verdict": json.load(open(good_json)) if os.path.exists(good_json) else None,
    "mutants": [{"name": r[0], "verdict": r[1], "gates_failed": r[2],
                 "expected_gate": r[3]} for r in rows],
}
with open(out, "w") as fh:
    json.dump(doc, fh, indent=2, sort_keys=True)
    fh.write("\n")
print(f"[selftest] wrote {out}")
PY
fi

log "selftest: $([ "$rc" = 0 ] && echo PASS || echo FAIL)"
exit "$rc"
