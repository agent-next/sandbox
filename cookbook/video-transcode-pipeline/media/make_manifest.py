#!/usr/bin/env python3
"""Write media/MANIFEST.json: what each media file shows and its sha256."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

FILES = [
    ("result.png",
     "The judge's measured gates on examples/good with their pass lines: the "
     "burned frame counter decoded back out of both renditions against the "
     "analytic frame index (G5), and the caption word error rate against its "
     "0.20 limit (G8).",
     "media/make_media.sh (make_figures.py)",
     "media/data/good.json, media/data/counter.json"),
    ("loop.png",
     "The agent loop: gate outcome per iteration of a scripted fixing replay "
     "(wrong-resolution -> truncated -> dropped-segment -> wrong-keyframe -> "
     "good), plus the self-test kill-rate bars for the known-good artifact "
     "and each single-edit mutant.",
     "media/make_media.sh (make_figures.py)",
     "media/data/replay.json, media/data/mutants.json"),
    ("demo.mp4",
     "30 s, 1920x1080, 30 fps, H.264. The source fixture with its burned "
     "frame counter, the 360p and 720p renditions, the counter decoded back "
     "out frame by frame, the caption WER, the kill-rate bars, and the final "
     "verdict.",
     "media/make_media.sh (make_video.py)",
     "media/data/*.json, fixtures/source.mp4, examples/good output"),
    ("data/good.json",
     "The full judge verdict for examples/good at seed 0, as grade.sh wrote it.",
     "judge/grade.sh examples/good --seed 0 --json data/good.json",
     "examples/good/pipeline.sh"),
    ("data/mutants.json",
     "Verdict for each single-edit mutant of examples/good: which gate killed "
     "it, and the kill rate.",
     "judge/grade.sh <mutant> (driven by media/make_data.py)",
     "judge/mutants.py"),
    ("data/replay.json",
     "The scripted fixing replay: one verdict per iteration until the pipeline "
     "passes.",
     "judge/grade.sh <artifact> (driven by media/make_data.py)",
     "examples/good/pipeline.sh, judge/mutants.py"),
    ("data/counter.json",
     "The burned frame counter decoded from both renditions, sampled every "
     "12 frames, against the expected frame index.",
     "media/make_data.py (uses judge/vtp_judge.py's decoder)",
     "examples/good output, fixtures/source.mp4"),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    entries = []
    for name, shows, command, source in FILES:
        path = HERE / name
        if not path.is_file():
            print(f"manifest: {name} is missing; run make_media.sh first",
                  file=sys.stderr)
            return 1
        entries.append({"file": name, "shows": shows, "command": command,
                        "source_data": source, "bytes": path.stat().st_size,
                        "sha256": sha256(path)})
    tools = {}
    for tool, args in (("ffmpeg", ["-version"]), ("python3", ["--version"])):
        try:
            out = subprocess.run([tool, *args], capture_output=True, text=True,
                                 timeout=30).stdout.strip().splitlines()
            tools[tool] = out[0] if out else "?"
        except (OSError, subprocess.SubprocessError):
            tools[tool] = "not found"
    manifest = {
        "demo": "cookbook/video-transcode-pipeline",
        "regenerate": "bash media/make_media.sh",
        "master": "media/master/ holds the lossless crf-0 master and the "
                  "individual frames; both are git-ignored",
        "tools": tools,
        "files": entries,
    }
    (HERE / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"manifest: wrote MANIFEST.json for {len(entries)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
