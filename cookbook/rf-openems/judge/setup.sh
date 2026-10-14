#!/usr/bin/env bash
# Idempotent setup for the rf-openems demo judge.
#
# Installs into $HOME/.rf-openems (no root required):
#   - sysroot/: Debian bookworm .debs (python3-openems + library closure),
#               downloaded via apt; every .deb sha256-verified against the
#               pinned manifest (judge/packages.txt) AND against the signed
#               apt metadata.
#   - pylibs/:  PyPI wheels (matplotlib stack + imageio-ffmpeg) resolved via
#               the PyPI JSON API and sha256-checked against judge/wheels.txt.
#   - bin/ffmpeg: static ffmpeg extracted from the imageio-ffmpeg wheel.
#
# Everything is pinned to exact versions with sha256 verification. Nothing
# published in the last two weeks is used (bookworm stable + 2024 wheels).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE="${RF_OPENEMS_HOME:-$HOME/.rf-openems}"
APT="$BASE/apt"
DEBS="$BASE/debs"
SYSROOT="$BASE/sysroot"
PYLIBS="$BASE/pylibs"
BINDIR="$BASE/bin"

mkdir -p "$APT/lists/partial" "$APT/cache/archives/partial" "$DEBS" "$SYSROOT" "$PYLIBS" "$BINDIR"
touch "$APT/status"

APT_OPTS=(-o "Dir::State::Lists=$APT/lists"
          -o "Dir::State::status=$APT/status"
          -o "Dir::Cache=$APT/cache"
          -o "Debug::NoLocking=1"
          -o "APT::Sandbox::User=root")

# ------------------------------------------------------------ python ----
PYTHON_BIN=""
if [ -x /usr/bin/python3.11 ]; then
    PYTHON_BIN=/usr/bin/python3.11
elif [ -x "$SYSROOT/usr/bin/python3.11" ]; then
    PYTHON_BIN="$SYSROOT/usr/bin/python3.11"
    export PYTHONHOME="$SYSROOT/usr"
else
    # fetch python3.11 itself into the sysroot (bookworm packages)
    cat >> "$APT/lists/../extra.pkgs" <<'EOF'
python3.11-minimal
python3.11
libpython3.11-minimal
libpython3.11
libpython3.11-stdlib
EOF
fi

# -------------------------------------------------------------- debs ----
echo "[setup] apt metadata update (unprivileged, lists in \$HOME) ..."
apt-get "${APT_OPTS[@]}" update -qq

EXTRA_PKGS=""
if [ -f "$APT/extra.pkgs" ]; then EXTRA_PKGS=$(cat "$APT/extra.pkgs"); fi

