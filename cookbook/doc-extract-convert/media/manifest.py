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
     "27 s step-through of the agent loop with captions: the accuracy "
     "figure, one captioned frame per graded artifact, then the self-test "
     "kill rate.",
     "bash media/make_media.sh"),
]

DATA = {          # every verdict JSON a figure or frame draws from
    "result.png": ["good", "m01-total-as-float", "m03-box-on-whitespace",
                   "m03b-whole-page-box", "m04-quarantine-everything",
                   "m05-wrong-date-format", "m06-accept-bad-date"],
    "loop.png": ["good", "m01-total-as-float", "m03-box-on-whitespace",
                 "m03b-whole-page-box", "m04-quarantine-everything",
                 "m05-wrong-date-format", "m06-accept-bad-date",
                 "judge_guard"],
    "demo.mp4": ["good", "m01-total-as-float", "m03-box-on-whitespace",
                 "m03b-whole-page-box", "m04-quarantine-everything",
                 "m05-wrong-date-format", "m06-accept-bad-date",
                 "judge_guard"],
}


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
            "source_data": ["media/data/%s.json" % d for d in DATA[name]],
            "sha256": sha256(os.path.join(HERE, name)),
        }
    with open(os.path.join(HERE, "MANIFEST.json"), "w") as f:
        json.dump(out, f, indent=2, sort_keys=True)
        f.write("\n")
    print("[media] MANIFEST.json written for %d files" % len(FILES))


if __name__ == "__main__":
    main()