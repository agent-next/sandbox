#!/usr/bin/env python3
"""Write media/MANIFEST.json: what each artifact shows, the command and
the source data behind it, and its sha256."""

import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    entries = {
        "result.png": {
            "shows": ("Left: the real UART0 transcript of examples/good "
                      "booting in QEMU lm3s6965evb (banner + scripted "
                      "shell session; elided lines marked). Right: the "
                      "8 judge gates with measured values and the "
                      "maps_ok 8192 B pass line; flash/SRAM usage from "
                      "the linker map."),
            "command": "media/.venv/bin/python media/fig_result.py",
            "sources": ["media/data/uart-good.json",
                        "media/data/verdict-good.json",
                        "media/data/size-good.txt",
                        "media/data/firmware-good.map",
                        "judge/spec.json"],
        },
        "loop.png": {
            "shows": ("Mutant x gate matrix: examples/good plus the 14 "
                      "single-edit mutants against all 8 gates. Red "
                      "cells carry the gate's measured detail (e.g. "
                      "'5/46 wrong'); the amber row is the build-only "
                      "kill. Footer: the replayed fix sequence and the "
                      "14/14 kill rate."),
            "command": "media/.venv/bin/python media/fig_loop.py",
            "sources": ["media/data/verdict-good.json"] +
                       ["media/data/verdict-%s.json" % m for m in [
                           "build-broken", "crc-init", "crc-no-xorout",
                           "crc-poly", "crc-shift-dir", "ring-count-drift",
                           "ring-drop-newest", "ring-off-by-one",
                           "shell-bad-hex-accepted", "shell-unknown-ok",
                           "startup-bad-sp", "startup-no-reset",
                           "uart-no-init", "uart-rx-inverted"]] +
                       ["media/data/loop.json", "media/data/selftest.log"],
        },
        "demo.mp4": {
            "shows": ("Replay of the real UART transcript (typed pace "
                      "from the capture timestamps), then the crc-poly "
                      "mutant session with the oracle-divergent "
                      "responses highlighted against the expected "
                      "lines, then the verdicts. 1920x1080 30 fps "
                      "H.264; lossless master in media/master/ "
                      "(git-ignored)."),
            "command": ("media/.venv/bin/python media/video.py && "
                        "ffmpeg -framerate 30 -i media/frames/%05d.png "
                        "-c:v libx264 -crf 0 -pix_fmt yuv420p "
                        "media/master/demo.mp4 && "
                        "ffmpeg -i media/master/demo.mp4 -c:v libx264 "
                        "-crf 18 -preset slow -pix_fmt yuv420p "
                        "-movflags +faststart media/demo.mp4"),
            "sources": ["media/data/uart-good.json",
                        "media/data/uart-crc-poly.json",
                        "media/data/verdict-good.json",
                        "media/data/loop.json",
                        "media/data/selftest.log"],
        },
    }

    ffv = subprocess.run(["ffmpeg", "-version"], capture_output=True,
                         text=True).stdout.splitlines()[0]
    manifest = {
        "generated_by": "bash media/make_media.sh",
        "ffmpeg": ffv,
        "python_packages": "media/requirements.txt",
        "data_provenance": ("media/data/ is produced by "
                            "media/collect_data.sh: judge/grade.sh "
                            "--seed 20260814 --json on examples/good and "
                            "each mutants.py artifact, judge/selftest.sh, "
                            "media/capture.py (same driver, same wire), "
                            "and arm-none-eabi-size on the real build."),
        "files": {},
    }
    for name, meta in entries.items():
        path = os.path.join(HERE, name)
        if not os.path.isfile(path):
            raise SystemExit("manifest: missing %s" % path)
        manifest["files"][name] = dict(meta, sha256=sha256(path),
                                       bytes=os.path.getsize(path))

    out = os.path.join(HERE, "MANIFEST.json")
    with open(out, "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("wrote", out)


if __name__ == "__main__":
    main()
