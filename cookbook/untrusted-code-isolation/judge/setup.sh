#!/bin/sh
# Install the pinned judge toolchain for the untrusted-code-isolation demo.
#
# The judge is Python-standard-library only, so there is no pip closure to
# pin. What this script pins is the one system tool the demo's isolation
# ladder needs and that can be installed without root:
#
#   util-linux 2.38.1-5+deb12u3  - provides `unshare`, used by the runner's
#                                  rootless-userns fallback and by the
#                                  judge's own capability probe
#
# It is fetched from the Debian bookworm pool by exact URL (no `latest`, no
# `apt-get install`; a Debian stable security update from 2024, not a
# package published in the last two weeks), checked against the sha256
# below, and unpacked with `dpkg-deb -x` into
# $HOME/.local/untrusted-code-isolation, so the system package database is
# never touched and no root is needed.
#
# `sudo` is the other tool the ladder uses, but it cannot be installed this
# way: a sudo binary that is not owned by uid 0 and setuid-root refuses to
# run. The script therefore checks the *system* sudo and records its exact
# version; the runner falls back to the rootless-userns rung when it is
# missing. The version this demo was built against is 1.9.13p3-1+deb12u4.
#
# Idempotent: a tool already present at the pinned version is left alone.

set -eu

PREFIX="$HOME/.local/untrusted-code-isolation"
HERE=$(cd "$(dirname "$0")" && pwd)

UL_VER="2.38.1-5+deb12u3"
UL_URL="http://deb.debian.org/debian/pool/main/u/util-linux/util-linux_${UL_VER}_amd64.deb"
UL_SHA="8eb241ff24b2e1ee9c0373f4fc9bc728b85bf5966c1496154df7da01c0e42f34"
SUDO_WANT="1.9.13p3"

case "$(uname -s):$(uname -m)" in
    Linux:x86_64) ;;
    *) echo "setup.sh: unsupported platform $(uname -s) $(uname -m) \
(supported: x86-64 Linux, CPython 3.10-3.13)" >&2; exit 2 ;;
esac

case "$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')" in
    3.10|3.11|3.12|3.13) ;;
    *) echo "setup.sh: unsupported Python \
$(python3 -c 'import sys; print(sys.version.split()[0])') (supported: 3.10-3.13)" >&2
       exit 2 ;;
esac

# The judge runs on this interpreter; a venv keeps the demo's path stable
# and shows that nothing in the demo needs a third-party package.
VENV="$HOME/.venvs/untrusted-code-isolation"
if [ ! -x "$VENV/bin/python" ]; then
    echo "setup.sh: creating judge venv at $VENV"
    python3 -m venv "$VENV"
fi

fetch_unshare() {
    tmp=$(mktemp -d)
    trap 'rm -rf "$tmp"' EXIT INT TERM
    deb="$tmp/util-linux.deb"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL -o "$deb" "$UL_URL"
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "$deb" "$UL_URL"
    else
        echo "setup.sh: need curl or wget to fetch util-linux" >&2
        exit 3
    fi
    got=$(sha256sum "$deb" | cut -d' ' -f1)
    if [ "$got" != "$UL_SHA" ]; then
        echo "setup.sh: sha256 mismatch for $UL_URL" >&2
        echo "  expected $UL_SHA" >&2
        echo "  got      $got" >&2
        exit 3
    fi
    mkdir -p "$PREFIX"
    dpkg-deb -x "$deb" "$PREFIX"
    rm -rf "$tmp"
    trap - EXIT INT TERM
}

UNSHARE=""
if command -v unshare >/dev/null 2>&1; then
    UNSHARE=$(command -v unshare)
    echo "setup.sh: system unshare: $("$UNSHARE" --version 2>/dev/null || echo unknown)"
elif [ -x "$PREFIX/usr/bin/unshare" ]; then
    UNSHARE="$PREFIX/usr/bin/unshare"
    echo "setup.sh: unpacked unshare present"
else
    echo "setup.sh: fetching util-linux $UL_VER (sha256 checked)"
    fetch_unshare
    UNSHARE="$PREFIX/usr/bin/unshare"
fi

if [ -x "$PREFIX/usr/bin/unshare" ]; then
    echo "setup.sh: unpacked util-linux $UL_VER (sha256 checked) available at $PREFIX"
fi

SUDO_BIN=""
SUDO_VER="unavailable"
if command -v sudo >/dev/null 2>&1; then
    SUDO_BIN=$(command -v sudo)
    SUDO_VER=$("$SUDO_BIN" --version 2>/dev/null | head -1 | sed 's/^Sudo version //') || true
fi
case "$SUDO_VER" in
    "$SUDO_WANT"*) echo "setup.sh: system sudo $SUDO_VER (matches the built-against version)" ;;
    unavailable) echo "setup.sh: no sudo; the runner will use the rootless-userns rung" ;;
    *) echo "setup.sh: system sudo $SUDO_VER (demo built against $SUDO_WANT*; still works, recorded)" ;;
esac

# Record what is actually installed, for RECEIPT.md.
{
    printf '## python %s\n' "$("$VENV/bin/python" -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
    printf '## unshare %s\n' "$("$UNSHARE" --version 2>/dev/null || echo unavailable)"
    printf '## unshare path %s\n' "$UNSHARE"
    printf '## sudo %s\n' "$SUDO_VER"
    printf '## kernel %s\n' "$(uname -r)"
    printf '## user-namespaces-max %s\n' "$(cat /proc/sys/user/max_user_namespaces 2>/dev/null || echo n/a)"
    printf '## judge-packages\n'
    "$VENV/bin/pip" list --format=freeze 2>/dev/null
} > "$HERE/VERSIONS.txt.tmp"
mv "$HERE/VERSIONS.txt.tmp" "$HERE/VERSIONS.txt"

echo "setup.sh: judge interpreter: $VENV/bin/python"
echo "setup.sh: ok"
