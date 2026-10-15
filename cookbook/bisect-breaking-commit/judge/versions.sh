#!/usr/bin/env bash
# judge/versions.sh — print the versions setup.sh installed, from the tools'
# own --version output and dpkg-query.  setup.sh writes this to
# judge/VERSIONS.txt.
#
# Usage: bash judge/versions.sh
#        bash judge/versions.sh --check   # fail if judge/VERSIONS.txt is stale

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cat <<'EOF'
# What judge/setup.sh actually installed — recorded by the tools'
# own --version output, not by hand.  Debian bookworm, snapshot 2026-10-15.
# Reproduce: bash judge/setup.sh && bash judge/versions.sh
EOF
git --version
python3 --version
printf 'dpkg git: '
dpkg-query -W -f='${Version}' git 2>/dev/null || echo '(not a dpkg install)'
echo

if [[ "${1:-}" == "--check" ]]; then
    if ! diff -q <(bash "$0") "$SCRIPT_DIR/VERSIONS.txt" >/dev/null 2>&1; then
        echo "VERSIONS.txt is stale; regenerate with:" >&2
        echo "  bash judge/setup.sh" >&2
        exit 1
    fi
    echo "VERSIONS.txt up to date"
fi
