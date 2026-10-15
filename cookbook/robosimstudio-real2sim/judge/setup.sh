#!/usr/bin/env bash
# Install the pinned toolchain this demo needs, into $HOME, idempotently.
#
# Two halves, because the demo runs in two places:
#
#   1. the judge's own Python packages (numpy, for the gate arithmetic), from
#      judge/requirements.lock, sha256-checked;
#   2. the RoboSimStudio stack for the *sandbox* that will step the physics,
#      from judge/wheels.sha256, into $HOME/rsssite.
#
# Half 2 is what the GPU lease cannot get for itself: it has no network, so the
# wheels are shipped in through the lease's exec payloads and installed with
# `pip install --no-index --no-deps --target`. On a machine with a network
# (this CPU sandbox, or the runner that builds the payload) the same wheels are
# fetched from PyPI at the exact pinned versions and checked against the same
# sha256 file, so both paths install byte-identical files.
#
#   judge/setup.sh [--wheels DIR] [--target DIR] [--build]
#
# --build additionally builds the two wheels PyPI does not carry
# (robosimstudio itself, and pyroki at its pinned git revision).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
wheels="${RSS_WHEELS:-$HOME/rss-wheels}"
target="${RSS_SITE:-$HOME/rsssite}"
build=0
while [ $# -gt 0 ]; do
    case "$1" in
        --wheels) wheels="$2"; shift 2 ;;
        --target) target="$2"; shift 2 ;;
        --build) build=1; shift ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

RSS_SHA=73739abe212f963e8a9f5862b27bca370df091a7
PYROKI_SHA=95afccc22658c461ab1042a048ae4e9c24bc2a47
JAXLS_SHA=50a58be88c5ef74532f09e3f55268b4f02c490e3

mkdir -p "$wheels" "$target"

if [ "$build" = 1 ]; then
    echo "== building the wheels PyPI does not carry =="
    work="$(mktemp -d)"
    git clone -q https://github.com/robosimstudio/robosimstudio.git "$work/rss"
    git -C "$work/rss" checkout -q "$RSS_SHA"
    python3 -m pip wheel --no-deps -w "$wheels" "$work/rss"

    git clone -q https://github.com/chungmin99/pyroki.git "$work/pyroki"
    git -C "$work/pyroki" checkout -q "$PYROKI_SHA"
    python3 -m pip wheel --no-deps -w "$wheels" "$work/pyroki"

    git clone -q https://github.com/brentyi/jaxls.git "$work/jaxls"
    git -C "$work/jaxls" checkout -q "$JAXLS_SHA"
    python3 -m pip wheel --no-deps -w "$wheels" "$work/jaxls"
    rm -rf "$work"
fi

echo "== fetching the pinned wheels =="
missing=()
while read -r sha name; do
    [ -f "$wheels/$name" ] && continue
    missing+=("$name")
done < "$here/wheels.sha256"

if [ "${#missing[@]}" -gt 0 ]; then
    # The wheels PyPI carries are fetched by exact version and platform; the
    # three built above are skipped, since `--build` is how they get here.
    python3 - "$here/wheels.sha256" "$wheels" "${missing[@]}" <<'PY'
import os, subprocess, sys
manifest, wheels = sys.argv[1], sys.argv[2]
names = sys.argv[3:]
for name in names:
    if name.startswith(("robosimstudio-", "pyroki-", "jaxls-")):
        continue  # built, not fetched
    stem = name.split("-py3")[0].split("-cp3")[0]
    pkg, _, version = stem.rpartition("-")
    subprocess.run(
        # The lease is Python 3.13 on manylinux; without this a host running
        # 3.12 would fetch cp312 wheels that never match wheels.sha256.
        [sys.executable, "-m", "pip", "download", "--no-deps", "--only-binary=:all:",
         "--python-version", "3.13",
         "--platform", "manylinux2014_x86_64", "--platform", "manylinux_2_28_x86_64",
         "--platform", "manylinux_2_27_x86_64", "--platform", "manylinux_2_24_x86_64",
         "--platform", "manylinux_2_17_x86_64",
         "--dest", wheels, f"{pkg}=={version}"],
        check=True,
    )
PY
fi

echo "== verifying sha256 =="
( cd "$wheels" && sha256sum -c "$here/wheels.sha256" --quiet ) || {
    echo "a wheel does not match judge/wheels.sha256" >&2
    exit 1
}
echo "all $(wc -l < "$here/wheels.sha256") wheels verified"

echo "== installing into $target =="
python3 -m pip install --no-index --no-deps --target "$target" \
    --find-links "$wheels" robosimstudio newton mujoco mujoco-warp warp-lang numpy
echo "installed; PYTHONPATH=$target"
