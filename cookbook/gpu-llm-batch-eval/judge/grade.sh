#!/bin/sh
# Grade an LLM batch-eval artifact. See SPEC.md for the gates.
#
#   judge/grade.sh examples/good/bundle.json [--seed N] [--json out.json]
#   LLM_EVAL_MODEL_DIR=<dir with the files pinned in judge/MODEL.txt> \
#       judge/grade.sh examples/good/eval.py [--device cpu] [--json out.json]
#
# Exits 0 only if every gate passes; prints one JSON verdict on stdout.
# Delegates to judge/_grade.py, which runs a .py artifact from a copy in a
# fresh temp dir and checksums judge/ before and after. The judge supplies
# the pinned problems (LLM_EVAL_PROBLEMS) and the device/seed; the caller
# supplies the model directory through LLM_EVAL_MODEL_DIR — the judge never
# downloads weights, so without it a .py artifact fails the structure gate
# naming exactly that. The judge itself is CPU-only: it reads the bundle and
# does string/float work, so it needs nothing but the pinned interpreter.

set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
PY="${LLM_EVAL_PY:-$HOME/.venvs/gpu-llm-batch-eval/bin/python}"

if [ ! -x "$PY" ]; then
    echo "grade.sh: judge interpreter missing; run judge/setup.sh first" >&2
    exit 2
fi

exec "$PY" -I "$HERE/_grade.py" "$@"
