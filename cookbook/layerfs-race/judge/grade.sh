#!/usr/bin/env bash
# layerfs-race judge: run the artifact, then check every gate in SPEC.md by
# reading the LayerFS Store through the SDK and re-running the pinned suite.
#
# Usage:
#   bash judge/grade.sh <dir-with-race.mjs> [--seed N] [--json out.json]
#
# Prints one JSON verdict on stdout; exits 0 only if every gate passes.
# Deterministic per seed: run-varying numbers live under the "timing" key.
# The artifact runs on a copy; judge/ is checksummed before and after.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "${HERE}")"
PREFIX="${HOME}/layerfs-race"

ARTDIR="${1:-}"
SEED="20261019"
JSON_OUT=""
shift || true
while [ $# -gt 0 ]; do
  case "$1" in
    --seed) SEED="$2"; shift 2 ;;
    --json) JSON_OUT="$2"; shift 2 ;;
    *) shift ;;
  esac
done

log() { echo "grade: $*" >&2; }
usage() { echo "usage: grade.sh <dir-with-race.mjs> [--seed N] [--json out.json]" >&2; exit 2; }

[ -n "${ARTDIR}" ] && [ -f "${ARTDIR}/race.mjs" ] || usage
[ -d "${ARTDIR}/candidates" ] || { log "artifact has no candidates/ dir"; exit 2; }
[ -f "${PREFIX}/env.sh" ] || { log "run 'bash judge/setup.sh' first (missing ${PREFIX}/env.sh)"; exit 2; }
# shellcheck disable=SC1091
. "${PREFIX}/env.sh"

JUDGE_BEFORE="$(find "${HERE}" -type f ! -name '*.actual.txt' -exec sha256sum {} + | sort | sha256sum | cut -d' ' -f1)"

RUN="$(mktemp -d /tmp/layerfs-race-grade.XXXXXX)"
STAGE="${LAYERFS_SRC}/sdk/js/.race-grade"
VOL="lfs-race-grade-$(date +%s)-$$"
cleanup() {
  for c in $(docker ps -aq --filter "volume=${VOL}" 2>/dev/null); do
    docker rm -f "$c" >/dev/null 2>&1 || true
  done
  docker volume rm "${VOL}" >/dev/null 2>&1 || true
  rm -rf "${RUN}" "${STAGE}"
}
trap cleanup EXIT

# the bugged repository: pinned tree + judge-owned bug.patch
cp -a "${EXPRESS_SRC}" "${RUN}/bugged"
( cd "${RUN}/bugged" && git apply --whitespace=nowarn "${DEMO}/examples/bug.patch" ) \
  || { log "bug.patch does not apply to ${EXPRESS_SRC##*/}"; exit 2; }
grep -q "subdomain offset', 3" "${RUN}/bugged/lib/application.js" \
  || { log "bug.patch did not inject the bug"; exit 2; }

docker volume create "${VOL}" >/dev/null
mkdir -p "${RUN}/home"
chmod 0700 "${RUN}/home"

# stage the artifact inside sdk/js ("@layerfs/sdk" resolves only from there)
rm -rf "${STAGE}"
mkdir -p "${STAGE}"
cp "${ARTDIR}/race.mjs" "${STAGE}/race.mjs"
cp -r "${ARTDIR}/candidates" "${STAGE}/candidates"
cp "${HERE}/grader.mjs" "${STAGE}/grader.mjs"

export LAYERFS_HOME="${RUN}/home" LAYERFS_VOLUME="${VOL}"
export LAYERFS_DOCKER LAYERFS_IMAGE LAYERFS_DAEMON
export RACE_SRC="${RUN}/bugged" RACE_PROJECT="race" RACE_OUT="${RUN}/race.json"
export BASELINE_PASS CORRECT_INDEX

if ! ( cd "${STAGE}" && timeout 600 node race.mjs ); then
  log "artifact exited non-zero (a verdict is still produced)"
fi
( cd "${STAGE}" && timeout 900 node grader.mjs "${RACE_OUT}" "${RUN}/verdict.json" ) \
  || log "grader exited non-zero"

if [ ! -f "${RUN}/verdict.json" ]; then
  printf '{"schema":"agent-next/layerfs-race-verdict@1","verdict":"FAIL","gates":[{"name":"judge-error","pass":false,"detail":"grader produced no verdict"}],"timing":{}}\n' \
    > "${RUN}/verdict.json"
fi

JUDGE_AFTER="$(find "${HERE}" -type f ! -name '*.actual.txt' -exec sha256sum {} + | sort | sha256sum | cut -d' ' -f1)"
if [ "${JUDGE_BEFORE}" != "${JUDGE_AFTER}" ]; then
  node -e '
    const fs = require("fs");
    const v = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
    v.gates.push({ name: "judge-integrity", pass: false, detail: "judge/ changed during grading" });
    v.verdict = "FAIL";
    fs.writeFileSync(process.argv[1], JSON.stringify(v, null, 1));
  ' "${RUN}/verdict.json"
  log "judge/ changed during grading — verdict forced to FAIL"
fi

cat "${RUN}/verdict.json"
[ -n "${JSON_OUT}" ] && cp "${RUN}/verdict.json" "${JSON_OUT}"
grep -q '"verdict": "PASS"' "${RUN}/verdict.json"
