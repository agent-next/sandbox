#!/bin/sh
# Grade an LLM batch-eval artifact. See SPEC.md for the gates.
#
#   judge/grade.sh examples/good/eval.py [--seed N] [--json out.json]
#   judge/grade.sh examples/good/bundle.json [--json out.json]
#
# Exits 0 only if every gate passes; prints one JSON verdict on stdout.
# Delegates to judge/_grade.py, which runs a .py artifact from a copy in a
# fresh temp dir and checksums judge/ before and after. The judge is
# CPU-only: it reads the bundle and does string/float work, so it needs
# nothing but the pinned interpreter.

set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
PY="${LLM_EVAL_PY:-$HOME/.venvs/gpu-llm-batch-eval/bin/python}"

if [ ! -x "$PY" ]; then
    echo "grade.sh: judge interpreter missing; run judge/setup.sh first" >&2
    exit 2
fi

exec "$PY" -I "$HERE/_grade.py" "$@"
