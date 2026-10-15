#!/bin/bash
# doc-extract-convert — install the judge's pinned, sha256-checked tools.
#
# Idempotent: safe to run repeatedly; every step checks before it installs.
# Nothing here is "latest": the Debian .deb versions are the bookworm
# release versions and the Pillow wheel is the pinned 11.3.0.
#
# Tools and exact versions (recorded into judge/VERSIONS.txt by this script):
#   tesseract-ocr 5.3.0-2         (bookworm)  OCR engine
#   tesseract-ocr-eng 1:4.1.0-2   (bookworm)  English language data
#   fonts-dejavu-core 2.37-6      (bookworm)  fonts the corpus is rendered in
#   Pillow 11.3.0                             corpus rendering / G2 re-measure
#
# The apt lists on this image may be empty, so "apt-get update" is verified
# to have actually fetched lists (a stale/empty cache would silently pin to
# whatever is lying around) before anything is installed.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- apt packages ---------------------------------------------------------
need_install=()
for pkg in tesseract-ocr tesseract-ocr-eng fonts-dejavu-core; do
    if dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q "install ok installed"; then
        echo "[setup] $pkg already installed"
    else
        need_install+=("$pkg")
    fi
done

if [ "${#need_install[@]}" -gt 0 ]; then
    echo "[setup] refreshing apt lists"
    sudo apt-get update -qq
    n_lists=$(ls /var/lib/apt/lists/*Packages* 2>/dev/null | wc -l)
    if [ "$n_lists" -eq 0 ]; then
        echo "[setup] ERROR: apt-get update fetched no package lists" >&2
        exit 1
    fi

    # Resolve the full dependency closure into our own cache dir (apt's _apt
    # user needs a world-writable dir), sha256-check every .deb that arrives
    # against judge/package-sha256.txt, then install exactly the checked files.
    cachedir="$(mktemp -d)"
    trap 'sudo rm -rf "$cachedir"' EXIT
    mkdir "$cachedir/partial"
    chmod -R 777 "$cachedir"
    sudo apt-get --yes --no-install-recommends --download-only \
        -o Dir::Cache::archives="$cachedir" \
        install --reinstall "${need_install[@]}" >/dev/null 2>&1
    sudo chown -R "$(id -u)" "$cachedir"

    bad=0
    debs=("$cachedir"/*.deb)
    for deb in "${debs[@]}"; do
        base=$(basename "$deb")
        want=$(grep "  $base$" "$here/package-sha256.txt" | awk '{print $1}')
        if [ -z "$want" ]; then
            echo "[setup] ERROR: $base is not pinned in judge/package-sha256.txt" >&2
            bad=1
        else
            got=$(sha256sum "$deb" | awk '{print $1}')
            if [ "$got" != "$want" ]; then
                echo "[setup] ERROR: sha256 mismatch for $base: $got != $want" >&2
                bad=1
            fi
        fi
    done
    [ "$bad" -eq 0 ] || exit 1

    sudo dpkg -i --skip-same-version "${debs[@]}" >/dev/null
fi

# --- Pillow wheel ---------------------------------------------------------
if python3 -c "import PIL; import sys; sys.exit(0 if PIL.__version__ == '11.3.0' else 1)" 2>/dev/null; then
    echo "[setup] Pillow 11.3.0 already installed"
else
    wheel_dir="$(mktemp -d)"
    trap "rm -rf $wheel_dir" EXIT
    pip download --no-deps --only-binary=:all: -q -d "$wheel_dir" "Pillow==11.3.0"

    wheel=$(ls "$wheel_dir"/pillow-11.3.0-*.whl)
    got=$(sha256sum "$wheel" | awk '{print $1}')
    base=$(basename "$wheel")
    if ! grep -q "^Pillow==11.3.0 .*$got" "$here/requirements.txt"; then
        echo "[setup] ERROR: sha256 of $base not pinned in requirements.txt ($got)" >&2
        exit 1
    fi
    pip install -q --no-deps "$wheel"
fi

# --- record what is actually installed -------------------------------------
versions="$(mktemp)"
{
    echo "tesseract-ocr $(dpkg-query -W -f='${Version}' tesseract-ocr)"
    echo "tesseract-ocr-eng $(dpkg-query -W -f='${Version}' tesseract-ocr-eng)"
    echo "fonts-dejavu-core $(dpkg-query -W -f='${Version}' fonts-dejavu-core)"
    echo "python3 $(python3 --version 2>&1)"
    echo "Pillow $(python3 -c 'import PIL; print(PIL.__version__)')"
} > "$versions" 2>/dev/null || true
cp "$versions" "$here/VERSIONS.txt"
rm -f "$versions"

echo "[setup] all tools present; versions recorded to judge/VERSIONS.txt"
cat "$here/VERSIONS.txt"
