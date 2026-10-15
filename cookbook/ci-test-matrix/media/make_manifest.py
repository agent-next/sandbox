#!/usr/bin/env python3
"""MANIFEST.json -- what each media file shows, and how it was made.

For every committed media deliverable: the source data file(s) the judge
wrote, the command that produced the file, and its sha256 + size.  Run by
media/make_media.sh after the figures, the video and result.json exist;
it fails if any deliverable is missing so a half-built media directory
can never be shipped.
"""
import hashlib
import json
import os
import subprocess
import sys

MEDIA = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(MEDIA)

NAMES = [
    "result.png", "loop.png", "demo.mp4", "result.json",
    "master/demo_lossless.mp4",
]

SHOWS = {
    "result.png":
        "the five matrix cells with their measured interpreter stamps, the "
        "failing 3.9 cell (match-syntax SyntaxError), the eight judge gates "
        "with their measured values, and the pass/fail mask -- all from "
        "media/data/verdict-good.json (judge/grade.sh examples/good "
        "--seed 42)",
    "loop.png":
        "the replayed fixing sequence (bad -> partly fixed -> good, real "
        "grade.sh verdicts ordered by media/data/loop.json) and the "
        "self-test kill matrix: examples/good plus nine single-edit mutants "
        "against the eight gates, every red cell carrying the judge's own "
        "measured detail",
    "demo.mp4":
        "the storyboard in media/STORYBOARD.md cut as one clip: the matrix "
        "building from the real grade JSON, judge/selftest.sh output "
        "streaming, the verdict JSON streaming, the replayed fix loop, the "
        "kill matrix, the mask filling -- then the static launch end card",
    "result.json":
        "the demo result manifest (schema agent-next/result@1) with the "
        "headline verdict, all eight gates, and the numbers the README "
        "Results section quotes",
    "master/demo_lossless.mp4":
        "the lossless (-crf 0) intermediate demo.mp4 is cut from; git "
        "ignored per cookbook/DEMO-STANDARD.md",
}

SOURCE = {
    "result.png": ["media/data/verdict-good.json",
                   "media/data/selftest.log"],
    "loop.png": ["media/data/verdict-good.json",
                 "media/data/verdict-<mutant>.json (9 files)",
                 "media/data/loop.json",
                 "media/data/selftest.log"],
    "demo.mp4": ["media/data/verdict-good.json",
                 "media/data/verdict-<mutant>.json (9 files)",
                 "media/data/grade-good.txt",
                 "media/data/selftest.log",
                 "media/data/loop.json",
                 "examples/good/matrix.yaml"],
    "result.json": ["media/data/verdict-good.json",
                    "media/data/selftest.log"],
    "master/demo_lossless.mp4": ["media/master/frames/ (rendered frames)"],
}

COMMAND = {
    "result.png": "python3 media/fig_result.py",
    "loop.png": "python3 media/fig_loop.py",
    "demo.mp4": "python3 media/make_video.py  (lossless master -> "
                "ffmpeg -crf 18 -preset slow -pix_fmt yuv420p -movflags "
                "+faststart)",
    "result.json": "python3 media/write_result.py  (checked with "
                   "python3 cookbook/tools/result.py check)",
    "master/demo_lossless.mp4": "python3 media/make_video.py  (ffmpeg "
                                "-crf 0 -preset slow)",
}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def ffprobe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_streams", "-show_format", path],
        capture_output=True, text=True, check=True).stdout
    meta = json.loads(out)
    st = next(s for s in meta["streams"] if s["codec_type"] == "video")
    return {
        "width": st["width"], "height": st["height"],
        "duration_sec": round(float(meta["format"]["duration"]), 2),
        "fps": st["r_frame_rate"],
        "codec": st["codec_name"], "pix_fmt": st["pix_fmt"],
    }


def pip_version(pkg):
    out = subprocess.run([sys.executable, "-m", "pip", "show", pkg],
                         capture_output=True, text=True)
    for line in out.stdout.splitlines():
        if line.startswith("Version:"):
            return line.split()[-1]
    return "absent"


def main():
    missing = [n for n in NAMES if not os.path.exists(os.path.join(MEDIA, n))]
    if missing:
        raise SystemExit("make_manifest: missing %s -- build them first"
                         % ", ".join(missing))

    files = {}
    for n in NAMES:
        path = os.path.join(MEDIA, n)
        entry = {
            "shows": SHOWS[n],
            "command": COMMAND[n],
            "source_data": SOURCE[n],
            "sha256": sha256(path),
            "size_bytes": os.path.getsize(path),
        }
        if n.endswith(".mp4"):
            entry.update(ffprobe(path))
        files[n] = entry

    for name in ("verdict-good.json", "selftest.log", "loop.json"):
        path = os.path.join(MEDIA, "data", name)
        if os.path.exists(path):
            files["data/" + name] = {
                "sha256": sha256(path),
                "size_bytes": os.path.getsize(path),
            }

    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=DEMO,
                          capture_output=True, text=True, check=True)
    doc = {
        "schema": "agent-next/media-manifest@1",
        "demo": "ci-test-matrix",
        "generated_by": "bash media/make_media.sh",
        "judge_outputs_are_the_only_source":
            "every number in every file was written by judge/grade.sh or "
            "judge/selftest.sh in this sandbox (media/data/); nothing is "
            "synthesised; the fixing sequence is a labelled replay",
        "files": files,
        "commands": {
            "setup": "bash judge/setup.sh",
            "collect": "bash media/collect.sh   (grade.sh on examples/good "
                       "+ 9 mutants, then selftest.sh)",
            "figures": "python3 media/fig_result.py && python3 "
                       "media/fig_loop.py",
            "video": "python3 media/make_video.py",
            "result": "python3 media/write_result.py && python3 "
                      "cookbook/tools/result.py check media/result.json",
            "gate": "python3 cookbook/tools/video_gate.py "
                    "cookbook/ci-test-matrix/media/demo.mp4",
            "all": "bash media/make_media.sh",
        },
        "environment": {
            "python": "%d.%d.%d" % sys.version_info[:3],
            "matplotlib": pip_version("matplotlib"),
            "ffmpeg": subprocess.run(["ffmpeg", "-version"],
                                     capture_output=True, text=True)
            .stdout.splitlines()[0].split()[2],
        },
        "sandbox_commit": head.stdout.strip(),
    }
    out = os.path.join(MEDIA, "MANIFEST.json")
    with open(out, "w") as fh:
        json.dump(doc, fh, indent=1, sort_keys=False)
        fh.write("\n")
    print("wrote", out, "(%d files)" % len(files))


if __name__ == "__main__":
    main()
