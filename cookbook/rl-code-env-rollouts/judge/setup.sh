#!/usr/bin/env bash
#
# setup.sh -- install the judge's pinned Python environment, idempotently.
#
# The judge needs exactly one third-party package: `gymnasium`, the API the
# artifact must satisfy.  Every wheel is downloaded at an exact version from
# PyPI, checked against the sha256 recorded here, and only then installed
# into a virtualenv under $HOME.  Nothing is fetched from a `latest` URL and
# no version is resolved at install time.
#
# The venv is what makes the pins real: installing into the system Python
# would let a wheel already present there satisfy an import without ever
# being checked.
#
# Tools, in the standard's order of preference:
#   1. pip wheels at exact versions, sha256-verified  (gymnasium + deps)
#   2. the host's own python3 -- the judge's own code and the artifact under
#      test use the standard library only, so no package is required for them.
# No release tarball and no Debian package are needed by this demo.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${HOME}/.rl-code-env-rollouts"
VENV="${PREFIX}/venv"
DL="${HOME}/.cache/rl-code-env-rollouts"
mkdir -p "${PREFIX}" "${DL}"

log() { printf 'setup: %s\n' "$*"; }

# --------------------------------------------------------------------------
# 0. A Python new enough for the artifact and the judge.
# --------------------------------------------------------------------------
PY="${PYTHON:-python3}"
"${PY}" - <<'EOF' || { echo "setup: python3 >= 3.10 required" >&2; exit 1; }
import sys
assert sys.version_info >= (3, 10), sys.version_info
EOF
PY_VER="$("${PY}" -c 'import sys; print("%d.%d.%d" % sys.version_info[:3])')"

# --------------------------------------------------------------------------
# 1. Pinned wheels, sha256-checked.
#
#    NAME==VERSION  FILENAME  SHA256
#
#    numpy's wheel is built per Python version, so several hashes are listed
#    and the one matching the running interpreter is the one checked; the
#    others are recorded so a different minor version is not silently
#    unverified.
# --------------------------------------------------------------------------
WHEELS=(
  "cloudpickle|3.1.2|cloudpickle-3.1.2-py3-none-any.whl|9acb47f6afd73f60dc1df93bb801b472f05ff42fa6c84167d25cb206be1fbf4a"
  "farama-notifications|0.0.6|farama_notifications-0.0.6-py3-none-any.whl|f84839188efa1ce5bb361c2a84881b2dc2c0d0d7fb661ff00421820170930935"
  "gymnasium|1.3.0|gymnasium-1.3.0-py3-none-any.whl|6b8c159a8540dcbcb221722d7efda24d78ebbcbc3bd2ea1c2611aa2a34471fc2"
  "typing-extensions|4.14.1|typing_extensions-4.14.1-py3-none-any.whl|d1e1e3b58374dc93031d6eda2420a48ea44a36c2b4766a4fdeb3710755731d76"
)

# numpy: tag -> sha256 (manylinux_2_17_x86_64, the wheel pip picks here)
NUMPY_VERSION="2.2.6"
numpy_wheel() {
    local tag="$1"
    echo "numpy-${NUMPY_VERSION}-${tag}-${tag}-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
}
numpy_sha() {
    case "$1" in
        cp310) echo "fc7b73d02efb0e18c000e9ad8b83480dfcd5dfd11065997ed4c6747470ae8915" ;;
        cp311) echo "ba10f8411898fc418a521833e014a77d3ca01c15b0c6cdcce6a0d2897e6dbbdf" ;;
        cp312) echo "fd83c01228a688733f1ded5201c678f0c53ecc1006ffbc404db9f7a899ac6249" ;;
        cp313) echo "1bc23a79bfabc5d056d106f9befb8d50c31ced2fbc70eedb8155aec74a45798f" ;;
        *)     echo "" ;;
    esac
}
PY_TAG="$("${PY}" -c 'import sys; print("cp%d%d" % sys.version_info[:2])')"
NUMPY_WHEEL="$(numpy_wheel "${PY_TAG}")"
NUMPY_SHA="$(numpy_sha "${PY_TAG}")"
if [ -z "${NUMPY_SHA}" ]; then
    echo "setup: no pinned numpy wheel for interpreter tag ${PY_TAG}; add one" >&2
    exit 1
fi

# --------------------------------------------------------------------------
# 2. Virtualenv.
# --------------------------------------------------------------------------
if [ ! -x "${VENV}/bin/python" ]; then
    log "creating virtualenv ${VENV}"
    "${PY}" -m venv "${VENV}"
else
    log "virtualenv already present"
fi
VENV_PY="${VENV}/bin/python"

# --------------------------------------------------------------------------
# 3. Download + verify + install, one wheel at a time.
#
#    pip is asked for the exact version as a wheel only; whatever it fetches
#    is then checked against the sha256 pinned above.  A version bump or a
#    rebuilt wheel therefore fails here rather than installing silently.
#    The verified wheels are then installed with --no-index, so the install
#    step cannot reach the network and cannot substitute a different build.
# --------------------------------------------------------------------------
STAGE="${DL}/wheels-${PY_TAG}"
rm -rf "${STAGE}"
mkdir -p "${STAGE}"

