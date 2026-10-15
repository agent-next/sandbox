#!/usr/bin/env bash
# Prove the judge can fail — through the right gate, and only that gate.
#
# 1. judge/test_judge.py must pass: unit tests of the plant physics, the
#    linearisation, the margin math and the settling definition.
# 2. The good example must pass: the deterministic gates (--no-mc), then
#    the full gate set twice with the same seed — the Monte-Carlo gate
#    must pass and the two verdict JSONs must be byte-identical.
# 3. Every known-bad mutant from judge/mutants.py must be rejected by
#    exit code 1 AND a valid verdict JSON whose overall verdict is FAIL
#    and whose declared target gate (examples/bad/_manifest.json) is the
#    one that failed. A crash, a missing verdict or a judge-integrity
#    trip (exit 2/3) is NOT a kill. Mutants marked isolated must fail
#    their target gate and nothing else — that is what proves the margin
#    and Monte-Carlo gates have independent killing power.
#
# Prints the kill table and kill rate; exits non-zero if any check fails
# or the kill rate is below 90 %. --summary PATH also writes the
# machine-readable kill table read by media/scripts/make_loop.py.
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DEMO="$(cd "$HERE/.." && pwd)"
PY="$HOME/ct-judge-venv/bin/python3"
if [ ! -x "$PY" ]; then
  echo "selftest: judge venv not found; run judge/setup.sh first" >&2
  exit 2
fi

GOOD="$DEMO/examples/good/controller.json"
BADDIR="$DEMO/examples/bad"
SUMMARY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --summary) SUMMARY="$2"; shift 2 ;;
    *) echo "usage: selftest.sh [--summary out.json]" >&2; exit 2 ;;
  esac
done

# regenerate mutants (and their expectations) so they cannot drift from
# the good example
"$PY" -I "$HERE/mutants.py" "$GOOD" "$BADDIR" >/dev/null

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
RESULTS="$TMP/results.tsv"    # name <tab> killed(0/1) <tab> rc <tab> detail
GOODFACTS="$TMP/good.tsv"     # key=value lines about the good gradings
: > "$RESULTS"

fail=0

# ---------------------------------------------------------------- helpers
# grade one artifact quietly; echoes the exit code, verdict in $TMP/v.json
# (removed first: a grade that dies before writing a verdict must never be
# confused with the previous artifact's verdict)
grade_q() {
  local art="$1"; shift
  local rc=0
  rm -f "$TMP/v.json"
  bash "$HERE/grade.sh" "$art" --json "$TMP/v.json" "$@" >/dev/null 2>&1 \
    || rc=$?
  echo "$rc"
}

# check one known-bad kill: rc must be 1 (a clean rejection, not a crash
# or an integrity trip) and the verdict must name the target gate
check_kill() {
  local name="$1" rc="$2"
  cp "$TMP/v.json" "$TMP/kill_${name}.json" 2>/dev/null || : > "$TMP/kill_${name}.json"
  "$PY" -I - "$BADDIR/_manifest.json" "$name" "$rc" "$TMP/kill_${name}.json" \
    "$RESULTS" <<'PYEOF'
import json, sys

man_path, name, rc, vpath, results = sys.argv[1:6]
rc = int(rc)
spec = json.load(open(man_path))[name]
target, isolated = spec["target"], spec["isolated"]
problems, detail = [], ""

if rc != 1:
    problems.append(f"grade exited {rc}, not 1 (2 = setup, 3 = judge "
                    f"modified, 139 = crash — none of these is a kill)")
try:
    v = json.load(open(vpath))
except Exception as exc:
    v = None
    problems.append(f"no valid verdict JSON ({type(exc).__name__})")
if v is not None:
    if v.get("passed") is not False:
        problems.append("overall verdict is not FAIL")
    if target == "validation":
        if not v.get("error"):
            problems.append("expected a validation error verdict")
        detail = v.get("error", "")[:70]
    else:
        gates = v.get("gates", {})
        if target not in gates:
            problems.append(f"verdict has no gate '{target}'")
        else:
            g = gates[target]
            if g["pass"]:
                problems.append(f"target gate {target} passed")
            else:
                detail = f"{target} = {g['value']:.6g}"
            if isolated:
                others = [k for k, gg in gates.items()
                          if k != target and not gg["pass"]]
                if others:
                    problems.append(
                        "also failed (must be isolated): " + ", ".join(others))

killed = 0 if problems else 1
with open(results, "a", encoding="utf-8") as fh:
    fh.write(f"{name}\t{killed}\t{rc}\t{detail}\n")
iso = " [isolated]" if isolated else ""
if problems:
    print(f"FAIL (expected reject): {name}{iso} - " + "; ".join(problems))
    sys.exit(1)
print(f"PASS (expected reject): {name}{iso} - {spec['desc']}"
      + (f" ({detail})" if detail else ""))
PYEOF
}

# ---------------------------------------------------- 1. judge unit tests
echo "== judge unit tests (python3 -m unittest judge/test_judge.py) =="
if (cd "$DEMO" && "$PY" -m unittest judge/test_judge.py); then
  echo "unit_tests=1" >> "$GOODFACTS"
else
  echo "FAIL: judge unit tests" >&2
  echo "unit_tests=0" >> "$GOODFACTS"
  fail=1
fi

# --------------------------------------------- 2. good example must pass
echo "== good example (deterministic gates, --no-mc) =="
rc="$(grade_q "$GOOD" --no-mc)"
if [ "$rc" = 0 ]; then
  echo "PASS (expected pass): $GOOD"
  echo "det_good=1" >> "$GOODFACTS"
