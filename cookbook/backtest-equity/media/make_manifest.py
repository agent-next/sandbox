#!/usr/bin/env python3
"""Generate MANIFEST.json for the backtest-equity demo media.

For each media file: what it shows, the command that produced it, the source
data file, and the sha256 of both the file and its source.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

MEDIA = Path(__file__).resolve().parent


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe(path):
    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,duration,codec_name",
             "-of", "json", str(path)], text=True)
        s = json.loads(out)["streams"][0]
        return {"width": s.get("width"), "height": s.get("height"),
                "duration_sec": round(float(s.get("duration", 0.0)), 1),
                "codec": s.get("codec_name")}
    except Exception as exc:                       # pragma: no cover
        return {"error": str(exc)}


def describe(name, source):
    p = MEDIA / name
    return {
        "shows": {
            "result.png":
                "the known-good artifact's equity curve against the blind "
                "reference's final equity (the G2 oracle agreement), with "
                "the drawdown and position panels",
            "loop.png":
                "the agent-loop replay's judge-measured deviation per attempt "
                "until the judge passes, and the self-test kill rate per "
                "known-bad mutant",
            "demo.mp4":
                "the same series animated: the backtest running day by day, "
                "the agent loop's deviations, then the kill rates",
        }[name],
        "command": {
            "result.png": "media/make_media.sh -> media/make_figures.py make_result",
            "loop.png": "media/make_media.sh -> media/make_figures.py make_loop",
            "demo.mp4": "media/make_media.sh -> media/make_video.py + ffmpeg "
                        "(crf 0 lossless master in media/master/, then "
                        "-crf 18 -preset slow -pix_fmt yuv420p "
                        "-movflags +faststart)",
        }[name],
        "source_data": source,
        "sha256": sha256(p),
        "size_bytes": p.stat().st_size,
    }


def main():
    files = {
        "result.png": describe(
            "result.png",
            "media/data/series.json + media/data/metrics.json "
            "(the judge's own blind reference run)"),
        "loop.png": describe(
            "loop.png",
            "media/data/replay.json + media/data/selftest.json "
            "(grade verdicts of the known-bad mutants and the good artifact)"),
        "demo.mp4": describe(
            "demo.mp4",
            "media/frames rendered by make_video.py from media/data/*.json"),
    }
    files["demo.mp4"].update(probe(MEDIA / "demo.mp4"))

    # selftest.json is written by make_data.py from judge/mutants.py, so the
    # number of known-bad mutants lives in the data, not in this file.
    try:
        selftest = json.loads((MEDIA / "data" / "selftest.json").read_text())
        n_mutants = len(selftest.get("mutants", {}))
    except Exception:
        n_mutants = 0

    try:
        ffmpeg = subprocess.check_output(["ffmpeg", "-version"], text=True)
        ffmpeg = ffmpeg.splitlines()[0].split()[2]
    except Exception:
        ffmpeg = "unknown"

    manifest = {
        "demo": "backtest-equity",
        "generated_by": "media/make_media.sh",
        "files": files,
        "source_data": {
            "curve": "media/data/curve.json (judge reference summary metrics)",
            "series": "media/data/series.json (the judge's own blind "
                      "reference equity/position/drawdown series)",
            "selftest": f"media/data/selftest.json (grade verdicts: good + "
                        f"{n_mutants} known-bad mutants)",
            "replay": "media/data/replay.json (the known-bad mutants graded "
                      "in the order a fixing agent would meet them)",
            "comparison": "media/data/comparison.json (artifact metrics vs "
                          "reference metrics)",
        },
        "commands": {
            "setup": "bash judge/setup.sh",
            "selftest": "bash judge/selftest.sh",
            "grade_good": "bash judge/grade.sh examples/good --seed 42",
            "media": "bash media/make_media.sh",
        },
        "environment": {
            "ffmpeg": ffmpeg,
            "python": "3.12",
            "matplotlib": "3.9.4",
            "numpy": "2.2.6",
        },
    }
    (MEDIA / "MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print("manifest: media/MANIFEST.json")


if __name__ == "__main__":
    main()