# Fetch every pinned wheel, ignoring what is already installed, then verify.
PINNED=(
    "gymnasium==1.3.0"
    "numpy==${NUMPY_VERSION}"
    "cloudpickle==3.1.2"
    "typing-extensions==4.14.1"
    "farama-notifications==0.0.6"
)
log "downloading ${#PINNED[@]} pinned wheels for ${PY_TAG}"
"${VENV_PY}" -m pip download --quiet --disable-pip-version-check \
    --only-binary=:all: --no-deps -d "${STAGE}" "${PINNED[@]}"

# Verify each downloaded wheel against its pin.  Anything unexpected -- a
# missing wheel, an extra wheel, a hash that does not match -- is fatal.
verified_count=0
for path in "${STAGE}"/*.whl; do
    file="$(basename "${path}")"
    want=""
    for entry in "${WHEELS[@]}"; do
        IFS='|' read -r _name _ver f s <<<"${entry}"
        [ "${f}" = "${file}" ] && want="${s}"
    done
    [ "${file}" = "${NUMPY_WHEEL}" ] && want="${NUMPY_SHA}"
    if [ -z "${want}" ]; then
        echo "setup: unexpected wheel ${file} -- not in the pinned set" >&2
        exit 1
    fi
    echo "${want}  ${path}" | sha256sum -c - >/dev/null \
        || { echo "setup: sha256 mismatch for ${file}" >&2; exit 1; }
    log "verified ${file}"
    verified_count=$((verified_count + 1))
done
if [ "${verified_count}" -ne 5 ]; then
    echo "setup: verified ${verified_count} wheels, expected 5" >&2
    exit 1
fi

log "installing pinned wheels into ${VENV}"
"${VENV_PY}" -m pip install --quiet --no-index --find-links "${STAGE}" \
    --disable-pip-version-check "${PINNED[@]}"

# --------------------------------------------------------------------------
# 4. Prove the installed set is the pinned set, not something that happened
#    to be on the path.
# --------------------------------------------------------------------------
"${VENV_PY}" - <<'EOF' || { echo "setup: pinned import check failed" >&2; exit 1; }
import gymnasium
assert gymnasium.__version__ == "1.3.0", gymnasium.__version__
import numpy
assert numpy.__version__ == "2.2.6", numpy.__version__
EOF

# --------------------------------------------------------------------------
# 5. Record what is actually installed, next to the scripts that installed it.
# --------------------------------------------------------------------------
{
    echo "# VERSIONS.txt -- recorded by judge/setup.sh"
    echo "# One entry per tool this demo depends on: the pinned version and the"
    echo "# sha256 the download was verified against, then the tool's own"
    echo "# --version output as installed."
    echo
    echo "python3 ${PY_VER} (host interpreter that built the venv)"
    echo
    echo "gymnasium 1.3.0 (PyPI wheel, MIT License)"
    echo "  url    : https://pypi.org/project/gymnasium/1.3.0/"
    echo "  sha256 : 6b8c159a8540dcbcb221722d7efda24d78ebbcbc3bd2ea1c2611aa2a34471fc2"
    echo "  venv   : ${VENV}"
    echo
    echo "numpy ${NUMPY_VERSION} (PyPI wheel, BSD-3-Clause)"
    echo "  wheel  : ${NUMPY_WHEEL}"
    echo "  sha256 : ${NUMPY_SHA}"
    echo
    echo "cloudpickle 3.1.2 (BSD-3-Clause)"
    echo "  sha256 : 9acb47f6afd73f60dc1df93bb801b472f05ff42fa6c84167d25cb206be1fbf4a"
    echo
    echo "typing-extensions 4.14.1 (PSF-2.0)"
    echo "  sha256 : d1e1e3b58374dc93031d6eda2420a48ea44a36c2b4766a4fdeb3710755731d76"
    echo
    echo "farama-notifications 0.0.6 (MIT License)"
    echo "  sha256 : f84839188efa1ce5bb361c2a84881b2dc2c0d0d7fb661ff00421820170930935"
    echo
    echo "pip freeze (the venv as installed):"
    "${VENV_PY}" -m pip freeze 2>/dev/null | sed 's/^/  /'
    echo
    echo "host tools used by the judge (standard library only):"
    echo "  python3 : $("${PY}" --version 2>&1)"
    echo "  bash    : ${BASH_VERSION}"
} > "${HERE}/VERSIONS.txt"

# A machine-readable pointer, so grade.sh and selftest.sh find the venv
# without hard-coding $HOME.
cat > "${PREFIX}/env.sh" <<EOF
# sourced by judge/grade.sh and judge/selftest.sh
export RL_CODE_ENV_VENV="${VENV}"
export RL_CODE_ENV_PY="${VENV_PY}"
EOF

log "wrote ${HERE}/VERSIONS.txt"
log "wrote ${PREFIX}/env.sh"
log "done (gymnasium 1.3.0, numpy ${NUMPY_VERSION}, python ${PY_VER})"
