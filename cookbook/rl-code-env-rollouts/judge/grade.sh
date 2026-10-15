#!/usr/bin/env bash
#
# grade.sh -- judge one artifact for the rl-code-env-rollouts demo.
#
#   grade.sh <artifact-dir> [--seed N] [--json out.json]
#
# Prints exactly one JSON verdict object and exits 0 only if every gate
# passes.  The gates themselves live in drive.py; this script only locates the
# pinned Python, applies the numeric constants from the environment, and
# forwards the exit code.

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(dirname "${HERE}")"

ARTIFACT=""
SEED=20261015
JSON_OUT=""

while [ $# -gt 0 ]; do
    case "$1" in
        --seed) SEED="$2"; shift 2 ;;
        --json) JSON_OUT="$2"; shift 2 ;;
        --) shift ;;
        -*) echo "grade: unknown flag $1" >&2; exit 2 ;;
        *) if [ -z "$ARTIFACT" ]; then ARTIFACT="$1"; shift
           else echo "grade: extra arg $1" >&2; exit 2; fi ;;
    esac
done

if [ -z "$ARTIFACT" ]; then
    echo "usage: grade.sh <artifact-dir> [--seed N] [--json out.json]" >&2
    exit 2
fi
if [ ! -d "$ARTIFACT" ]; then
    echo "grade: not a directory: $ARTIFACT" >&2
    exit 2
fi
ARTIFACT="$(cd "$ARTIFACT" && pwd)"

# ------------------------------------------------------------------ python ---
# The judge's own code is standard library only, but the artifact under test
# imports gymnasium, so grading runs in the pinned venv setup.sh created.
ENV_SH="${HOME}/.rl-code-env-rollouts/env.sh"
if [ -f "$ENV_SH" ]; then
    # shellcheck disable=SC1090
    . "$ENV_SH"
fi
PY="${RL_CODE_ENV_PY:-}"
if [ -z "$PY" ] || [ ! -x "$PY" ]; then
    if [ -x "${HOME}/.rl-code-env-rollouts/venv/bin/python" ]; then
        PY="${HOME}/.rl-code-env-rollouts/venv/bin/python"
    else
        echo "grade: pinned venv not found; run judge/setup.sh first" >&2
        exit 3
    fi
fi

# The artifact must not be able to import its way into the judge: grading runs
# from a scratch copy of the artifact, and the judge's own directory is never
# on sys.path ahead of the standard library (drive.py sets that up).
ARGS=("$ARTIFACT" "--seed" "$SEED")
if [ -n "$JSON_OUT" ]; then
    ARGS+=("--json" "$JSON_OUT")
fi

exec "$PY" -I "${HERE}/drive.py" "${ARGS[@]}"
