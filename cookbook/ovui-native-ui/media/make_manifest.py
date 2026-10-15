#!/usr/bin/env python3
"""media/make_manifest.py -- write media/MANIFEST.json.

Describes every shipped media file: what it shows, the command that makes
it, the source data file it is built from, and its sha256.  Run by
make_media.sh after the files exist; never hand-edited.
"""
import hashlib
import json
import subprocess
from pathlib import Path

MEDIA = Path(__file__).resolve().parent
DEMO = MEDIA.parent

GIT_SHA = subprocess.run(
    ["git", "-C", str(DEMO), "rev-parse", "--short", "HEAD"],
    capture_output=True, text=True).stdout.strip() or "unset"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def entry(what, command, source, path):
    return {
        "file": str(Path(path).relative_to(DEMO)),
        "what_it_shows": what,
        "command": command,
        "source_data": source,
        "sha256": sha256(path),
        "generated_at_commit": GIT_SHA,
    }


def main():
    manifest = [
        entry(
            "Key figure: the known-good panel's real 1280x720 headless "
            "render with the judge's measured widget bboxes and content "
            "region, plus the pixel gate's swatch chart (measured median "
            "RGB vs the judge's ±tol mask around the analytic sRGB target) "
            "and the PASS stamp with the real determinism sha256.",
            "media/.venv/bin/python -I media/make_figures.py",
            "media/data/render.png, media/data/facts.json, "
            "media/data/grade_good.json, judge/reference.json",
            MEDIA / "result.png"),
        entry(
            "Agent loop: a scripted replay of real judge verdicts in the "
            "order a fixing agent meets the failures (build error, pixel "
            "mismatch, nondeterminism, then the known-good PASS), and the "
            "self-test kill table — one row per mutant with the gate(s) "
            "the judge failed it on, kill rate from the real selftest run.",
            "media/.venv/bin/python -I media/make_figures.py",
            "media/data/grade_good.json, media/data/mutants.json, "
            "media/data/selftest.txt",
            MEDIA / "loop.png"),
        entry(
            "25-60 s, 1920x1080 @ 30 fps H.264 walkthrough cut from 600 "
            "real camera frames of the known-good panel (media/.frames/, "
            "recaptured each run) with hard-cut black flashes: the "
            "finished render as the hook, the spec beside the render, "
            "the judge's measured widget bboxes, the swatch close-up with "
            "its measured median vs the analytic target, the self-test "
            "terminal replay labelled with its real speed-up, the 4-gate "
            "PASS verdict and kill matrix, and a static end card with the "
            "one-command launch. Encoded with -crf 18 -preset slow "
            "-pix_fmt yuv420p -movflags +faststart from a lossless -crf 0 "
            "master (media/master/, git-ignored).",
            "media/.venv/bin/python -I media/make_video.py",
            "media/data/* (render.png, facts.json, grade_good.json, "
            "mutants.json, selftest.txt, timings.json) + media/.frames/ "
            "(the make_frames.py camera captures)",
            MEDIA / "demo.mp4"),
    ]
    (MEDIA / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2) + "\n")
    print(f"make_manifest: {len(manifest)} entries")


if __name__ == "__main__":
    main()
