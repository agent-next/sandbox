#!/usr/bin/env bash
# Install pinned tools for the pr-review-agent judge, idempotently.
#
# What the judge needs beyond the base image:
#   * pytest 8.4.2 -- exact version, SHA256-pinned wheels from PyPI
#     (judge/requirements.txt, installed with --require-hashes) into a venv
#     under $HOME.  This is the only download.
#   * python3 >= 3.10 and git -- already present in the agent-next base
#     image; checked here and named in the failure if missing.
#
# Deliberately no Debian packages: this image's apt lists are empty
# (`ls /var/lib/apt/lists` is empty and `apt-get update` would be a network
# dependency for no benefit), and the judge needs nothing from apt.  The
# wheels are py3-none-any, so the install is interpreter-agnostic.
set -euo pipefail

PYTEST_VERSION="8.4.2"
VENV="${PR_REVIEW_VENV:-$HOME/.pr-review-agent/venv}"
# For messages and VERSIONS.txt: the home directory is printed as "$HOME",
# so the committed file records no absolute path (this repo is public).
if [ -n "${PR_REVIEW_VENV:-}" ]; then
    VENV_SHOWN="$PR_REVIEW_VENV"
else
    VENV_SHOWN='$HOME/.pr-review-agent/venv'
fi
JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$JDIR/.." && pwd)"

echo "setup: pr-review-agent judge ($(uname -sm))"

# --- interpreter and git ------------------------------------------------
python3 - <<'EOF' || { echo "setup: python3 >= 3.10 required" >&2; exit 1; }
import sys
assert sys.version_info >= (3, 10), sys.version
EOF
command -v git >/dev/null || {
    echo "setup: git is required (the judge applies the PR diffs with git apply)" >&2
    exit 1
}

# --- pytest into a venv under $HOME -------------------------------------
installed_pytest() {
    [ -x "$VENV/bin/python" ] || return 0
    "$VENV/bin/python" -c 'import pytest; print(pytest.__version__)' 2>/dev/null || true
}

if [ "$(installed_pytest)" = "$PYTEST_VERSION" ]; then
    echo "setup: pytest $PYTEST_VERSION already installed in $VENV_SHOWN (skipping download)"
else
    echo "setup: creating venv $VENV_SHOWN"
    python3 -m venv "$VENV"
    echo "setup: installing pytest $PYTEST_VERSION from PyPI (hashes pinned)"
    "$VENV/bin/python" -m pip install --quiet --no-cache-dir --require-hashes \
        --disable-pip-version-check -r "$JDIR/requirements.txt"
    actual="$(installed_pytest)"
    if [ "$actual" != "$PYTEST_VERSION" ]; then
        echo "setup: installed pytest '$actual' != '$PYTEST_VERSION'" >&2
        exit 1
    fi
fi

# --- fixture integrity: the pinned tree and the answer key must agree ----
python3 -I "$JDIR/fixture/make_fixture.py" --check

# --- record what was installed ------------------------------------------
{
    echo "# pr-review-agent judge: versions installed by judge/setup.sh"
    echo "# ($(uname -sm)), $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "pytest $("$VENV/bin/python" -c 'import pytest; print(pytest.__version__)')"
    echo "pytest venv: $VENV_SHOWN"
    echo "python3 $(python3 --version | awk '{print $2}')"
    echo "git $(git --version | awk '{print $3}')"
} > "$JDIR/VERSIONS.txt"

echo "setup: tool versions"
cat "$JDIR/VERSIONS.txt"
echo "setup: wrote judge/VERSIONS.txt"
echo "setup: done"
