#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT="$HOME/.local/share/render-pathtrace"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/opt/ms-playwright}"
mkdir -p "$ROOT"
python3 - <<'PY'
import importlib.metadata, platform, sys
if sys.version_info[:2] != (3, 12) or platform.machine() != "x86_64":
    sys.exit("setup requires the CPU image's CPython 3.12 / Linux x86_64")
try:
    assert importlib.metadata.version("playwright") == "1.63.0"
except (AssertionError, importlib.metadata.PackageNotFoundError):
    sys.exit("missing image prerequisite: Python Playwright exactly 1.63.0")
PY
if [ ! -x "$ROOT/venv/bin/python" ]; then
    python3 -m venv --system-site-packages "$ROOT/venv"
fi
"$ROOT/venv/bin/python" -m pip install --disable-pip-version-check --require-hashes --only-binary=:all: -r "$HERE/requirements.txt"
ARCHIVE="$ROOT/mutracer-0.1.1.tgz"
if [ ! -f "$ARCHIVE" ]; then
    curl --fail --location --silent --show-error --retry 3 \
        https://registry.npmjs.org/@meimu/mutracer/-/mutracer-0.1.1.tgz \
        -o "$ARCHIVE.part"
    mv "$ARCHIVE.part" "$ARCHIVE"
fi
"$ROOT/venv/bin/python" - "$ARCHIVE" <<'PY'
import base64, hashlib, pathlib, sys
data = pathlib.Path(sys.argv[1]).read_bytes()
assert base64.b64encode(hashlib.sha512(data).digest()).decode() == "iSqsI9GppKGPfDM7ntmZp5JZZjsIubh+aHVvyW516qTf2Hp64FPNzQwZIkF1LOA6aEk2JAisHBFAnpKUINyBBA==", "MuTracer npm integrity mismatch"
assert hashlib.sha256(data).hexdigest() == "a84ec7913ae95e49b1172ea0cba45f20179f4a5d0cce08768d4812348e3e7b4a", "MuTracer SHA-256 mismatch"
print("MuTracer 0.1.1 SHA-512 and SHA-256 verified")
PY
# Re-extract the verified archive so an edited installation cannot survive setup.
tar -xzf "$ARCHIVE" -C "$ROOT"
"$ROOT/venv/bin/python" - "$HERE/VERSIONS.txt" <<'PY'
import importlib.metadata, pathlib, platform, sys
from playwright.sync_api import sync_playwright
try:
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chromium", headless=True)
        chromium = b.version
        b.close()
        if chromium != "153.0.8010.12":
            sys.exit(f"Chromium version mismatch: expected 153.0.8010.12, got {chromium}")
except Exception as exc:
    sys.exit(f"missing Chromium prerequisite in PLAYWRIGHT_BROWSERS_PATH: {exc}")
versions = (f"Python {platform.python_version()}\n"
            f"Playwright {importlib.metadata.version('playwright')}\n"
            f"Chromium {chromium}\n"
            f"numpy {importlib.metadata.version('numpy')}\n"
            "MuTracer 0.1.1 (MIT)\n"
            "MuTracer SHA-256 a84ec7913ae95e49b1172ea0cba45f20179f4a5d0cce08768d4812348e3e7b4a\n")
pathlib.Path(sys.argv[1]).write_text(versions)
print(versions, end="")
print("setup PASS")
PY
