#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT="$HOME/.local/share/render-pathtrace"
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-/opt/ms-playwright}"
mkdir -p "$ROOT"
if [ "${SBX_RENDER_BACKEND:-cpu}" = gpu ]; then
    export PYTHONPATH="$ROOT/deps${PYTHONPATH:+:$PYTHONPATH}"
    /opt/browser/bin/python - "$ROOT" "$SBX_RENDER_ARCHIVE" "${SBX_RENDER_NUMPY_WHEEL:-}" <<'PY'
import base64, hashlib, importlib.metadata, pathlib, subprocess, sys, tarfile
root, archive = map(pathlib.Path, sys.argv[1:3])
assert sys.version_info[:2] == (3, 12), "GPU template requires CPython 3.12"
assert importlib.metadata.version("playwright") == "1.55.0"
if sys.argv[3]:
    wheel = pathlib.Path(sys.argv[3])
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == "fd83c01228a688733f1ded5201c678f0c53ecc1006ffbc404db9f7a899ac6249", "NumPy wheel SHA-256 mismatch"
    subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                    "--no-index", "--no-deps", "--target", str(root / "deps"),
                    "--upgrade", str(wheel)], check=True)
else:
    assert importlib.metadata.version("numpy") == "2.2.6", "GPU image NumPy must be 2.2.6"
data = archive.read_bytes()
assert base64.b64encode(hashlib.sha512(data).digest()).decode() == "iSqsI9GppKGPfDM7ntmZp5JZZjsIubh+aHVvyW516qTf2Hp64FPNzQwZIkF1LOA6aEk2JAisHBFAnpKUINyBBA==", "MuTracer npm integrity mismatch"
assert hashlib.sha256(data).hexdigest() == "a84ec7913ae95e49b1172ea0cba45f20179f4a5d0cce08768d4812348e3e7b4a", "MuTracer SHA-256 mismatch"
with tarfile.open(archive) as tar:
    tar.extractall(root, filter="data")
(root / "venv/bin").mkdir(parents=True, exist_ok=True)
python = root / "venv/bin/python"
if python.is_symlink():
    python.unlink()
python.write_text('#!/bin/sh\nexec /opt/browser/bin/python "$@"\n')
python.chmod(0o755)
print("MuTracer 0.1.1 SHA-512 and SHA-256 verified")
PY
else
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
fi
"$ROOT/venv/bin/python" - "$HERE/VERSIONS.txt" <<'PY'
import importlib.metadata, os, pathlib, platform, sys
from playwright.sync_api import sync_playwright
try:
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chromium", headless=True,
                              args=["--no-sandbox", "--disable-setuid-sandbox",
                                    "--disable-dev-shm-usage"])
        chromium = b.version
        b.close()
        expected = ("140.0.7339.16" if os.environ.get("SBX_RENDER_BACKEND") == "gpu"
                    else "153.0.8010.12")
        if chromium != expected:
            sys.exit(f"Chromium version mismatch: expected {expected}, got {chromium}")
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