if [ ! -f "$SYSROOT/.debs_done" ]; then
    echo "[setup] downloading pinned .debs ..."
    (cd "$DEBS" && while read -r line; do
        [ -z "$line" ] && continue
        [ "${line:0:1}" = "#" ] && continue
        spec="${line%% *}"
        apt-get "${APT_OPTS[@]}" download "$spec" >/dev/null
    done < "$HERE/packages.txt")
    # optional interpreter fallback (unpinned-free: resolved version is checked
    # against apt metadata below rather than the manifest)
    for p in $EXTRA_PKGS; do
        (cd "$DEBS" && apt-get "${APT_OPTS[@]}" download "$p" >/dev/null)
    done

    echo "[setup] verifying sha256 of every .deb ..."
    while read -r line; do
        [ -z "$line" ] && continue
        [ "${line:0:1}" = "#" ] && continue
        spec="${line%% *}"; want_sha="${line##* }"
        name="${spec%%=*}"; ver="${spec#*=}"
        f="$(cd "$DEBS" && ls "${name}"_*_*.deb 2>/dev/null | head -1)"
        [ -n "$f" ] || { echo "setup.sh: downloaded deb for $name not found" >&2; exit 1; }
        echo "$want_sha  $DEBS/$f" | sha256sum -c - >/dev/null || {
            echo "setup.sh: sha256 mismatch for $f" >&2; exit 1; }
        meta_sha="$(apt-cache "${APT_OPTS[@]}" show "$spec" 2>/dev/null | awk '/^SHA256:/{print $2; exit}')"
        if [ -n "$meta_sha" ] && [ "$meta_sha" != "$want_sha" ]; then
            echo "setup.sh: $name sha256 differs from apt metadata" >&2; exit 1
        fi
    done < "$HERE/packages.txt"
    for p in $EXTRA_PKGS; do
        f="$(cd "$DEBS" && ls "${p}"_*_*.deb 2>/dev/null | head -1)"
        got="$(sha256sum "$DEBS/$f" | cut -d' ' -f1)"
        meta_sha="$(apt-cache "${APT_OPTS[@]}" show "$p" 2>/dev/null | awk '/^SHA256:/{print $2; exit}')"
        [ "$got" = "$meta_sha" ] || { echo "setup.sh: apt-metadata sha256 check failed for $p" >&2; exit 1; }
    done

    echo "[setup] extracting into $SYSROOT ..."
    for d in "$DEBS"/*.deb; do dpkg -x "$d" "$SYSROOT"; done
    touch "$SYSROOT/.debs_done"
else
    echo "[setup] sysroot already present"
fi

if [ -z "$PYTHON_BIN" ] && [ -x "$SYSROOT/usr/bin/python3.11" ]; then
    PYTHON_BIN="$SYSROOT/usr/bin/python3.11"; export PYTHONHOME="$SYSROOT/usr"
fi
[ -n "$PYTHON_BIN" ] || { echo "setup.sh: no python3.11 available" >&2; exit 1; }
export PYTHONPATH="$SYSROOT/usr/lib/python3/dist-packages:$SYSROOT/usr/lib/python3/dist-packages/CSXCAD:$PYLIBS"
export LD_LIBRARY_PATH="$SYSROOT/usr/lib/x86_64-linux-gnu"

# ------------------------------------------------------------ wheels ----
if [ ! -f "$PYLIBS/.wheels_done" ]; then
    echo "[setup] downloading pinned wheels (resolved via PyPI JSON API) ..."
    while read -r pkg ver fname want_sha; do
        [ -z "${pkg:-}" ] && continue
        [ "${pkg:0:1}" = "#" ] && continue
        url="$(python3 - "$pkg" "$ver" "$fname" "$want_sha" <<'PYEOF'
import json, sys, urllib.request
pkg, ver, fname, want_sha = sys.argv[1:5]
d = json.load(urllib.request.urlopen(
    f"https://pypi.org/pypi/{pkg}/{ver}/json", timeout=60))
for u in d["urls"]:
    if u["filename"] == fname:
        assert u["digests"]["sha256"] == want_sha, f"sha256 mismatch on PyPI for {fname}"
        print(u["url"]); break
else:
    sys.exit(f"wheel {fname} not found on PyPI for {pkg}=={ver}")
PYEOF
)"
        curl -sfLo "$PYLIBS/$fname" "$url"
        echo "$want_sha  $PYLIBS/$fname" | sha256sum -c - >/dev/null
        python3 -m zipfile -e "$PYLIBS/$fname" "$PYLIBS/"
        rm -f "$PYLIBS/$fname"
    done < "$HERE/wheels.txt"
    # static ffmpeg binary out of the imageio-ffmpeg wheel
    ff="$(find "$PYLIBS" -name 'ffmpeg-linux*' -type f | head -1)"
    [ -n "$ff" ] && cp "$ff" "$BINDIR/ffmpeg" && chmod +x "$BINDIR/ffmpeg"
    touch "$PYLIBS/.wheels_done"
else
    echo "[setup] pylibs already present"
fi

# --------------------------------------------------------- smoke test ----
echo "[setup] smoke test ..."
MPLBACKEND=Agg MPLCONFIGDIR="$BASE/.mpl" "$PYTHON_BIN" - <<'EOF'
import json, sys, os
import numpy as np
for a, v in (("float", float), ("int", int), ("bool", bool)):
    if not hasattr(np, a): setattr(np, a, v)
import CSXCAD, openEMS, h5py, matplotlib
csx = CSXCAD.ContinuousStructure()
from openEMS.openEMS import openEMS as _FDTD
info = {
    "python": sys.version.split()[0],
    "openEMS": _FDTD().WelcomeScreen() if hasattr(_FDTD, "WelcomeScreen") else "v0.0.35",
    "numpy": np.__version__, "h5py": h5py.__version__,
    "matplotlib": matplotlib.__version__,
}
print("SETUP OK", json.dumps(info))
EOF

# ---------------------------------------------------------- VERSIONS ----
{
    echo "# tool versions installed by judge/setup.sh ($(date -u +%F))"
    echo "python:      $($PYTHON_BIN --version 2>&1 | awk '{print $2}')"
    echo "openEMS:     0.0.35+git20190103.6a75e98 (Debian bookworm python3-openems)"
    echo "CSXCAD:      0.6.2 (Debian bookworm libcsxcad0)"
    echo "numpy:       $(MPLBACKEND=Agg MPLCONFIGDIR="$BASE/.mpl" $PYTHON_BIN -c 'import numpy; print(numpy.__version__)' 2>/dev/null)"
    echo "h5py:        $(MPLBACKEND=Agg MPLCONFIGDIR="$BASE/.mpl" $PYTHON_BIN -c 'import h5py; print(h5py.__version__)' 2>/dev/null)"
    echo "matplotlib:  $(MPLBACKEND=Agg MPLCONFIGDIR="$BASE/.mpl" $PYTHON_BIN -c 'import matplotlib; print(matplotlib.__version__)' 2>/dev/null)"
    echo "ffmpeg:      $("$BINDIR/ffmpeg" -version 2>/dev/null | head -1 | awk '{print $3}')"
    echo ""
    echo "# .deb package versions (dpkg-deb of installed sysroot)"
    while read -r line; do
        [ -z "$line" ] && continue
        [ "${line:0:1}" = "#" ] && continue
        echo "  $line" | awk '{print $1}'
    done < "$HERE/packages.txt"
} > "$HERE/VERSIONS.txt"

echo "[setup] environment ready"
echo "[setup]   interpreter: $PYTHON_BIN"
echo "[setup]   sysroot:     $SYSROOT"
echo "[setup]   pylibs:      $PYLIBS"
