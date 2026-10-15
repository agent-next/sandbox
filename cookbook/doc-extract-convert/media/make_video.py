#!/usr/bin/env python3
"""Render the demo's video frames from real judge data, then encode.

The simulation is not time-dependent in the physics sense, so (as the media
standard allows) this is a step-through of the agent loop with captions: the
graded artifacts one at a time, each holding on its measured bars for a few
seconds, ending on the pass line.  Every frame is drawn from media/data/*.json
— the verdict JSONs judge/grade.sh wrote in this invocation.

Frames land in media/frames/ (git-ignored); media/make_media.sh encodes them
to the lossless master and the web file.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image, ImageDraw

import chartlib as C
from make_figures import MUTANT_ORDER, SHORT, load, new_figure

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
FRAMES = os.path.join(HERE, "frames")

FPS = 30
HOLD = 3.0          # seconds per graded artifact
W, H = 1920, 1080


def scale(im, box):
    """Letterbox/crop `im` into `box` (1920x1080) keeping its aspect."""
    sw, sh = im.size
    tw, th = box
    s = min(tw / sw, th / sh)
    nw, nh = int(sw * s), int(sh * s)
    scaled = im.resize((nw, nh), Image.LANCZOS)
    out = Image.new("RGB", (tw, th), C.SURFACE)
    out.paste(scaled, ((tw - nw) // 2, (th - nh) // 2))
    return out


def caption_frame(d, kicker, headline, body):
    """A caption bar under the figure: what this frame shows and its number."""
    d.rectangle([0, H - 300, W, H], fill=(28, 28, 30))
    d.text((60, H - 262), kicker, font=C.font(24), fill=(150, 150, 155),
           anchor="lm")
    d.text((60, H - 206), headline, font=C.font(38, True),
           fill=(245, 245, 245), anchor="lm")
    d.text((60, H - 148), body, font=C.font(26), fill=(200, 200, 205),
           anchor="lm")


def still(d, lines, y):
    for line in lines:
        d.text((60, y), line, font=C.font(25), fill=(190, 190, 196),
               anchor="lm")
        y += 40
    return y


def main():
    rows = [load(m) for m in MUTANT_ORDER] + [load("good")]
    seed = rows[-1]["seed"]
    os.makedirs(FRAMES, exist_ok=True)

    # the still figures are the ones make_figures.py just wrote
    result = Image.open(os.path.join(HERE, "result.png"))
    loop = Image.open(os.path.join(HERE, "loop.png"))

    frames = []

    def add(im, kicker, headline, body_lines):
        d = im.copy().convert("RGB")
        dd = ImageDraw.Draw(d)
        caption_frame(dd, kicker, headline, body_lines[0])
        y = still(dd, body_lines[1:], H - 100)
        frames.append(d)

    killed = sum(1 for r in rows[:-1] if not r["passed"])
    add(scale(result, (W, H)),
        "agent-next sandbox  ·  disposable, 2 vCPU  ·  seed %d" % seed,
        "The judge grades every artifact against the generator's own "
        "answer key",
        ["Left: field accuracy (G1, pass line 95 %).  Right: the gates each "
         "artifact cleared.",
         "One bar per graded artifact, all graded at seed %d." % seed,
         "A bar to the right of the dashed line still fails: G1 is only one "
         "of five gates."])

    for i, r in enumerate(rows):
        body = ["fails: " + ", ".join(r["failed"]) if not r["passed"]
                else "every gate passes"]
        add(scale(result, (W, H)),
            "iteration %d of %d  ·  seed %d" % (i + 1, len(rows), seed),
            "%s  —  field accuracy %.3f (%d/%d)"
            % (SHORT[r["name"]], r["accuracy"], r["correct"], r["slots"]),
            body + ["highlighted bar is the artifact graded in this step."])

    add(scale(loop, (W, H)),
        "self-test  ·  seed %d" % seed,
        "The judge is not a rubber stamp: %d/%d known-bad artifacts killed"
        % (killed, len(rows) - 1),
        ["Left: gates cleared per iteration, from the mutants to the "
         "known-good extractor.",
         "Right: kill rate against the >= 90 % rule the demo standard sets.",
         "A judge whose kill rate fell below 90 % would fail its own "
         "self-test."])

    out = []
    for i, im in enumerate(frames):
        # hold every frame for HOLD seconds
        p = os.path.join(FRAMES, "f%04d.png" % i)
        im.save(p)
        out.append(p)
    with open(os.path.join(FRAMES, "list.txt"), "w") as f:
        for p in out:
            for _ in range(int(HOLD * FPS)):
                f.write(p + "\n")
    n = int(HOLD * FPS * len(frames))
    print("[media] %d frames, %d encoded frames, %.1f s at %d fps"
          % (len(frames), n, n / float(FPS), FPS))


if __name__ == "__main__":
    main()