#!/usr/bin/env python3
"""Stage a props JSON for rendering: copy every referenced clip/model into
public/staged/ and rewrite paths to staged names usable with staticFile().

Clip paths in the props file are resolved relative to the props file's own
directory (absolute paths are used as-is). When ffprobe is available, each
shot gains "_srcSeconds" so the composition can loop short clips under
speed > 1 without freezing on the last frame.

Usage: stage_props.py <props.json> <public_dir> <out_props.json>
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys


def _probe_seconds(path: str) -> float | None:
    try:
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "json", path],
            capture_output=True, text=True, timeout=60,
        )
        if proc.returncode == 0:
            return float(json.loads(proc.stdout)["format"]["duration"])
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        pass
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print(f"usage: {argv[0]} <props.json> <public_dir> <out.json>",
              file=sys.stderr)
        return 2
    props_path, public_dir, out_path = argv[1], argv[2], argv[3]
    base = os.path.dirname(os.path.abspath(props_path))
    staged = os.path.join(public_dir, "staged")
    os.makedirs(staged, exist_ok=True)

    with open(props_path, encoding="utf-8") as fh:
        props = json.load(fh)

    def stage(src: str, name: str) -> str:
        src_path = src if os.path.isabs(src) else os.path.join(base, src)
        if not os.path.isfile(src_path):
            print(f"missing asset: {src_path}", file=sys.stderr)
            raise SystemExit(2)
        ext = os.path.splitext(src_path)[1].lower()
        dest_rel = f"staged/{name}{ext}"
        shutil.copyfile(src_path, os.path.join(public_dir, dest_rel))
        return dest_rel

    for i, shot in enumerate(props["shots"]):
        src_path = shot["clip"]
        if not os.path.isabs(src_path):
            src_path = os.path.join(base, src_path)
        shot["clip"] = stage(shot["clip"], f"shot{i}")
        seconds = _probe_seconds(src_path)
        if seconds:
            shot["_srcSeconds"] = seconds

    if "model3d" in props:
        props["model3d"]["glb"] = stage(props["model3d"]["glb"], "model")

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(props, fh, indent=2)
        fh.write("\n")
    print(f"staged {len(props['shots'])} clip(s) -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
