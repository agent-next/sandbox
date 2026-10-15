#!/usr/bin/env bash
# cookbook/scheduled-agent-digest: install pinned tools idempotently.
#
# Installs/verifies:
#   - sqlite3 CLI 3.40.1-2+deb12u2 (Debian bookworm) — the judge's
#     independent aggregate engine (judge/_night.py's SQL oracle).
#   - Python 3.10+ (standard library only — the demo needs no pip packages).
#
# Nothing is fetched with "latest"; the exact Debian package version is the
# pin, and dpkg verifies the package's own sha256 against the Debian index
# on install.  Safe to re-run.
#
# Usage: bash judge/setup.sh
set -euo pipefail

# ---------------------------------------------------------------------------
# Pinned versions (source of truth: judge/VERSIONS.txt)
# ---------------------------------------------------------------------------
SQLITE3_PKG="sqlite3"
SQLITE3_VERSION="3.40.1-2+deb12u2"
PY_MIN_MAJOR=3
PY_MIN_MINOR=10

PREFIX="${HOME}/.scheduled-agent-digest"
VERSIONS="${PREFIX}/VERSIONS.txt"

fail() { echo "setup: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Python 3.10+ (stdlib only; no pip installs)
# ---------------------------------------------------------------------------
python_ensure() {
    if command -v python3 >/dev/null 2>&1; then
        local ver
        ver="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
        local major="${ver%%.*}" minor="${ver##*.}"
        if [ "$major" -gt "$PY_MIN_MAJOR" ] || \
           { [ "$major" -eq "$PY_MIN_MAJOR" ] && [ "$minor" -ge "$PY_MIN_MINOR" ]; }; then
            echo "[setup] python3 ${ver} present (stdlib only, no pip installs needed)"
            return 0
        fi
        echo "[setup] python3 ${ver} is older than ${PY_MIN_MAJOR}.${PY_MIN_MINOR}; installing"
    else
        echo "[setup] python3 not found; installing"
    fi
    sudo apt-get update -qq || fail "apt-get update failed"
    sudo apt-get install -y -qq python3 \
        || fail "installing python3 failed"
}

# ---------------------------------------------------------------------------
# sqlite3 CLI, pinned to the bookworm package version
# ---------------------------------------------------------------------------
sqlite3_ensure() {
    local have=""
    if command -v sqlite3 >/dev/null 2>&1; then
        have="$(sqlite3 --version 2>/dev/null | awk '{print $1}')"
    fi
    if [ "$have" = "$SQLITE3_VERSION" ]; then
        echo "[setup] sqlite3 ${have} already present -> $(command -v sqlite3)"
        return 0
    fi

    echo "[setup] sqlite3 ${SQLITE3_VERSION} not installed (found: ${have:-none}); installing"
    # this image's apt lists may be empty; update and verify it actually fetched
    sudo apt-get update -qq || fail "apt-get update failed"
    # shellcheck disable=SC2046  # dpkg-query output is a simple status line
    lists="$(dpkg-query -W -f='${db:Status-Abbrev}}' apt 2>/dev/null || true)"
    sudo apt-get install -y -qq "${SQLITE3_PKG}=${SQLITE3_VERSION}" \
        || sudo apt-get install -y -qq "${SQLITE3_PKG}" \
        || fail "installing ${SQLITE3_PKG}=${SQLITE3_VERSION} failed"
    have="$(sqlite3 --version 2>/dev/null | awk '{print $1}')"
    [ "$have" = "$SQLITE3_VERSION" ] \
        || fail "sqlite3 is ${have}, expected ${SQLITE3_VERSION}"
    echo "[setup] installed sqlite3 ${have} -> $(command -v sqlite3)"
}

python_ensure
sqlite3_ensure

# ---------------------------------------------------------------------------
# record what is actually installed (SPEC: judge/VERSIONS.txt)
# ---------------------------------------------------------------------------
mkdir -p "${PREFIX}"
{
    echo "# pinned by judge/setup.sh — installed $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "sqlite3 $(sqlite3 --version 2>/dev/null | awk '{print $1, $NF}' | sed 's/ (.*//')"
    echo "python3 $(python3 -c 'import platform; print(platform.python_version())')"
} > "${VERSIONS}"

echo "[setup] done.  versions recorded in ${VERSIONS}"
echo "  sqlite3  -> $(command -v sqlite3) ($(sqlite3 --version | awk '{print $1}'))"
echo "  python3  -> $(command -v python3)"
