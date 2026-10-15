#!/usr/bin/env python3
"""Write media/MANIFEST.json: what each media file shows and its sha256.

    make_manifest.py <media_dir> [--seed N]

Every entry names the command that produced the file and the source data it
was drawn from, so a figure can be traced back to the judge run that measured
it.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe(path: str) -> dict:
    """ffprobe the video: size, duration, fps, codec."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,r_frame_rate,codec_name",
             "-show_entries", "format=duration", "-of", "json", path],
            capture_output=True, text=True, check=True).stdout
        d = json.loads(out)
        st = d["streams"][0]
        num, den = st["r_frame_rate"].split("/")
        return dict(width=st["width"], height=st["height"],
                    fps=round(int(num) / int(den), 3),
                    codec=st["codec_name"],
                    duration_s=round(float(d["format"]["duration"]), 3))
    except Exception as exc:                     # ffprobe is optional
        return dict(probe_error=f"{type(exc).__name__}: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("media_dir")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    d = os.path.abspath(args.media_dir)
    seed = args.seed

    selftest = json.load(open(os.path.join(d, "data", "selftest.json")))
    entries = {}

    result = os.path.join(d, "result.png")
    entries["result.png"] = dict(
        shows="The four artifacts with the judge's measured numbers drawn on "
              "them: the Shepard chroma glide against its analytic fit and the "
              "3.0-octave spec floor; the ball's bottom edge per frame with the "
              "measured floor row and each bounce marked; the QR code and the "
              "5-colour palette card.",
        command=f"python3 media/make_figures.py examples/good media --seed {seed}",
        source_data=["examples/good/shepard.wav", "examples/good/ball.gif",
                     "examples/good/qr.png", "examples/good/palette.png"],
        judge_verdict="judge/grade.sh examples/good --seed 42 (all six gates "
                      "pass)",
        sha256=sha256(result))

    loop = os.path.join(d, "loop.png")
    entries["loop.png"] = dict(
        shows="Self-test kill rate: each known-bad mutant and whether the "
              f"judge killed it ({selftest['killed']}/{selftest['total']} = "
              f"{selftest['kill_rate']}).",
        command=f"python3 media/make_figures.py examples/good media --seed {seed}",
        source_data=["media/data/selftest.json"],
        sha256=sha256(loop))

    mp4 = os.path.join(d, "demo.mp4")
    entries["demo.mp4"] = dict(
        shows="30 s animation of the judged artifact: the bouncing ball GIF "
              "frame by frame with the judge's bounce marks, the Shepard chroma "
              "glide drawing itself against its fit and the spec floor, and the "
              "WAV envelope with a playhead.",
        command=(f"python3 media/make_video.py examples/good "
                 f"media/master/demo.mkv --seed {seed} --fps 30 && "
                 f"ffmpeg -i media/master/demo.mkv -c:v libx264 -crf 18 "
                 f"-preset slow -pix_fmt yuv420p -movflags +faststart "
                 f"media/demo.mp4"),
        source_data=["examples/good/ball.gif", "examples/good/shepard.wav"],
        master="media/master/demo.mkv (lossless, git-ignored)",
        sha256=sha256(mp4), **probe(mp4))

    st = os.path.join(d, "data", "selftest.json")
    entries["data/selftest.json"] = dict(
        shows="Raw self-test result: the gate that killed each mutant.",
        command=(f"python3 media/make_selftest_data.py . media/data/"
                 f"selftest.json --seed {seed}"),
        source_data=["examples/good", "judge/mutants.py"],
        sha256=sha256(st))

    manifest = dict(seed=seed,
                    generated_by="bash media/make_media.sh",
                    files=entries)
    with open(os.path.join(d, "MANIFEST.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"make_manifest: wrote {os.path.join(d, 'MANIFEST.json')} "
          f"({len(entries)} entries)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
