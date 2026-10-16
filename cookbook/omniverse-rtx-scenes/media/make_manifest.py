#!/usr/bin/env python3
"""make_manifest.py — write media/MANIFEST.json for the shipped media.

Part of media/make_media.sh.  For each file: what it shows, the command
that produced it, the sha256.  MANIFEST.json itself is not listed.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

FILES = {
    "result.png": ("the judge figure: hero frame, G1/G2/G3 gate bars with "
                   "pass lines, s/frame and step wall times",
                   "python3 media/make_figures.py <run_dir>"),
    "loop.png": ("mutant kill matrix + per-scene silhouette IoU",
                 "python3 media/make_figures.py <run_dir>"),
    "demo.mp4": ("the demo video: hero hook, scenes A/B/C, real run.py "
                 "terminal, judge HUD, end card",
                 "python3 media/make_video.py <run_dir>"),
    "STORYBOARD.md": ("the slot table the video is cut to",
                      "written before the video; make_video.py realises it"),
}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    out = {}
    for name, (what, cmd) in FILES.items():
        p = HERE / name
        if not p.exists():
            print(f"make_manifest: skipping {name} (not built yet)",
                  file=sys.stderr)
            continue
        out[name] = {"shows": what, "command": cmd, "sha256": sha(p),
                     "bytes": p.stat().st_size}
    master = HERE / "master" / "master.mp4"
    if master.exists():
        out["master/master.mp4"] = {
            "shows": "lossless CRF-0 master of demo.mp4 (gitignored)",
            "command": "python3 media/make_video.py <run_dir>",
            "sha256": sha(master), "bytes": master.stat().st_size}
    (HERE / "MANIFEST.json").write_text(
        json.dumps(out, indent=2, sort_keys=True) + "\n")
    for k, v in out.items():
        print(f"{v['sha256'][:12]}  {k}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
