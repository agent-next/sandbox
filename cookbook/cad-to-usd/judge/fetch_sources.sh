#!/usr/bin/env bash
# judge/fetch_sources.sh — fetch the pinned RC-Car-CAD sources into
# <target-dir>/sources/ and verify every sha256 against judge/sources.txt.
# Never writes anything to the repo; never trusts the download (digest
# check first, then move into place).
#
# Usage: bash judge/fetch_sources.sh <target-dir>
# Exit codes: 0 ok, 1 fetch/verify failure.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="https://github.com/NVIDIA-Omniverse/RC-Car-CAD"
COMMIT="407bd553ee57668ceb58d81ffd7f4d617dee3dfa"

target="${1:?usage: fetch_sources.sh <target-dir>}"
mkdir -p "$target/sources"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/cad2usd-src.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

while IFS='|' read -r sha path key; do
    [[ -z "$sha" || "$sha" == \#* ]] && continue
    dest="$target/sources/$path"
    if [[ -f "$dest" ]] && echo "$sha  $dest" | sha256sum -c --quiet -; then
        echo "[fetch] $path already present, digest ok"
        continue
    fi
    mkdir -p "$(dirname "$dest")"
    # percent-encode spaces for the raw.githubusercontent URL
    enc="$(printf '%s' "$path" | sed 's/ /%20/g')"
    echo "[fetch] $path @ $COMMIT"
    curl -sfL --retry 3 -o "$tmp/dl" "$REPO/raw/$COMMIT/$enc"
    echo "$sha  $tmp/dl" | sha256sum -c --quiet - || {
        echo "[fetch] ERROR: sha256 mismatch for $path" >&2
        exit 1
    }
    mv "$tmp/dl" "$dest"
done < "$SCRIPT_DIR/sources.txt"

echo "[fetch] $(find "$target/sources" -type f | wc -l) source file(s) verified in $target/sources"
