#!/usr/bin/env python3
"""Write media/MANIFEST.json: what each artifact shows, the command and
the source data behind it, and its sha256."""

import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

MUTANTS = ["blank_canvas", "missing_parts", "console_error",
           "static_camera", "wrong_labels", "no_interaction",
           "tiny_capture"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def entry(what, command, sources):
    return {"what": what, "command": command, "sources": sources}


def main():
    files = {
        "result.png": entry(
            "Exploded-view showcase capture of the real figure "
            "(?shot&labels&explode=0.72, yaw 35) rendered by Chrome "
            "Headless Shell + SwiftShader at 1920x1080, with a verdict "
            "band drawn from the measured values in verdict-good.json.",
            "media/make_media.sh  (render_media.py + fig_result.py)",
            ["media/master/exploded.png", "media/data/verdict-good.json"]),
        "assembled.png": entry(
            "The same scene fully assembled (?shot&labels=0, yaw 35): "
            "a raw real screenshot, no annotation.",
            "media/make_media.sh  (render_media.py)",
            ["examples/good/four-stroke-engine/four-stroke-engine.html"]),
        "loop.png": entry(
            "Mutant x gate matrix: examples/good plus the 7 single-edit "
            "mutants against all 6 judge gates. Red cells carry the "
            "measured value that broke the gate.",
            "media/.venv/bin/python media/fig_loop.py",
            ["media/data/verdict-good.json"] +
            ["media/data/verdict-%s.json" % m for m in MUTANTS] +
            ["media/data/selftest.log"]),
        "demo.mp4": entry(
            "21 s turntable + exploded-view animation assembled from "
            "630 real rendered frames (no interpolation), h264 crf 18; "
            "lossless master in media/master/ (git-ignored).",
            "media/make_media.sh  (render_media.py)",
            ["examples/good/four-stroke-engine/four-stroke-engine.html"]),
    }
    manifest = {
        "note": "Every frame of result.png/assembled.png/demo.mp4 is a "
                "real screenshot of the figure rendered by Chrome "
                "Headless Shell + SwiftShader WebGL -- no synthesized or "
                "interpolated frames. loop.png's cells come from real "
                "grade.sh verdicts in media/data/ (collect_data.sh).",
        "source": "cookbook/anatomy-machines, seed 42, "
                  "chrome-headless-shell 148.0.7778.96 + SwiftShader, "
                  "viewport 1920x1080",
        "files": {},
    }
    for name, meta in files.items():
        p = os.path.join(HERE, name)
        manifest["files"][name] = dict(
            meta, sha256=sha256(p), bytes=os.path.getsize(p))
    with open(os.path.join(HERE, "MANIFEST.json"), "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    print("manifest: wrote MANIFEST.json")


if __name__ == "__main__":
    main()
