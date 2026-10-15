#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT="$HOME/.local/share/blender-studio"
mkdir -p "$ROOT"
export PYTHONDONTWRITEBYTECODE=1
python3 - "$ROOT" "$HERE" <<'PY'
from pathlib import Path
import platform
import subprocess
import sys
root, here = map(Path, sys.argv[1:])
assert platform.python_version() == "3.13.5", "requires blender template Python 3.13.5"
version = subprocess.check_output(["blender", "--version"], text=True)
assert version.splitlines()[0] == "Blender 5.2.2 LTS", "requires Blender 5.2.2 LTS"
assert "d13f752e3b9c" in version, "unexpected Blender build"
probe = subprocess.check_output(["blender", "-b", "--factory-startup", "--python-expr",
    "import bpy,numpy,sys; print('PIN numpy='+numpy.__version__+' python='+sys.version.split()[0])"],
    text=True)
pin = next(line for line in probe.splitlines() if line.startswith("PIN "))
assert pin == "PIN numpy=2.3.4 python=3.13.13", pin
text = version.splitlines()[0] + "\nBlender build d13f752e3b9c\n" + pin + "\nPython " + platform.python_version() + "\n"
(root / "VERSIONS.txt").write_text(text)
(here / "VERSIONS.txt").write_text(text)
print(text, end="")
print("setup PASS (pinned image tools; no downloads)")
PY
