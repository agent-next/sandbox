#!/usr/bin/env bash
# cookbook/cnc-gcode: install pinned judge tools idempotently into $HOME.
#
# Installs (into $HOME/.cnc-gcode/venv):
#   - numpy 2.5.3, sha256-pinned wheels from judge/requirements.txt
# The rest of the judge (G-code parser, heightmap simulator, gates) is Python
# 3.12 stdlib + numpy.  Safe to re-run; exact versions, never "latest".
#
# Usage: bash judge/setup.sh
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${HOME}/.cnc-gcode/venv"
PY="${VENV}/bin/python"

python3 - <<'EOF' || { echo "setup: python3 >= 3.12 required" >&2; exit 1; }
import sys
assert sys.version_info >= (3, 12), sys.version
EOF

if [ -x "$PY" ] && "$PY" -c "import numpy" >/dev/null 2>&1 \
   && [ "$("$PY" -c "import numpy;print(numpy.__version__)")" = "2.5.3" ]; then
    echo "setup: numpy 2.5.3 already installed in ${VENV} (skipping)"
else
    echo "setup: creating venv + installing pinned numpy"
    rm -rf "$VENV"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --no-cache-dir --upgrade "pip==25.0.1" >/dev/null
    "$VENV/bin/pip" install --no-cache-dir --require-hashes \
        -r "${JDIR}/requirements.txt"
fi

for tool in curl dpkg-deb sha256sum; do
    command -v "$tool" >/dev/null 2>&1 || {
        echo "setup: $tool is required to install the rs274 reference" >&2; exit 1; }
done

# --- reference cross-check tool: LinuxCNC standalone rs274 interpreter -----
# Installed rootless: three pinned Debian .debs are downloaded by URL, sha256-
# verified against judge/reference_packages.tsv, and extracted with dpkg-deb -x
# into $HOME/.cnc-gcode/rs274 (no apt, no root).
RS274_DIR="${HOME}/.cnc-gcode/rs274"
RS274_BIN="${RS274_DIR}/root/usr/bin/rs274"

rs274_ok() {
    [ -x "$RS274_BIN" ] || return 1
    LD_LIBRARY_PATH="${RS274_DIR}/root/usr/lib/x86_64-linux-gnu:${RS274_DIR}/root/usr/lib:${RS274_DIR}/root/usr/lib/linuxcnc" \
        "$RS274_BIN" -h </dev/null >/dev/null 2>&1
    # rs274 exits non-zero on -h; success == it ran at all (no loader error)
}

if [ -x "$RS274_BIN" ]; then
    echo "setup: rs274 already installed in ${RS274_DIR} (skipping download)"
else
    echo "setup: downloading pinned debs for LinuxCNC rs274 (sha256-checked)"
    rm -rf "$RS274_DIR"
    mkdir -p "$RS274_DIR/debs" "$RS274_DIR/root"
    while IFS=$'\t' read -r url sha pkg; do
        case "$url" in ''|\#*) continue ;; esac
        f="${RS274_DIR}/debs/${url##*/}"
        curl -fsS --retry 3 -o "$f" "$url"
        echo "${sha}  ${f}" | sha256sum -c - >/dev/null \
            || { echo "setup: sha256 mismatch for $url" >&2; exit 1; }
        dpkg-deb -x "$f" "${RS274_DIR}/root"
        echo "setup: extracted ${pkg}"
    done < "${JDIR}/reference_packages.tsv"
    [ -x "$RS274_BIN" ] || { echo "setup: rs274 missing after extract" >&2; exit 1; }
fi

echo "setup: tool versions"
"$PY" --version
"$PY" -c "import numpy;print('numpy', numpy.__version__)"
RS274_VERSION="$("$RS274_BIN" -h </dev/null 2>&1 | head -1 || true)"
LD_LIBRARY_PATH="${RS274_DIR}/root/usr/lib/x86_64-linux-gnu:${RS274_DIR}/root/usr/lib:${RS274_DIR}/root/usr/lib/linuxcnc" \
    "$RS274_BIN" -h </dev/null >/dev/null 2>&1 || true
echo "rs274 (LinuxCNC) 2.9.0~pre1+git20230208.f1270d6ed7-1+deb12u2 (Debian bookworm)"
{
    echo "# cnc-gcode judge: versions installed by judge/setup.sh"
    echo "# ($(uname -sm))"
    "$PY" --version
    "$PY" -c "import numpy;print('numpy', numpy.__version__)"
    echo "rs274 (LinuxCNC) 2.9.0~pre1+git20230208.f1270d6ed7-1+deb12u2 (Debian bookworm)"
    echo "libboost-python1.74.0 1.74.0+ds1-21"
    echo "libpython3.11 3.11.2-6+deb12u9"
} > "$JDIR/VERSIONS.txt"
echo "setup: wrote $JDIR/VERSIONS.txt"
echo "setup: done"
