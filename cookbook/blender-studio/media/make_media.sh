#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python3 -c 'import PIL; assert PIL.__version__ == "10.2.0", "requires Pillow 10.2.0"'
python3 - <<'PY'
import subprocess
for tool in ("ffmpeg", "ffprobe"):
    version = subprocess.check_output([tool, "-version"], text=True).splitlines()[0]
    assert version.startswith(tool + " version 6.1.1-3ubuntu5 "), version
    print(version)
PY
if [ "${STUDIO_REUSE_SOURCE:-0}" != 1 ]; then
    if [ "${STUDIO_USE_SDK:-0}" = 1 ]; then
        "${STUDIO_CAPTURE_PYTHON:-python3}" "$HERE/capture.py" --sdk
    else
        python3 "$HERE/capture.py"
    fi
fi
python3 "$HERE/compose.py"
python3 "$HERE/../../tools/video_gate.py" "$HERE/demo.mp4"
