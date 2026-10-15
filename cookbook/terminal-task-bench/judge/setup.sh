#!/usr/bin/env bash
# Install the pinned tools the terminal-task-bench judge needs, idempotently.
#
# What the judge uses: bash, python3 (>= 3.10, stdlib only), git, the sqlite3
# CLI, tar and coreutils.  On a Debian/Ubuntu image all of these are already
# present except sqlite3, which is installed from a sha256-checked Debian
# .deb.  Nothing is downloaded at grade time beyond this one package, and no
# `latest` is ever used.
#
# The demo's fixtures are generated from a seed by
# fixtures/make_fixtures.py, so there is no third-party data to fetch.
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Debian bookworm pool; version pinned, sha256 checked below.
SQLITE3_VERSION="3.40.1-2+deb12u2"
SQLITE3_URL="https://deb.debian.org/debian/pool/main/s/sqlite3/sqlite3_${SQLITE3_VERSION}_amd64.deb"
SQLITE3_SHA256="58e59f7db8a88f87333c3f9896b98146fdf4dc33eda75a1f79d9100d1b819909"

SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    SUDO="sudo"
fi

installed_sqlite3() {
    dpkg-query -W -f='${Version}' sqlite3 2>/dev/null || true
}

need_sqlite3=1
if command -v sqlite3 >/dev/null 2>&1; then
    have="$(installed_sqlite3)"
    have_cli="$(sqlite3 --version | awk '{print $1}')"
    if [ -n "$have" ] && [ "$have" = "$SQLITE3_VERSION" ]; then
        echo "setup: sqlite3 $SQLITE3_VERSION already installed (skipping)"
        need_sqlite3=0
    elif [ "$have_cli" = "3.40.1" ]; then
        echo "setup: sqlite3 CLI 3.40.1 present (package version ${have:-unknown})"
        need_sqlite3=0
    fi
fi

if [ "$need_sqlite3" -eq 1 ]; then
    echo "setup: installing sqlite3 $SQLITE3_VERSION from the Debian pool"
    tmpdir="$(mktemp -d)"
    trap 'rm -rf "$tmpdir"' EXIT
    curl -fsSL -o "$tmpdir/sqlite3.deb" "$SQLITE3_URL"
    echo "$SQLITE3_SHA256  $tmpdir/sqlite3.deb" | sha256sum -c - || {
        echo "setup: sha256 mismatch on sqlite3.deb" >&2
        exit 1
    }
    $SUDO apt-get update -qq
    $SUDO DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$tmpdir/sqlite3.deb"
fi

# Every other tool has to be there already; fail loudly rather than let a
# missing binary turn into a mysterious verifier failure later.
missing=""
for tool in bash python3 git tar awk sed grep sha256sum cmp; do
    command -v "$tool" >/dev/null 2>&1 || missing="$missing $tool"
done
[ -n "$missing" ] && { echo "setup: missing tools:$missing" >&2; exit 1; }

python3 - <<'EOF' || { echo "setup: python3 >= 3.10 required" >&2; exit 1; }
import sys
assert sys.version_info >= (3, 10), sys.version
EOF

echo "setup: tool versions"
python3 --version
git --version
sqlite3 --version
bash --version | head -1
tar --version | head -1

{
    echo "# terminal-task-bench judge: versions installed by judge/setup.sh"
    echo "# ($(uname -sm))"
    echo "python3 $(python3 --version | awk '{print $2}')"
    echo "git $(git --version | awk '{print $3}')"
    echo "sqlite3 $(sqlite3 --version | awk '{print $1}')"
    echo "sqlite3 debian package: $(installed_sqlite3)"
    echo "bash $(bash --version | head -1 | awk '{print $4}')"
    echo "tar $(tar --version | head -1 | awk '{print $4}')"
} > "$JDIR/VERSIONS.txt"
echo "setup: wrote $JDIR/VERSIONS.txt"
echo "setup: done"
