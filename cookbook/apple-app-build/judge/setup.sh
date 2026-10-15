#!/usr/bin/env bash
# The judge is Python 3 standard library only; the builder needs the `apple` sandbox template
# (Swift 6.2.3 + xtool 1.22.2 + Darwin SDK 26.2 + rcodesign 0.29.0 + apple-build).
set -euo pipefail
python3 -c 'import sys; assert sys.version_info >= (3, 9), sys.version'
{
  python3 --version
  if command -v apple-build >/dev/null; then
    swift --version 2>&1 | head -1
    echo "xtool $(xtool --version)"
    rcodesign --version
    swift sdk list
  else
    echo "apple-build not found: grading only (create the sandbox with --template apple to build)"
  fi
} | tee "$(dirname "$0")/VERSIONS.txt"
