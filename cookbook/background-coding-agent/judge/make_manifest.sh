#!/usr/bin/env bash
# Regenerate judge/FIXTURE.sha256 from the current fixture/ tree.
#
# The judge fails closed when the fixture it is about to grade differs
# from this manifest, so the manifest is how "pinned by content" is
# enforced.  Run this only when intentionally changing the fixture.
set -euo pipefail

JDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO="$(cd "$JDIR/.." && pwd)"
FIXTURE="$DEMO/fixture"

cd "$FIXTURE"
find . -type f ! -name '*.pyc' \
    ! -path '*/__pycache__/*' ! -path '*/.pytest_cache/*' \
    ! -path '*/.ruff_cache/*' -print0 \
    | sort -z \
    | xargs -0 sha256sum \
    | sed 's|\./||' > "$JDIR/FIXTURE.sha256"
echo "make_manifest: wrote $JDIR/FIXTURE.sha256 ($(wc -l < "$JDIR/FIXTURE.sha256") files)"
