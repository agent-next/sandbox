#!/usr/bin/env bash
# Install pinned tools for the background-coding-agent judge, idempotently
# into $HOME.  Every download is sha256-checked; nothing is fetched from
# `latest` and nothing is newer than two weeks before this demo merged.
#
#   ruff   0.16.9  (MIT)          lint gate
#   pytest 9.1.1   (MIT)          regression + acceptance gates
#     pluggy 1.6.0, iniconfig 2.3.1, packaging 26.3, pygments 2.21.0
#
# The judge engine itself is stdlib-only (Python >= 3.10) and needs none
# of this; only the test/lint gates shell out to the tools installed here.
set -euo pipefail

PYTEST_VERSION="9.1.1"
RUFF_VERSION="0.16.9"

# name  version  filename  sha256  url
WHEELS=(
"pluggy 1.6.0 pluggy-1.6.0-py3-none-any.whl e920276dd6813095e9377c0bc5566d94c932c33b27a3e3945d8389c374dd4746 https://files.pythonhosted.org/packages/54/20/4d324d65cc6d9205fabedc306948156824eb9f0ee1633355a8f7ec5c66bf/pluggy-1.6.0-py3-none-any.whl"
"iniconfig 2.3.1 iniconfig-2.3.1-py3-none-any.whl 9121e2c1fdb355232495be3194c8dfe87ccc2d5dee45947b78e68f499790d7a7 https://files.pythonhosted.org/packages/56/43/4ca9e49d27a1fcf6bece6f6aec0ea46bb9112489b93d4b688fb415457bdb/iniconfig-2.3.1-py3-none-any.whl"
"packaging 26.3 packaging-26.3-py3-none-any.whl d7193f7c8e4e93f444fde0262bf90af30e16fa0ad0ad44cb553c87339b23cd1c https://files.pythonhosted.org/packages/63/34/ba1c580383c9eada3711951fef0795c80b829a078d72188184bcab9dd527/packaging-26.3-py3-none-any.whl"
"pygments 2.21.0 pygments-2.21.0-py3-none-any.whl 2363c69b61c4a97c838da3b130dcd6468f4848992b21a82f2a63ec34377137d9 https://files.pythonhosted.org/packages/71/46/17f022dd3e953bf20a04a028a21ec746d942f8d2af30fa0f124fa0e6a684/pygments-2.21.0-py3-none-any.whl"
"pytest ${PYTEST_VERSION} pytest-9.1.1-py3-none-any.whl 37a86b45efb9a47a61a36449063e8e18d0cab3161329fc099eb21783169c4f0c https://files.pythonhosted.org/packages/24/25/1de2678b631f5a49215c6c96fff41ba892b0a34df68d6d80292b1b48aa7f/pytest-9.1.1-py3-none-any.whl"
"ruff ${RUFF_VERSION} ruff-0.16.9-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl a21713e629d3e5bdb2f5c2def1cc7f04f47fa8e1a7eb0571b4a28e1da64bc728 https://files.pythonhosted.org/packages/bc/b8/9c543074918061abbefc3bd139bee22de35abedb00dde0f2d27288838962/ruff-0.16.9-py3-none-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
)

ROOT="${MEASURECTL_JUDGE_HOME:-$HOME/.local/share/measurectl-judge}"
PYTEST_VENV="$ROOT/pytest-venv"
RUFF_VENV="$ROOT/ruff-venv"
JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

py_ok() { python3 -c 'import sys; assert sys.version_info >= (3, 10)' 2>/dev/null; }
py_ok || { echo "setup: python3 >= 3.10 required" >&2; exit 1; }

installed_pytest() {
    [ -x "$PYTEST_VENV/bin/pytest" ] && "$PYTEST_VENV/bin/pytest" --version 2>/dev/null | awk '{print $2}' || true
}
installed_ruff() {
    [ -x "$RUFF_VENV/bin/ruff" ] && "$RUFF_VENV/bin/ruff" --version 2>/dev/null | awk '{print $2}' || true
}

# The venvs are reused when they already hold the pinned versions: a
# self-test grades 14 deliveries, and rebuilding two venvs per grade
# (~60 s of pip each) would blow the run's time budget.  The wheels are
# re-verified against their sha256 pins on every run, so a cached venv is
# only reused after its contents were installed from verified wheels.
if [ "$(installed_pytest)" = "$PYTEST_VERSION" ] && \
   [ "$(installed_ruff)" = "$RUFF_VERSION" ]; then
    echo "setup: pytest $PYTEST_VERSION and ruff $RUFF_VERSION already installed (skipping download)"
else
    echo "setup: downloading pinned wheels into $ROOT"
    mkdir -p "$ROOT/wheels"
    for entry in "${WHEELS[@]}"; do
        # shellcheck disable=SC2086
        set -- $entry
        name="$1"; version="$2"; file="$3"; sha="$4"; url="$5"
        if [ -f "$ROOT/wheels/$file" ] && \
           echo "$sha  $ROOT/wheels/$file" | sha256sum -c - >/dev/null 2>&1; then
            echo "setup:   $name $version cached"
            continue
        fi
        curl -fsSL -o "$ROOT/wheels/$file.tmp" "$url"
        echo "$sha  $ROOT/wheels/$file.tmp" | sha256sum -c - >/dev/null || {
            echo "setup: sha256 mismatch on $file" >&2
            rm -f "$ROOT/wheels/$file.tmp"
            exit 1
        }
        mv "$ROOT/wheels/$file.tmp" "$ROOT/wheels/$file"
        echo "setup:   $name $version downloaded and sha256-verified"
    done

    echo "setup: creating venvs"
    python3 -m venv --clear "$PYTEST_VENV"
    python3 -m venv --clear "$RUFF_VENV"
    # --require-hashes: pip refuses any file whose sha256 is not in
    # judge/requirements.txt, so a corrupted or swapped wheel cannot land.
    "$PYTEST_VENV/bin/pip" install -q --no-index --find-links "$ROOT/wheels" \
        --require-hashes -r "$JDIR/requirements.txt"
    "$RUFF_VENV/bin/pip" install -q --no-index --find-links "$ROOT/wheels" \
        "ruff==$RUFF_VERSION"

    [ "$(installed_pytest)" = "$PYTEST_VERSION" ] || {
        echo "setup: pytest version $(installed_pytest) != $PYTEST_VERSION" >&2
        exit 1
    }
    [ "$(installed_ruff)" = "$RUFF_VERSION" ] || {
        echo "setup: ruff version $(installed_ruff) != $RUFF_VERSION" >&2
        exit 1
    }
fi

git --version >/dev/null || { echo "setup: git is required" >&2; exit 1; }

echo "setup: tool versions"
"$RUFF_VENV/bin/ruff" --version
"$PYTEST_VENV/bin/pytest" --version
python3 --version
{
    echo "# background-coding-agent judge: versions installed by judge/setup.sh"
    echo "# ($(uname -sm))"
    echo "ruff $("$RUFF_VENV/bin/ruff" --version | awk '{print $2}')"
    echo "pytest $("$PYTEST_VENV/bin/pytest" --version | awk '{print $2}')"
    echo "python3 $(python3 --version | awk '{print $2}')"
} > "$JDIR/VERSIONS.txt"
echo "setup: wrote $JDIR/VERSIONS.txt"
echo "setup: done"
