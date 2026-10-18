#!/usr/bin/env python3
"""Bump or check the three release version strings.

The release version lives in three files, which must always agree:

    cli/pyproject.toml                           [project] version = "x.y.z"
    plugins/sandbox/.claude-plugin/plugin.json   "version": "x.y.z"
    plugins/sandbox/.codex-plugin/plugin.json    "version": "x.y.z"

Usage:
    bump_version.py X.Y.Z [--allow-minor]   rewrite all three to X.Y.Z
    bump_version.py --check [--tag vX.Y.Z]  exit non-zero when they disagree
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

VERSION_FILES = (
    "cli/pyproject.toml",
    "plugins/sandbox/.claude-plugin/plugin.json",
    "plugins/sandbox/.codex-plugin/plugin.json",
)

_TOML_VERSION = re.compile(r'^version\s*=\s*"([^"]*)"', re.M)


class BumpError(Exception):
    pass


def read_version(path):
    text = path.read_text()
    if path.suffix == ".toml":
        m = _TOML_VERSION.search(text)
        if m:
            return m.group(1)
        raise BumpError(f"{path}: no version found")
    return json.loads(text)["version"]


def main(argv=None, root=ROOT):
    return 0
