#!/usr/bin/env python3
"""Write media/MANIFEST.json: what each shipped file shows and its sha256."""

import hashlib
import json
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))

FILES = [
    ("result.png",
     "G1 field accuracy for each graded artifact (six single-edit mutants "
     "and the known-good extractor) with the >= 95 % pass line, the gates "
     "each artifact cleared and the artifact names.",
     "python3 media/make_figures.py"),
    ("loop.png",
     "The agent loop: gates passed (of 5) per graded iteration from the "
     "mutants to the known-good extractor, plus the self-test kill rate "
     "against the >= 90 % rule.",
     "python3 media/make_figures.py"),
    ("demo.mp4",
     "30 s of real animated output at 1920x1080: the grounded record typing "
     "in, a scanner band sweeping a real scan as the boxes lock on, the "
     "faded photocopy re-binarising with the ink coverage it recovers, the "
     "blank/smear pages quarantined, the self-test at 3x speed, and the "
     "verdict HUD.",
     "bash media/make_media.sh"),
    ("result.json",
     "The result-card manifest (agent-next/result@1): headline, the five "
     "gates with their measured values and thresholds, hero/gallery "
     "pointers and the launch prompt, all generated from the same verdict "
     "JSONs as the figures.",
     "python3 media/result_json.py"),
]

DATA = {          # every verdict JSON a figure or frame draws from
    "result.png": ["good", "m01-total-as-float", "m03-box-on-whitespace",
                   "m03b-whole-page-box", "m04-quarantine-everything",
                   "m05-wrong-date-format", "m06-accept-bad-date"],
    "loop.png": ["good", "m01-total-as-float", "m03-box-on-whitespace",
                 "m03b-whole-page-box", "m04-quarantine-everything",
                 "m05-wrong-date-format", "m06-accept-bad-date",
                 "judge_guard"],
    # the video animates the real corpus/extractor runs as well as the verdicts
    "demo.mp4": ["corpus", "extract", "corrupt", "extract-corrupt", "good",
                 "m01-total-as-float", "m03-box-on-whitespace",
                 "m03b-whole-page-box", "m04-quarantine-everything",
                 "m05-wrong-date-format", "m06-accept-bad-date",
                 "judge_guard"],
    "result.json": ["good", "judge_guard", "m01-total-as-float",
                    "m03-box-on-whitespace", "m03b-whole-page-box",
                    "m04-quarantine-everything", "m05-wrong-date-format",
                    "m06-accept-bad-date"],
}


def source_data(name):
    """The real inputs behind `name`, as paths a reader can follow."""
    entries = []
    for d in DATA.get(name, []):
        if d in ("corpus", "extract", "corrupt", "extract-corrupt"):
            entries.append("media/data/%s/" % d)
        elif d in ("README",):
            entries.append("README.md")
        else:
            entries.append("media/data/%s.json" % d)
    if name == "demo.mp4":
        entries += ["media/data/corpus/pages/*.png",
                    "media/data/extract/records.json",
                    "media/data/extract-corrupt/quarantine.json"]
    if name == "result.json":
        entries = list(dict.fromkeys(entries + ["README.md"]))
    return entries


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def seed_of(name):
    with open(os.path.join(HERE, "data", name + ".json")) as f:
        return json.load(f).get("seed")


def main():
    out = {"generator": "bash media/make_media.sh",
           "seed": seed_of("good"),
           "toolchain": {"Pillow": __import__("PIL").__version__,
                         "fonts": "fonts-dejavu-core 2.37-6",
                         "ffmpeg": subprocess.run(
                             ["ffmpeg", "-version"], capture_output=True,
                             text=True).stdout.splitlines()[0].split()[2]},
           "files": {}}
    for name, what, command in FILES:
        out["files"][name] = {
            "what": what,
            "command": command + "  (seed %d)" % out["seed"],
            "source_data": source_data(name),
            "sha256": sha256(os.path.join(HERE, name)),
        }
    with open(os.path.join(HERE, "MANIFEST.json"), "w") as f:
        json.dump(out, f, indent=2, sort_keys=True)
        f.write("\n")
    print("[media] MANIFEST.json written for %d files" % len(FILES))


if __name__ == "__main__":
    main()