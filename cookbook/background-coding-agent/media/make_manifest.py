#!/usr/bin/env python3
"""Generate MANIFEST.json for the background-coding-agent demo media."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

MEDIA = Path(__file__).resolve().parent


def sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def tool_version(cmd, pattern):
    try:
        out = subprocess.check_output(cmd, text=True,
                                      stderr=subprocess.STDOUT)
        import re
        m = re.search(pattern, out)
        return m.group(1) if m else out.splitlines()[0].split()[-1]
    except Exception:
        return "unknown"


def ffprobe_info(filepath):
    try:
        out = subprocess.check_output([
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration,codec_name",
            "-of", "json", str(filepath)
        ], text=True)
        stream = json.loads(out)["streams"][0]
        return {
            "width": stream.get("width"),
            "height": stream.get("height"),
            "duration_sec": float(stream.get("duration", 0)),
            "codec": stream.get("codec_name"),
        }
    except Exception as e:
        return {"error": str(e)}


def main():
    matplotlib_version = tool_version(
        [sys.executable, "-c", "import matplotlib; print(matplotlib.__version__)"],
        r"(\S+)")
    manifest = {
        "demo": "background-coding-agent",
        "generated_by": "media/make_media.sh",
        "files": {},
        "source_data": {
            "verdict_good": "media/data/verdict_good.json (grade.sh on "
                            "examples/good/delivery.patch)",
            "replay": "media/data/replay.json (scripted replay: one "
                      "mutant per gate in judge order, then good)",
            "selftest": "media/data/selftest.json (grade.sh on all 11 "
                        "mutants, kill rate 100%)",
            "oracle_detail": "media/data/oracle_detail.json (delivered "
                             "--json vs judge/reference.py, per field)",
        },
        "commands": {
            "setup": "bash judge/setup.sh",
            "selftest": "bash judge/selftest.sh",
            "grade_good": "bash judge/grade.sh "
                          "examples/good/delivery.patch --json good.json",
            "media": "bash media/make_media.sh",
        },
        "environment": {
            "python": tool_version([sys.executable, "--version"],
                                   r"Python (\S+)"),
            "matplotlib": matplotlib_version,
            "ffmpeg": tool_version(["ffmpeg", "-version"], r"ffmpeg version (\S+)"),
        },
    }

    for fname in ["result.png", "loop.png", "demo.mp4"]:
        fpath = MEDIA / fname
        if fpath.exists():
            manifest["files"][fname] = {
                "sha256": sha256(fpath),
                "size_bytes": fpath.stat().st_size,
                "shows": {
                    "result.png": "oracle agreement vs the 1e-9 pass line, "
                                  "measured summary of sample.csv, tests "
                                  "collected vs required minimums",
                    "loop.png": "agent-loop replay (judge score per "
                                "iteration until pass) + self-test "
                                "kill-rate bars",
                    "demo.mp4": "30 s captioned step-through: title, loop "
                                "replay, oracle panel, kill bars, verdict "
                                "card",
                }[fname],
            }
            if fname == "demo.mp4":
                manifest["files"][fname].update(ffprobe_info(fpath))

    master = MEDIA / "master" / "demo_master.mp4"
    if master.exists():
        manifest["files"]["master/demo_master.mp4"] = {
            "sha256": sha256(master),
            "size_bytes": master.stat().st_size,
            "note": "lossless crf-0 master, git-ignored",
        }

    (MEDIA / "MANIFEST.json").write_text(json.dumps(manifest, indent=1))
    print("MANIFEST.json written")


if __name__ == "__main__":
    main()
