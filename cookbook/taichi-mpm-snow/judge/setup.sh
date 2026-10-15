#!/usr/bin/env bash
#
# setup.sh -- install the toolchain this demo judges with, pinned and
# sha256-checked, into $HOME.  Idempotent: a second run is a no-op.
#
# The judge needs:
#   1. CPython (the system python3; nothing to install beyond the
#      stdlib -- the judge itself is stdlib-only).
#   2. A pinned virtualenv at $HOME/.taichi-mpm-venv with:
#        taichi==1.7.4, numpy, and every transitive dependency pinned by
#        exact version + sha256 (judge/requirements.txt).
#      `pip install --require-hashes` refuses anything that does not
#      match, so a later point release of any dependency fails loudly
#      here instead of silently changing the solver under the judge.
#
# Nothing is downloaded from a `latest` URL; every version is spelled
# out.  Releases are at least two weeks old (taichi 1.7.4 was published
# 2025-07-31).

set -euo pipefail

VENV="${HOME}/.taichi-mpm-venv"
MARK="${VENV}/.installed"
JUDGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REQ="${JUDGE_DIR}/requirements.txt"

log() { printf 'setup: %s\n' "$*"; }

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

if [[ $FORCE -eq 0 && -f "$MARK" && -x "${VENV}/bin/python3" ]]; then
    if grep -q '^taichi==1.7.4$' "$MARK"; then
        log "taichi 1.7.4 already installed in ${VENV}"
        exit 0
    fi
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "setup: python3 not found" >&2
    exit 1
fi

PY_MINOR="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
case "$PY_MINOR" in
    3.10|3.11|3.12|3.13) ;;
    *) echo "setup: python3 ${PY_MINOR} not supported by taichi 1.7.4 (needs >=3.9,<4)" >&2
       exit 1 ;;
esac

log "creating virtualenv at ${VENV}"
python3 -m venv "${VENV}"
"${VENV}/bin/pip" install --quiet --upgrade pip

log "installing pinned requirements (sha256-checked)"
"${VENV}/bin/pip" install --require-hashes -r "${REQ}"

# Verify the interpreter can import taichi on the CPU backend.
log "verifying taichi imports on the CPU backend"
TI_WANT=1.7.4
"${VENV}/bin/python3" - "$TI_WANT" <<'PY'
import sys, os
os.environ.setdefault('TI_LOG_LEVEL', 'error')
import taichi as ti
want = sys.argv[1]
ver = '.'.join(str(x) for x in ti.__version__) if \
    isinstance(ti.__version__, tuple) else ti.__version__
if ver != want:
    print(f'setup: taichi {ver} != {want}', file=sys.stderr)
    sys.exit(1)
ti.init(arch=ti.cpu)
print(f'setup: taichi {ver} OK on cpu')
# Taichi's LLVM teardown can segfault at interpreter exit on some
# hosts (rare, unrelated to the verdict); skip it once the check passed.
sys.stdout.flush(); sys.stderr.flush()
os._exit(0)
PY

cat > "$MARK" <<EOF
taichi==1.7.4
installed_at=$(date -Iseconds)
EOF

# Record what is on the path, so the receipt is reproducible.
{
    echo "# VERSIONS.txt -- recorded by judge/setup.sh"
    echo "# One entry per tool the demo depends on: the pinned version,"
    echo "# and the tool's own --version output as actually installed."
    echo
    echo "python3"
    python3 --version 2>&1 | sed 's/^/  /'
    echo
    echo "virtualenv ${VENV}"
    "${VENV}/bin/pip" freeze 2>/dev/null | sed 's/^/  /'
} > "${JUDGE_DIR}/VERSIONS.txt"

log "wrote ${JUDGE_DIR}/VERSIONS.txt"
log "done"
