#!/usr/bin/env bash
# Install the pinned tools for the skill-ab-bench judge, idempotently.
#
# One tool is installed: jq 1.6-2.1+deb12u2 (Debian bookworm), from the
# Debian pool, sha256-checked.  It is what `run.py` and the README use to
# read the verdict JSON and the experiment record at the shell; the judge
# engine itself is Python >= 3.10, standard library only, and is not
# installed by anything.
#
# Tool choice, in the order the demo standard asks for:
#   1. release tarballs  -- jq publishes source tarballs only, and building
#      from source would need autoconf/oniguruma headers on the judge host;
#   2. pip wheels        -- jq 1.8.0 exists on PyPI, but the wheel links a
#      bundled libjq and its version string is not the jq version, which
#      makes "record the exact version" harder to verify;
#   3. Debian packages   -- what this script uses.  `apt-get update` is run
#      first because a fresh sandbox image ships with empty apt lists, and
#      the .deb itself is fetched from the pool by URL and checked, so the
#      install does not depend on the lists being complete.
#
# Everything lands in $HOME (jq's .deb installs /usr/bin/jq through dpkg,
# which needs root; the script is run with sudo where required).

set -euo pipefail

JQ_VERSION="1.6-2.1+deb12u2"
POOL="https://deb.debian.org/debian/pool/main"
DEBS=(
    "j/jq/jq_${JQ_VERSION}_amd64.deb"
    "j/jq/libjq1_${JQ_VERSION}_amd64.deb"
    "libo/libonig/libonig5_6.9.8-1_amd64.deb"
)
SHA256=(
    "f2303584378ac85f6d3a9ae8e46412196061681e81610d3b020abe4b5d389eb0"
    "f501b6349a3c2462af59e7a598ebd71e7889de46c9ddf852eb12ebeba7df21a2"
    "59ecfce6d88c7c4b09496ce182b3b8303e8e8477664e009b16ae83a09cd12be7"
)

# --force re-downloads and re-verifies even when the pinned version is
# already installed.  It exists so the download-and-check path is testable on
# a machine that already has jq (and so the receipt can show it running).
FORCE=0
for arg in "$@"; do
    case "$arg" in
        --force) FORCE=1 ;;
        *) echo "setup: unknown argument $arg" >&2; exit 2 ;;
    esac
done

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

sudo_cmd() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    else
        sudo "$@"
    fi
}

installed() {
    dpkg-query -W -f='${Version}' jq 2>/dev/null || true
}

echo "setup: checking the platform"
case "$(uname -s):$(uname -m)" in
    Linux:x86_64) ;;
    *) echo "setup: unsupported platform $(uname -s) $(uname -m) \
(supported: x86-64 Linux, the architecture the pinned .debs are built for)" >&2
       exit 2 ;;
esac

python3 - <<'EOF' || { echo "setup: python3 >= 3.10 required" >&2; exit 1; }
import sys
assert sys.version_info >= (3, 10), sys.version
EOF

if [ "$FORCE" -eq 0 ] && [ "$(installed)" = "$JQ_VERSION" ]; then
    echo "setup: jq $JQ_VERSION already installed (skipping download)"
else
    echo "setup: refreshing apt lists (a fresh image ships them empty)"
    sudo_cmd apt-get update -qq || true   # the .debs below do not need them

    tmpdir="$(mktemp -d)"
    trap 'rm -rf "$tmpdir"' EXIT
    i=0
    for rel in "${DEBS[@]}"; do
        name="$(basename "$rel")"
        echo "setup: downloading $name"
        curl -fsSL -o "$tmpdir/$name" "$POOL/$rel"
        echo "${SHA256[$i]}  $tmpdir/$name" | sha256sum -c - || {
            echo "setup: sha256 mismatch on $name" >&2
            exit 1
        }
        i=$((i + 1))
    done
    # Install in dependency order, from the checked files, so the result does
    # not depend on what apt's lists happen to know about.
    sudo_cmd dpkg -i "$tmpdir/libonig5_6.9.8-1_amd64.deb" \
                   "$tmpdir/libjq1_${JQ_VERSION}_amd64.deb" \
                   "$tmpdir/jq_${JQ_VERSION}_amd64.deb"
    actual="$(installed)"
    if [ "$actual" != "$JQ_VERSION" ]; then
        echo "setup: installed jq version '$actual' != '$JQ_VERSION'" >&2
        exit 1
    fi
fi

# The corpus and the reference answers are generated, not hand-kept: fail
# here, loudly, if the checked-in files have drifted from their generators.
echo "setup: checking the generated corpus and reference answers"
python3 -I "$JDIR/gen_reference.py" --check

echo "setup: tool versions"
jq --version
dpkg-query -W -f='jq debian package: ${Version}\n' jq
python3 --version
{
    echo "# skill-ab-bench judge: versions installed by judge/setup.sh"
    echo "# ($(uname -sm))"
    echo "jq $(jq --version | sed 's/^jq-//')"
    echo "jq debian package: $(dpkg-query -W -f='${Version}' jq)"
    echo "libjq1 debian package: $(dpkg-query -W -f='${Version}' libjq1)"
    echo "python3 $(python3 --version | awk '{print $2}')"
    echo "judge engine: python3 standard library only (no packages installed)"
} > "$JDIR/VERSIONS.txt"
echo "setup: wrote $JDIR/VERSIONS.txt"
echo "setup: done"
