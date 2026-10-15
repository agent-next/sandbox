#!/usr/bin/env bash
# cookbook/scheduled-agent-digest: install pinned tools idempotently into $HOME.
#
# Installs (into $HOME/.scheduled-agent-digest):
#   - sqlite3 CLI 3.40.1-2+deb12u2 (Debian bookworm), sha256-pinned, with its
#     matching libsqlite3-0 — the independent aggregate engine behind the
#     judge's SQL oracle (judge/_night.py).
#
# The demo is stdlib-only Python; no pip packages are installed.  Python 3.10+
# is expected from the system (installed via apt if missing).
#
# Nothing is fetched with "latest"; the exact Debian package versions are the
# pins and every download is sha256-checked.  Safe to re-run.
#
# Usage: bash judge/setup.sh
set -euo pipefail

# ---------------------------------------------------------------------------
# Pinned versions (source of truth: judge/VERSIONS.txt)
# ---------------------------------------------------------------------------
SQLITE3_PKG_VERSION="3.40.1-2+deb12u2"
SQLITE3_UPSTREAM="3.40.1"

SQLITE3_DEB="sqlite3_${SQLITE3_PKG_VERSION}_amd64.deb"
SQLITE3_SHA256="58e59f7db8a88f87333c3f9896b98146fdf4dc33eda75a1f79d9100d1b819909"
LIBSQLITE_DEB="libsqlite3-0_${SQLITE3_PKG_VERSION}_amd64.deb"
LIBSQLITE_SHA256="a8d78b40e9b4e422224aeebfe0e4dfc243f6acf3532490b0c05480d4283d41e2"
DEB_BASE="https://deb.debian.org/debian/pool/main/s/sqlite3"

PREFIX="${HOME}/.scheduled-agent-digest"
BIN="${PREFIX}/bin"
LIB="${PREFIX}/lib"

