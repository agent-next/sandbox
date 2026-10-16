#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python3 -c 'import PIL; assert PIL.__version__ == "10.2.0", "requires Pillow 10.2.0"'
PYTHONPATH="$HERE" python3 -c 'import compose; print("Font DejaVuSans.ttf sha256=" + compose.FONT_SHA256)'
python3 - <<'PY'
import subprocess
for tool in ("ffmpeg", "ffprobe"):
    version = subprocess.check_output([tool, "-version"], text=True).splitlines()[0]
    assert version.startswith(tool + " version 5.1.9-0+deb12u1 "), version
    print(version)
PY
if [ "${STUDIO_REUSE_SOURCE:-0}" != 1 ]; then
    python3 "$HERE/capture.py"
fi
# Remotion's headless Chrome needs these system libraries.
sudo apt-get install -y --no-install-recommends libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libgbm1 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libpango-1.0-0 libcairo2 libasound2 fonts-dejavu-core >/dev/null
(cd "$HERE/video" && npm ci --no-audit --no-fund)
python3 "$HERE/compose.py"
python3 "$HERE/../../tools/video_gate.py" "$HERE/demo.mp4"
