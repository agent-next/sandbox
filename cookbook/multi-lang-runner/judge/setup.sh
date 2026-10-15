#!/usr/bin/env bash
# cookbook/multi-lang-runner: verify the pinned toolchain, idempotently.
#
# All six tools are expected in the Debian bookworm image the judge runs in.
# This script checks each tool's presence and exact version, and fails if any
# is missing or mismatched. It does not download anything: the tools are part
# of the image, and the judge must run without network access.
#
# Usage: bash judge/setup.sh
set -euo pipefail

log() { printf 'setup: %s\n' "$*"; }
fail() { printf 'setup: %s\n' "$*" >&2; exit 1; }

# Expected versions (Debian bookworm image, recorded in judge/VERSIONS.txt)
EXPECTED_PYTHON="3.12"
EXPECTED_NODE="24"
EXPECTED_GO="1.27"
EXPECTED_RUST="1.98"
EXPECTED_GCC="12.2"
EXPECTED_BASH="5.2"

check_ver() {
    local name="$1" cmd="$2" expected="$3" actual
    actual="$(eval "$cmd" 2>/dev/null || echo "MISSING")"
    case "$actual" in
        MISSING) fail "$name not found (expected $expected)" ;;
    esac
    case "$actual" in
        *"$expected"*) log "$name $actual (expected $expected) OK" ;;
        *) fail "$name version mismatch: got '$actual', expected '$expected'" ;;
    esac
}

check_ver "python3" "python3 --version" "$EXPECTED_PYTHON"
check_ver "node" "node --version" "$EXPECTED_NODE"
check_ver "go" "go version | awk '{print \$3}' | sed 's/go//'" "$EXPECTED_GO"
check_ver "rustc" "rustc --version | awk '{print \$2}'" "$EXPECTED_RUST"
check_ver "gcc" "gcc --version | head -1 | awk '{print \$NF}'" "$EXPECTED_GCC"
check_ver "bash" "bash --version | head -1 | awk '{print \$4}' | cut -d. -f1,2" "$EXPECTED_BASH"

# Record what is on the machine so the receipt is reproducible.
JUDGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
{
    echo "# VERSIONS.txt -- recorded by judge/setup.sh"
    echo "# One entry per tool the demo depends on: the expected version and"
    echo "# the tool's own --version output as actually installed."
    echo
    echo "python3 (oracle + judge + interpreted solutions)"
    python3 --version 2>&1 | sed 's/^/  /'
    echo
    echo "node (interpreted solutions)"
    node --version 2>&1 | sed 's/^/  /'
    echo
    echo "go (compiled solutions)"
    go version 2>&1 | sed 's/^/  /'
    echo
    echo "rustc (compiled solutions)"
    rustc --version 2>&1 | sed 's/^/  /'
    echo
    echo "gcc (compiled C solutions)"
    gcc --version 2>&1 | head -1 | sed 's/^/  /'
    echo
    echo "bash (interpreted solutions)"
    bash --version 2>&1 | head -1 | sed 's/^/  /'
} > "${JUDGE_DIR}/VERSIONS.txt"

log "wrote ${JUDGE_DIR}/VERSIONS.txt"
log "done"
