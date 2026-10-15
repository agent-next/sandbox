#!/usr/bin/env python3
"""Derive the negative-control corpus for doc-extract-convert.

Takes a clean corpus (as written by judge/fixtures.py) and replaces two
named pages with pages an extractor must refuse to read:

    b0  blank   -- scanner fed an empty sheet: uniform paper, no ink
    b1  noise   -- scanner mis-fed / head failure: dense salt-and-pepper
                   speckle, no glyphs

The two replaced page ids are recorded in `corrupt.json` at the corpus
root -- deliberately *outside* pages/, the only directory the extractor
is pointed at, so the negative control cannot be read off the input.  It
is what lets judge/grade.sh check "quarantined exactly these two" as an
exact set comparison rather than a guess.

The corrupted pages carry no field values, so an extractor that invents a
plausible-looking record for them is caught by G4 regardless of how good
its OCR is.

Usage:
    python3 corrupt.py --in CLEAN_CORPUS --out CORRUPT_CORPUS
                       [--which b0,b1] [--seed 42]

Both directories are corpus roots (the ones judge/fixtures.py writes); the
corrupted pages replace pages under <out>/pages/.
"""

import argparse
import json
import os
import random
import shutil
import sys

from PIL import Image, ImageDraw

BLANK = "b0"
NOISE = "b1"
DEFAULT_WHICH = (BLANK, NOISE)

# Which corpus page each synthetic page replaces.  Fixed indices (not a
# random draw) so the negative control is the same two pages every run.
REPLACES = {BLANK: 1, NOISE: 6}          # inv-02 and inv-07


def make_blank(width, height):
    """Uniform paper with a faint scanner gradient and two dust specks."""
    img = Image.new("L", (width, height), 247)
    px = img.load()
    for y in range(height):
        shade = 247 - (y * 4) // height
        for x in range(width):
            px[x, y] = shade
    px[width // 3, height // 2] = 210
    px[(width * 2) // 3, height // 3] = 205
    return img


def make_smear(rng, width, height):
    """Mis-feed smear: roller streaks and a smudge, no glyphs at all.

    The point is a page that *looks* like it has content -- dark bands, a
    blob, a solid footer -- but carries no readable text.  An extractor
    that only asks "is this page blank?" will happily try to read it.

    Dense per-pixel speckle would be the other obvious corruption, but it
    makes tesseract's layout analysis grind for many minutes on 2 vCPU
    (measured: > 10 min for one page), which would blow the demo's runtime
    budget without testing anything the smear does not.
    """
    img = Image.new("L", (width, height), 247)
    draw = ImageDraw.Draw(img)
    for i in range(4):
        y = int(height * 0.16) + i * int(height * 0.20)
        draw.line((0, y, width, y + int(height * 0.07)), fill=168,
                  width=int(height * 0.045))
    draw.ellipse((int(width * 0.33), int(height * 0.47),
                  int(width * 0.69), int(height * 0.61)), fill=96)
    draw.rectangle((0, int(height * 0.90), width, height), fill=202)
    for _ in range(3000):
        x, y = rng.randrange(width), rng.randrange(height)
        img.putpixel((x, y), rng.randrange(120, 200))
    return img


def corrupt(clean_dir, out_dir, which, seed):
    with open(os.path.join(clean_dir, "pages", "pages.json")) as f:
        index = json.load(f)["pages"]
    pages = {p["page_id"]: p for p in index}
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    shutil.copytree(clean_dir, out_dir)

    rng = random.Random(seed + 7717)
    replaced = []
    for key in which:
        idx = REPLACES[key]
        if idx >= len(index):
            raise SystemExit("corrupt.py: no page at index %d to replace" % idx)
        page = index[idx]
        width, height = page["width"], page["height"]
        img = make_blank(width, height) if key == BLANK else make_smear(
            rng, width, height)
        img.save(os.path.join(out_dir, "pages", page["file"]), format="PNG",
                 optimize=True)
        replaced.append({"key": key, "page_id": page["page_id"],
                         "file": page["file"],
                         "reason_expected": "NO_TEXT" if key == BLANK
                         else "UNREADABLE_PAGE"})

    with open(os.path.join(out_dir, "corrupt.json"), "w") as f:
        json.dump({"seed": seed, "replaced": replaced}, f, indent=2)
        f.write("\n")
    return replaced


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--in", dest="in_dir", required=True)
    ap.add_argument("--out", dest="out_dir", required=True)
    ap.add_argument("--which", default=",".join(DEFAULT_WHICH))
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)

    which = tuple(w.strip() for w in args.which.split(",") if w.strip())
    unknown = [w for w in which if w not in REPLACES]
    if unknown:
        raise SystemExit("corrupt.py: unknown corruption key(s): %s"
                         % ", ".join(unknown))
    replaced = corrupt(args.in_dir, args.out_dir, which, args.seed)
    for r in replaced:
        print("[corrupt] %s -> %s (%s, expects %s)"
              % (r["key"], r["page_id"], r["file"], r["reason_expected"]))
    print("[corrupt] wrote %d corrupted page(s) into %s"
          % (len(replaced), args.out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