fail() { echo "setup: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Python 3.10+ (stdlib only)
# ---------------------------------------------------------------------------
python_ensure() {
    if command -v python3 >/dev/null 2>&1 \
       && python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
        echo "[setup] python3 $(python3 -c 'import platform; print(platform.python_version())') present"
        return 0
    fi
    echo "[setup] installing python3 (>= 3.10)"
    sudo apt-get update -qq || fail "apt-get update failed"
    sudo apt-get install -y -qq python3 || fail "installing python3 failed"
}

# ---------------------------------------------------------------------------
# sqlite3 CLI, pinned.  Prefer an already-present binary that reports the
# pinned upstream version; otherwise download both pinned debs, verify their
# sha256, extract them under $HOME and expose a wrapper on PATH.
# ---------------------------------------------------------------------------
sqlite3_present() {
    command -v sqlite3 >/dev/null 2>&1 || return 1
    [ "$(sqlite3 --version 2>/dev/null | awk '{print $1}')" = "$SQLITE3_UPSTREAM" ]
}

fetch_deb() {
    local deb="$1" sha="$2" tmp="$3"
    echo "[setup] downloading ${deb}"
    curl -fsSL --retry 3 -o "${tmp}/${deb}" "${DEB_BASE}/${deb}" \
        || fail "download failed: ${deb}"
    echo "${sha}  ${tmp}/${deb}" | sha256sum -c - >/dev/null \
        || fail "sha256 mismatch on ${deb}"
}

sqlite3_ensure() {
    if [ -x "${BIN}/sqlite3" ] \
       && [ "$("${BIN}/sqlite3" --version 2>/dev/null | awk '{print $1}')" = "$SQLITE3_UPSTREAM" ]; then
        echo "[setup] sqlite3 ${SQLITE3_UPSTREAM} already installed -> ${BIN}/sqlite3"
        return 0
    fi
    if sqlite3_present; then
        echo "[setup] sqlite3 ${SQLITE3_UPSTREAM} already present -> $(command -v sqlite3)"
        return 0
    fi

    mkdir -p "${BIN}" "${LIB}"
    local tmp
    tmp="$(mktemp -d)"
    fetch_deb "${SQLITE3_DEB}" "${SQLITE3_SHA256}" "${tmp}"
    fetch_deb "${LIBSQLITE_DEB}" "${LIBSQLITE_SHA256}" "${tmp}"
    dpkg-deb -x "${tmp}/${SQLITE3_DEB}" "${tmp}/sqlite3"
    dpkg-deb -x "${tmp}/${LIBSQLITE_DEB}" "${tmp}/libsqlite3"

    install -m 0755 "$(find "${tmp}/sqlite3" -name sqlite3 -type f | head -1)" \
        "${PREFIX}/bin/sqlite3.real"
    # the private shared library the pinned binary links against
    cp -a "${tmp}/libsqlite3"/usr/lib/*/libsqlite3.so* "${LIB}/" 2>/dev/null \
        || fail "libsqlite3-0 deb held no shared library"
    rm -rf "${tmp}"

    # a wrapper so the judge finds the pinned binary and its library on PATH
    cat > "${BIN}/sqlite3" <<EOF
#!/bin/sh
# pinned by judge/setup.sh: sqlite3 ${SQLITE3_PKG_VERSION}
LD_LIBRARY_PATH="${LIB}\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}" exec "${BIN}/sqlite3.real" "\$@"
EOF
    chmod 0755 "${BIN}/sqlite3"
    echo "[setup] installed ${BIN}/sqlite3 (${SQLITE3_PKG_VERSION})"
}

# ---------------------------------------------------------------------------
# dependencies for the download/extract path (only if actually needed)
# ---------------------------------------------------------------------------
tool_ensure() {
    local missing=()
    for t in curl sha256sum dpkg-deb; do
        command -v "$t" >/dev/null 2>&1 || missing+=("$t")
    done
    [ "${#missing[@]}" -eq 0 ] && return 0
    echo "[setup] installing ${missing[*]}"
    sudo apt-get update -qq || fail "apt-get update failed"
    sudo apt-get install -y -qq curl coreutils dpkg || fail "installing tools failed"
}

python_ensure
tool_ensure
sqlite3_ensure

# verify the sqlite3 the judge will use: the pinned install if present,
# otherwise whatever is on PATH
SQLITE3_BIN=""
if [ -x "${BIN}/sqlite3" ]; then
    SQLITE3_BIN="${BIN}/sqlite3"
elif command -v sqlite3 >/dev/null 2>&1; then
    SQLITE3_BIN="$(command -v sqlite3)"
else
    fail "sqlite3 is not available after setup"
fi
HAVE="$("${SQLITE3_BIN}" --version | awk '{print $1}')"
[ "$HAVE" = "$SQLITE3_UPSTREAM" ] \
    || fail "sqlite3 at ${SQLITE3_BIN} reports ${HAVE}, expected ${SQLITE3_UPSTREAM}"

# ---------------------------------------------------------------------------
# record what is actually installed (judge/VERSIONS.txt, per the standard)
# ---------------------------------------------------------------------------
JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
{
    echo "# recorded by judge/setup.sh (re-running setup leaves this file unchanged)"
    echo "sqlite3 ${SQLITE3_PKG_VERSION} (upstream $("${SQLITE3_BIN}" --version | awk '{print $1}'))"
    echo "python3 $(python3 -c 'import platform; print(platform.python_version())')"
} > "${JDIR}/VERSIONS.txt"

echo "[setup] done."
echo "  sqlite3 -> ${SQLITE3_BIN} ($("${SQLITE3_BIN}" --version | awk '{print $1}'))"
echo "  python3 -> $(command -v python3)"
echo "  versions -> ${JDIR}/VERSIONS.txt"
if [ "${SQLITE3_BIN}" = "${BIN}/sqlite3" ]; then
    echo
    echo "  add the pinned tools to PATH: export PATH=\"${BIN}:\$PATH\""
fi
