#!/usr/bin/env bash
# layerfs-race judge: run the artifact, then check every gate in SPEC.md by
# reading the LayerFS Store through the SDK and re-running the pinned suite.
#
# Usage:
#   bash judge/grade.sh <dir-with-race.mjs> [--seed N] [--json out.json]
#
# Prints exactly one JSON verdict line on stdout; all progress goes to
# stderr. Exits 0 only if every gate passes. Deterministic per seed:
# run-varying numbers live under the "timing" key.
#
# The artifact runs in a staged directory that does NOT contain the grader,
# in its own session: when it exits or times out, its whole process group
# is killed so detached children cannot plant files or watch the judge.
# The grader runs from a private copy whose sha256 is checked before and
# after the artifact run; judge/ itself is also checksummed before and
# after, and the verdict is written into a directory created only after
# the artifact's process group is dead, so a planted verdict cannot win.
# An artifact that exits non-zero, a tampered grader copy, a grader crash,
# or a grader that cannot write its verdict all force a FAIL verdict and
# a non-zero exit.
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
# the staged artifact lives inside sdk/js, so the SDK source and the native
# addon are checksummed too. sdk/js/node_modules is NOT re-hashed here: its
# contents are the pinned, recorded dependency tree from setup.sh (npm does
# not verify installed packages at runtime), and layerfs-daemon is the
# pinned-commit build artifact.
SDK_BEFORE="$({ find "${LAYERFS_SRC}/sdk/js/src" "${LAYERFS_SRC}/sdk/js/operator" \
    -type f -exec sha256sum {} + 2>/dev/null | sort; \
  sha256sum "${LAYERFS_SRC}/sdk/js/package.json" "${LAYERFS_SRC}/sdk/js/native/layerfs.node" 2>/dev/null; \
  } | sha256sum | cut -d' ' -f1)"

RUN="$(mktemp -d /tmp/layerfs-race-grade.XXXXXX)"
STAGE="${LAYERFS_SRC}/sdk/js/.race-grade"
JSTAGE="${LAYERFS_SRC}/sdk/js/.race-judge-$$"
VOL="lfs-race-grade-$(date +%s)-$$"
cleanup() {
  for c in $(docker ps -aq --filter "volume=${VOL}" 2>/dev/null); do
    docker rm -f "$c" >/dev/null 2>&1 || true
  done
  docker volume rm "${VOL}" >/dev/null 2>&1 || true
  # the artifact may have chmod'ed away write bits inside ${RUN}
  chmod -R u+rwX "${RUN}" "${STAGE}" 2>/dev/null || true
  rm -rf "${RUN}" "${STAGE}" "${JSTAGE}"
}
trap cleanup EXIT

# the bugged repository: the judge's own pristine bugged checkout, built
# once by setup.sh; BUGGED_SHA is its full-tree digest (oracle reference).
[ -d "${BUGGED_SRC:-/nonexistent}" ] && [ -n "${BUGGED_SHA:-}" ] \
  || { log "env.sh has no BUGGED_SRC/BUGGED_SHA — re-run judge/setup.sh"; exit 2; }
cp -a "${BUGGED_SRC}" "${RUN}/bugged"
grep -q "subdomain offset', 3" "${RUN}/bugged/lib/application.js" \
  || { log "bugged checkout lost the injected bug"; exit 2; }

# the pinned test file list is fixed here, before the artifact runs, so the
# artifact cannot add, drop or reorder tests in the oracle.
export RACE_TEST_FILES
RACE_TEST_FILES="$(cd "${RUN}/bugged" && ls test/*.js test/acceptance/*.js | tr '\n' ' ')"

docker volume create "${VOL}" >/dev/null
mkdir -p "${RUN}/home"
chmod 0700 "${RUN}/home"

# stage the artifact inside sdk/js ("@layerfs/sdk" resolves only from there);
# the staged dir holds race.mjs + candidates and nothing else.
rm -rf "${STAGE}"
mkdir -p "${STAGE}"
cp "${ARTDIR}/race.mjs" "${STAGE}/race.mjs"
cp -r "${ARTDIR}/candidates" "${STAGE}/candidates"

# the grader runs from a private copy, not from judge/ and never from the
# staged dir; its sha256 is verified before and after the artifact runs.
rm -rf "${JSTAGE}"
mkdir -p "${JSTAGE}"
cp "${HERE}/grader.mjs" "${JSTAGE}/grader.mjs"
GRADER_SHA_BEFORE="$(sha256sum "${JSTAGE}/grader.mjs" | cut -d' ' -f1)"

export LAYERFS_HOME="${RUN}/home" LAYERFS_VOLUME="${VOL}"
export LAYERFS_DOCKER LAYERFS_IMAGE LAYERFS_DAEMON
export RACE_SRC="${RUN}/bugged" RACE_PROJECT="race" RACE_OUT="${RUN}/race.json"
export RACE_TREE_SHA="${BUGGED_SHA}"
export BASELINE_PASS CORRECT_INDEX

# The artifact runs in a new session (setsid): its PID is also its process
# group id. A watchdog kills the whole group at 600 s; after it exits, the
# group is killed again so detached children cannot survive into grading.
ART_RC=0
( cd "${STAGE}" && exec setsid node race.mjs ) >"${RUN}/artifact.log" 2>&1 &
ART_PID=$!
( sleep 600; touch "${RUN}/.art-timeout"; kill -KILL -- -"${ART_PID}" 2>/dev/null ) &
WDOG=$!
wait "${ART_PID}" || ART_RC=$?
if [ -f "${RUN}/.art-timeout" ]; then
  ART_RC=124
