#!/usr/bin/env bash
# judge/grade.sh — run every gate on one MCP server artifact.
#
# Usage: grade.sh <artifact> [--seed N] [--json out.json]
#
# Copies nothing, trusts nothing: the artifact is copied to a temp dir
# and launched from there by mcp_judge.py, which also verifies that the
# judge tree itself did not change while grading (gate J0, fails closed).
# Prints one JSON verdict; exits 0 only if every gate passes.

set -euo pipefail

JUDGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HOME/.venvs/mcp-tools-host"

if [ $# -lt 1 ]; then
    echo "usage: grade.sh <artifact> [--seed N] [--json out.json]" >&2
    exit 2
fi
if [ ! -f "$1" ]; then
    echo "grade.sh: artifact not found: $1" >&2
    exit 2
fi
if [ ! -x "$VENV/bin/python" ]; then
    echo "grade.sh: $VENV/bin/python missing — run judge/setup.sh first" >&2
    exit 2
fi

exec "$VENV/bin/python" "$JUDGE_DIR/mcp_judge.py" "$@"
