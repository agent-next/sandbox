#!/usr/bin/env bash
# judge/versions.sh — print what judge/setup.sh actually installed, from the
# tools' own --version output.  Writes judge/VERSIONS.txt.
#
# Usage: bash judge/versions.sh > judge/VERSIONS.txt
#        bash judge/versions.sh --check   # fail if VERSIONS.txt is stale

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSIONS_TXT="$SCRIPT_DIR/VERSIONS.txt"
JH="$HOME/.hyperframes-judge"
[[ -f "$JH/env.sh" ]] && source "$JH/env.sh"

cat <<'EOF'
# What judge/setup.sh actually installed — recorded by the tools' own
# --version output, not by hand.
#
# Reproduce:
#   bash judge/setup.sh && bash judge/versions.sh > judge/VERSIONS.txt
#
# Debian bookworm archive + upstream downloads, pinned by sha256 in
# judge/package-sha256.txt.  A superseded upstream build changes a digest
# and setup.sh fails loudly instead of silently installing something else.

EOF

echo '### Toolchain'
echo ''
echo '$ node --version'
"${HF_NODE:-node}" --version 2>/dev/null | sed 's/^/    /' || echo '    MISSING'
echo ''
echo '$ hyperframes --version'
if [[ -n "${HYPERFRAMES_BIN:-}" && -f "$HYPERFRAMES_BIN" ]]; then
    "${HF_NODE:-node}" "$HYPERFRAMES_BIN" --version 2>/dev/null \
        | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 | sed 's/^/    /'
else
    echo '    MISSING'
fi
echo ''
echo '$ chrome-headless-shell --version'
CHS="$HOME/.cache/hyperframes/chrome/chrome-headless-shell"
bin=$(find "$CHS" -name chrome-headless-shell -type f 2>/dev/null | head -1)
if [[ -n "$bin" ]]; then "$bin" --version 2>/dev/null | sed 's/^/    /'; else echo '    MISSING'; fi
echo ''
echo '$ ffmpeg -version | head -1'
ffmpeg -version 2>/dev/null | head -1 | sed 's/^/    /' || echo '    MISSING'
echo ''
echo '$ ffprobe -version | head -1'
ffprobe -version 2>/dev/null | head -1 | sed 's/^/    /' || echo '    MISSING'
echo ''
echo '$ tesseract --version | head -2'
tesseract --version 2>/dev/null | head -2 | sed 's/^/    /' || echo '    MISSING'
echo ''

echo '### dpkg versions (dpkg-query -W)'
echo ''
for pkg in ffmpeg tesseract-ocr libtesseract5 liblept5 tesseract-ocr-eng \
           fonts-dejavu-core; do
    printf '%s=%s\n' "$pkg" \
        "$(dpkg-query -W -f='${Version}' "$pkg" 2>/dev/null || echo MISSING)"
done
echo ''

echo '### Pinned download sha256 digests (judge/package-sha256.txt)'
echo ''
grep -v '^\s*#\|^\s*$' "$SCRIPT_DIR/package-sha256.txt" | sed 's/^/  /'
echo ''

echo '### npm lockfile'
echo ''
echo "packages in judge/package-lock.json: $(python3 -c 'import json;print(len(json.load(open("'"$SCRIPT_DIR"'/package-lock.json"))["packages"]))' 2>/dev/null || echo '?')"
echo "hyperframes: $(python3 -c 'import json;print(json.load(open("'"$SCRIPT_DIR"'/package-lock.json"))["packages"]["node_modules/hyperframes"]["version"])' 2>/dev/null || echo '?')"
echo ''

if [[ "${1:-}" == "--check" ]]; then
    echo "versions.sh --check: verifying judge/VERSIONS.txt is current" >&2
    tmp="$(mktemp)"
    bash "$0" >"$tmp"
    if diff -u "$VERSIONS_TXT" "$tmp"; then
        rm -f "$tmp"
        echo "versions.sh: judge/VERSIONS.txt is current" >&2
    else
        rm -f "$tmp"
        echo "versions.sh: judge/VERSIONS.txt is STALE" >&2
        exit 1
    fi
fi