else
  pkill -P "${WDOG}" 2>/dev/null || true
  kill "${WDOG}" 2>/dev/null || true
fi
wait "${WDOG}" 2>/dev/null || true
kill -KILL -- -"${ART_PID}" 2>/dev/null || true
if [ "${ART_RC}" -ne 0 ]; then
  log "artifact exited ${ART_RC} (last log lines follow)"
  tail -20 "${RUN}/artifact.log" >&2 || true
fi

# the verdict lives in a fresh, randomly-named directory created only now —
# after the artifact's process group is dead — so the artifact (which knows
# RUN via RACE_OUT) cannot have planted or pre-created it.
chmod u+rwx "${RUN}" 2>/dev/null || true
VDIR="$(mktemp -d "${RUN}/verdict.XXXXXX")"
rm -f "${VDIR}/verdict.json"

GRADER_SHA_AFTER="$(sha256sum "${JSTAGE}/grader.mjs" 2>/dev/null | cut -d' ' -f1 || echo missing)"
GRADER_INTACT=0
[ "${GRADER_SHA_AFTER}" = "${GRADER_SHA_BEFORE}" ] && GRADER_INTACT=1

GRADER_RC=0
if [ "${GRADER_INTACT}" -eq 1 ]; then
  ( cd "${JSTAGE}" && timeout 900 node grader.mjs "${RACE_OUT}" "${VDIR}/verdict.json" ) \
    >"${RUN}/grader.log" 2>&1 || GRADER_RC=$?
  if [ "${GRADER_RC}" -ne 0 ]; then
    log "grader exited ${GRADER_RC} (last log lines follow)"
    tail -20 "${RUN}/grader.log" >&2 || true
  fi
else
  log "private grader copy changed during the artifact run — refusing to run it"
fi

chmod -R u+rwX "${VDIR}" 2>/dev/null || true
if [ ! -f "${VDIR}/verdict.json" ]; then
  printf '{"schema":"agent-next/layerfs-race-verdict@1","verdict":"FAIL","gates":[{"name":"judge-error","pass":false,"detail":"grader produced no verdict"}],"timing":{}}\n' \
    > "${VDIR}/verdict.json"
fi

force_fail() {
  # $1 = gate name, $2 = detail: append a failing gate and force FAIL.
  # rmSync first: a planted read-only verdict cannot block the rewrite.
  node -e '
    const fs = require("fs");
    let v;
    try { v = JSON.parse(fs.readFileSync(process.argv[1], "utf8")); }
    catch { v = { schema: "agent-next/layerfs-race-verdict@1", verdict: "FAIL", gates: [], timing: {} }; }
    v.gates.push({ name: process.argv[2], pass: false, detail: process.argv[3] });
    v.verdict = "FAIL";
    fs.rmSync(process.argv[1]);
    fs.writeFileSync(process.argv[1], JSON.stringify(v, null, 1));
  ' "${VDIR}/verdict.json" "$1" "$2"
}

[ "${ART_RC}" -eq 0 ] || force_fail "artifact-exit" "artifact exited ${ART_RC}"
[ "${GRADER_INTACT}" -eq 1 ] || force_fail "grader-integrity" "private grader copy changed during the artifact run"
[ "${GRADER_RC}" -eq 0 ] || force_fail "grader-exit" "grader exited ${GRADER_RC}"

JUDGE_AFTER="$(find "${HERE}" -type f ! -name '*.actual.txt' -exec sha256sum {} + | sort | sha256sum | cut -d' ' -f1)"
if [ "${JUDGE_BEFORE}" != "${JUDGE_AFTER}" ]; then
  force_fail "judge-integrity" "judge/ changed during grading"
  log "judge/ changed during grading — verdict forced to FAIL"
fi
SDK_AFTER="$({ find "${LAYERFS_SRC}/sdk/js/src" "${LAYERFS_SRC}/sdk/js/operator" \
    -type f -exec sha256sum {} + 2>/dev/null | sort; \
  sha256sum "${LAYERFS_SRC}/sdk/js/package.json" "${LAYERFS_SRC}/sdk/js/native/layerfs.node" 2>/dev/null; \
  } | sha256sum | cut -d' ' -f1)"
if [ "${SDK_BEFORE}" != "${SDK_AFTER}" ]; then
  force_fail "sdk-integrity" "sdk/js sources changed during grading"
  log "sdk/js changed during grading — verdict forced to FAIL"
fi

# stdout carries exactly one JSON verdict line; everything else is stderr.
# A leftover artifact process could still swap the file afterwards — refuse
# to print anything but the bytes we just wrote.
VSHA="$(sha256sum "${VDIR}/verdict.json" | cut -d' ' -f1)"
chmod -R u+rwX "${VDIR}" 2>/dev/null || true
if [ "$(sha256sum "${VDIR}/verdict.json" | cut -d' ' -f1)" != "${VSHA}" ]; then
  log "verdict file changed after grading — forcing FAIL"
  printf '{"schema":"agent-next/layerfs-race-verdict@1","verdict":"FAIL","gates":[{"name":"judge-error","pass":false,"detail":"verdict file changed after grading"}],"timing":{}}\n' \
    > "${VDIR}/verdict.json"
fi
node -e 'process.stdout.write(JSON.stringify(JSON.parse(require("fs").readFileSync(process.argv[1], "utf8"))) + "\n")' \
  "${VDIR}/verdict.json"
[ -n "${JSON_OUT}" ] && cp "${VDIR}/verdict.json" "${JSON_OUT}"
grep -qE '"verdict": ?"PASS"' "${VDIR}/verdict.json"