else
  echo "FAIL (expected pass, grade exited $rc): $GOOD" >&2
  echo "det_good=0" >> "$GOODFACTS"
  fail=1
fi

# ----------------------- 3. known-bad mutants (deterministic, --no-mc)
echo "== known-bad mutants (deterministic gates, --no-mc) =="
for art in "$BADDIR"/*.json; do
  name="$(basename "$art" .json)"
  [ "$name" = "mc-marginal" ] && continue   # killed by the MC section below
  [ "$name" = "_manifest" ] && continue     # expectations file, not a mutant
  rc="$(grade_q "$art" --no-mc)"
  check_kill "$name" "$rc" || fail=1
done

# --- good example, full gates, twice: MC gate passes + determinism ---
echo "== good example (full gates, graded twice with the same seed) ==
"
D1="$TMP/d1.json"; D2="$TMP/d2.json"
rc1="$(grade_q "$GOOD")"; cp "$TMP/v.json" "$D1"
rc2="$(grade_q "$GOOD")"; cp "$TMP/v.json" "$D2"
if [ "$rc1" = 0 ] && [ "$rc2" = 0 ] \
    && "$PY" -I -c '
import json, sys
v = json.load(open(sys.argv[1]))
sys.exit(0 if (v["passed"] and v["gates"]["mc_pass_fraction"]["pass"]) else 1)
' "$D1"; then
  echo "PASS (expected pass): full grade of the good example, Monte-Carlo \
$("$PY" -I -c 'import json,sys; v=json.load(open(sys.argv[1])); print("%d/%d" % (v["mc_pass"], v["mc_n"]))' "$D1")"
  if "$PY" -I -c '
import json, sys
v = json.load(open(sys.argv[1]))
ng = len(v["gates"]); npr = sum(g["pass"] for g in v["gates"].values())
print("full_good=1\tgates=%d/%d\tmc=%d/%d"
      % (npr, ng, v["mc_pass"], v["mc_n"]))
' "$D1" >> "$GOODFACTS"; then :; else
    echo "FAIL: could not record the good grade facts" >&2
    fail=1
  fi
else
  echo "FAIL (expected pass): full grade rejected the good example \
(exit codes $rc1/$rc2)" >&2
  echo "full_good=0" >> "$GOODFACTS"
  fail=1
fi
if cmp -s "$D1" "$D2"; then
  echo "PASS: verdict JSON byte-identical across the two gradings (seed 20260101)"
  echo "deterministic=1" >> "$GOODFACTS"
else
  echo "FAIL: verdict JSON differs between two gradings with the same seed" >&2
  diff "$D1" "$D2" | head -20 >&2 || true
  echo "deterministic=0" >> "$GOODFACTS"
  fail=1
fi

# --- mc-marginal: passes every deterministic gate, killed by MC alone ---
echo "== mc-marginal mutant (killed by the Monte-Carlo gate alone) =="
rc="$(grade_q "$BADDIR/mc-marginal.json" --no-mc)"
if [ "$rc" = 0 ]; then
  echo "PASS (setup ok): mc-marginal passes every deterministic gate"
else
  echo "FAIL (unexpected): mc-marginal failed a deterministic gate (exit \
$rc), so the Monte-Carlo kill below would not isolate the MC gate" >&2
  fail=1
fi
rc="$(grade_q "$BADDIR/mc-marginal.json")"
check_kill "mc-marginal" "$rc" || fail=1

# ------------------------------------------------------ kill rate + summary
"$PY" -I - "$BADDIR/_manifest.json" "$RESULTS" "$GOODFACTS" "$SUMMARY" \
  <<'PYEOF'
import json, sys

man_path, results_path, goodfacts_path, summary = sys.argv[1:5]

manifest = json.load(open(man_path))
rows = {}
for line in open(results_path, encoding="utf-8"):
    name, killed, rc, detail = line.rstrip("\n").split("\t", 3)
    rows[name] = {"killed": killed == "1", "exit": int(rc), "detail": detail}
facts = dict(l.split("=", 1) for l in
             open(goodfacts_path, encoding="utf-8").read().splitlines())

killed = sum(1 for r in rows.values() if r["killed"])
total = len(manifest)
rate = killed * 100 // total
print(f"== kill rate: {killed}/{total} = {rate}% ==")
if total != len(rows):
    print(f"selftest: graded {len(rows)} mutants but the manifest declares "
          f"{total}", file=sys.stderr)
    sys.exit(1)

if summary:
    good = {"unit_tests": facts.get("unit_tests") == "1",
            "deterministic_gates": facts.get("det_good") == "1",
            "full_gates": facts.get("full_good", "0").split("\t")[0] == "1",
            "repeat_verdicts_identical": facts.get("deterministic") == "1"}
    if "gates" in facts.get("full_good", ""):
        bits = dict(kv.split("=", 1)
                    for kv in facts["full_good"].split("\t")[1:])
        good["gates_passed"], good["gates_total"] = \
            (int(x) for x in bits["gates"].split("/"))
        good["mc_pass"], good["mc_n"] = \
            (int(x) for x in bits["mc"].split("/"))
    doc = {"good": good,
           "mutants": [{"name": n, "desc": s["desc"], "target": s["target"],
                        "isolated": s["isolated"], **rows[n]}
                       for n, s in manifest.items() if n in rows],
           "killed": killed, "total": total, "kill_rate_pct": rate,
           "threshold_pct": 90}
    with open(summary, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")
    print(f"selftest summary written to {summary}")
sys.exit(0 if rate >= 90 else 1)
PYEOF
[ $? -eq 0 ] || fail=1

[ "$fail" = 0 ] && echo "selftest: OK (every check passed)"
exit $fail
