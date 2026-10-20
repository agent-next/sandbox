#!/usr/bin/env bash
# layerfs-race self-test: prove the judge can fail (cookbook/DEMO-STANDARD.md).
#
#   1. examples/good passes every gate
#   2. every mutant from judge/mutants.py fails at least one gate
#      (prints the failing gate names per mutant; kill rate >= 90%)
#   3. determinism: two grades of the good artifact with the same --seed give
#      byte-identical verdict JSON outside the "timing" key
#   4. judge/ checksums are equal before and after the whole run
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "${HERE}")"
GOOD="${DEMO}/examples/good"
WORK="$(mktemp -d /tmp/layerfs-race-selftest.XXXXXX)"
trap 'rm -rf "${WORK}"' EXIT

fail() { echo "selftest: FAIL: $*" >&2; exit 1; }
info() { echo "selftest: $*"; }

JHASH_BEFORE="$(find "${HERE}" -type f -exec sha256sum {} + | sort | sha256sum | cut -d' ' -f1)"

# A mutant counts as killed only when grade.sh fails AND leaves a valid
# verdict JSON with verdict == "FAIL" and at least one gate with
# pass == false. Anything else (no verdict, unreadable verdict, verdict not
# FAIL, no failing gate) is an infrastructure error, not a kill.
kill_status() {
  node -e '
    const fs = require("fs");
    let v;
    try { v = JSON.parse(fs.readFileSync(process.argv[1], "utf8")); }
    catch { console.log("invalid-verdict"); process.exit(0); }
    const failing = (v.gates || []).filter((g) => g.pass === false).map((g) => g.name);
    if (v.verdict === "FAIL" && failing.length > 0) {
      console.log("killed:" + failing.join(","));
    } else {
      console.log("inconsistent-verdict");
    }
  ' "$1" 2>/dev/null || echo "invalid-verdict"
}

# --- 1. known-good must pass -------------------------------------------------
if ! bash "${HERE}/grade.sh" "${GOOD}" --json "${WORK}/good1.json" >"${WORK}/good1.out" 2>"${WORK}/good1.err"; then
  cat "${WORK}/good1.out" "${WORK}/good1.err" >&2
  fail "known-good example did not pass"
fi
info "known-good PASS"

# --- 2. every mutant must fail -----------------------------------------------
python3 "${HERE}/mutants.py" "${GOOD}" "${WORK}/mutants" >/dev/null

nmut=0
killed=0
infra=""
for m in "${WORK}"/mutants/*/; do
  name="$(basename "$m")"
  nmut=$((nmut + 1))
  if bash "${HERE}/grade.sh" "$m" --json "${WORK}/${name}.json" >"${WORK}/${name}.out" 2>"${WORK}/${name}.err"; then
    fail "mutant ESCAPED: ${name} (judge passed on a bad artifact)"
  fi
  status="$(kill_status "${WORK}/${name}.json")"
  case "${status}" in
    killed:*)
      info "mutant KILLED: ${name} (failing gates: ${status#killed:})"
      killed=$((killed + 1))
      ;;
    *)
      info "mutant NOT KILLED (infrastructure): ${name} — ${status}"
      infra="${infra} ${name}(${status})"
      ;;
  esac
done
[ -z "${infra}" ] || info "infrastructure errors (not kills):${infra}"

rate=0
[ "${nmut}" -gt 0 ] && rate=$((100 * killed / nmut))
info "kill rate: ${killed}/${nmut} (${rate}%)"
[ "${nmut}" -ge 7 ] || fail "need >= 7 mutants, have ${nmut}"
[ "${rate}" -ge 90 ] || fail "kill rate ${rate}% < 90%"

# --- 3. determinism: same seed -> identical verdict outside "timing" ---------
bash "${HERE}/grade.sh" "${GOOD}" --json "${WORK}/det2.json" \
  >"${WORK}/det2.out" 2>"${WORK}/det2.err" || fail "second good grade failed"
node -e '
  const fs = require("fs");
  const a = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
  const b = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
  delete a.timing; delete b.timing;
  if (JSON.stringify(a) !== JSON.stringify(b)) {
    console.error("selftest: determinism FAILED: verdicts differ outside timing");
    process.exit(1);
  }
  console.log("selftest: determinism PASS (same seed -> identical verdict outside timing)");
' "${WORK}/good1.json" "${WORK}/det2.json" || exit 1

# --- 4. judge sources untouched ----------------------------------------------
JHASH_AFTER="$(find "${HERE}" -type f -exec sha256sum {} + | sort | sha256sum | cut -d' ' -f1)"
[ "${JHASH_BEFORE}" = "${JHASH_AFTER}" ] || fail "judge/ changed during selftest"

info "PASS"
