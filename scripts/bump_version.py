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

import argparse
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

VERSION_FILES = (
    "cli/pyproject.toml",
    "plugins/sandbox/.claude-plugin/plugin.json",
    "plugins/sandbox/.codex-plugin/plugin.json",
)

_SEMVER = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_TAG = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_TOML_VERSION = re.compile(r"""^version\s*=\s*(["'])([^"']*)\1(.*)$""")
_JSON_VERSION = re.compile(r'"version"(\s*:\s*)"([^"]*)"')


class BumpError(Exception):
    pass


def parse_version(text):
    m = _SEMVER.fullmatch(text)
    if not m:
        raise BumpError(f"invalid version {text!r}: expected x.y.z")
    return tuple(int(g) for g in m.groups())


def _fmt(v):
    return ".".join(str(n) for n in v)


def read_version(path):
    text = path.read_text()
    if path.suffix == ".toml":
        section = None
        for line in text.splitlines():
            s = line.strip()
            if s.startswith("["):
                section = s
            elif section == "[project]":
                m = _TOML_VERSION.match(s)
                if m:
                    return m.group(2)
        raise BumpError(f"{path}: no [project] version found")
    try:
        version = json.loads(text)["version"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise BumpError(f"{path}: cannot read version ({e})")
    if not isinstance(version, str):
        raise BumpError(f"{path}: version is not a string")
    return version


def _new_text(path, version):
    text = path.read_text()
    if path.suffix == ".toml":
        lines = text.splitlines(keepends=True)
        section = None
        for i, line in enumerate(lines):
            s = line.strip()
            if s.startswith("["):
                section = s
            elif section == "[project]" and (m := _TOML_VERSION.match(s)):
                indent = line[: len(line) - len(line.lstrip())]
                lines[i] = f'{indent}version = "{version}"{m.group(3)}\n'
                return "".join(lines)
        raise BumpError(f"{path}: no [project] version found")
    # Only the top-level key is ours; a nested object may carry its own.
    for m in _JSON_VERSION.finditer(text):
        if _json_depth(text, m.start()) == 1:
            return f'{text[:m.start()]}"version"{m.group(1)}"{version}"{text[m.end():]}'
    raise BumpError(f"{path}: no top-level version field found")


def _json_depth(text, end):
    """Object/array nesting depth at text[end]; -1 inside a string."""
    depth, in_str, esc = 0, False, False
    for ch in text[:end]:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
    return -1 if in_str else depth


def _write(path, text):
    """Stage text next to path with path's mode; return the temp file."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.chmod(tmp, stat.S_IMODE(path.stat().st_mode))
    except BaseException:
        os.unlink(tmp)
        raise
    return tmp


def bump(root, new_text, allow_minor=False):
    new = parse_version(new_text)
    paths = [root / rel for rel in VERSION_FILES]
    # Read and validate everything before touching any file.
    rendered = [(p, _new_text(p, new_text)) for p in paths]
    cur = max(parse_version(read_version(p)) for p in paths)
    if new < cur:
        raise BumpError(f"refusing to go backwards: {_fmt(cur)} -> {new_text}")
    if (new[0], new[1]) > (cur[0], cur[1]) and not allow_minor:
        raise BumpError(
            f"{_fmt(cur)} -> {new_text} is a minor/major bump; pass --allow-minor"
        )
    # Stage all three before replacing any, so a failed write moves none.
    staged = []
    try:
        for p, text in rendered:
            staged.append((_write(p, text), p))
    except BaseException:
        for tmp, _ in staged:
            os.unlink(tmp)
        raise
    originals = [(p, p.read_text()) for _, p in staged]
    done = 0
    try:
        for tmp, p in staged:
            os.replace(tmp, p)
            done += 1
    except BaseException:
        # Put back the files already replaced and drop the unused temps.
        for p, text in originals[:done]:
            os.replace(_write(p, text), p)
        for tmp, _ in staged[done:]:
            os.unlink(tmp)
        raise
    return paths


def check(root, tag=None):
    paths = [root / rel for rel in VERSION_FILES]
    versions = {rel: read_version(p) for rel, p in zip(VERSION_FILES, paths)}
    problems = [
        f"{rel}: version {v!r} is not x.y.z"
        for rel, v in versions.items()
        if not _SEMVER.fullmatch(v)
    ]
    if len(set(versions.values())) != 1:
        detail = ", ".join(f"{rel}={v}" for rel, v in versions.items())
        problems.append(f"version strings disagree: {detail}")
    if tag is not None:
        if not _TAG.fullmatch(tag):
            raise BumpError(f"invalid tag {tag!r}: expected vX.Y.Z")
        want = tag[1:]
        problems += [
            f"{rel}: version {v} != tag {tag}"
            for rel, v in versions.items()
            if v != want
        ]
    return problems


def main(argv=None, root=ROOT):
    ap = argparse.ArgumentParser(
        prog="bump_version.py",
        description="Bump or check the three release version strings.",
    )
    ap.add_argument("version", nargs="?", help="new version, x.y.z")
    ap.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero when the three versions disagree",
    )
    ap.add_argument(
        "--tag",
        help="with --check: also require the versions to match tag vX.Y.Z",
    )
    ap.add_argument(
        "--allow-minor",
        action="store_true",
        help="allow a minor or major bump (default: patch only)",
    )
    args = ap.parse_args(argv)
    try:
        if args.check:
            if args.version or args.allow_minor:
                ap.error("--check takes no NEW_VERSION or --allow-minor")
            problems = check(root, args.tag)
            for p in problems:
                print(f"error: {p}", file=sys.stderr)
            if problems:
                return 1
            suffix = f" and match tag {args.tag}" if args.tag else ""
            print(f"ok: all version strings agree{suffix}")
            return 0
        if args.tag is not None:
            ap.error("--tag is only valid with --check")
        if not args.version:
            ap.error("NEW_VERSION required (or use --check)")
        for p in bump(root, args.version, args.allow_minor):
            print(p)
        return 0
    except BumpError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
