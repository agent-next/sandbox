#!/usr/bin/env python3
"""Generate the 8 known-bad batches (single-edit mutants of the good one).

    judge/mutants.py <good_batch_dir> <out_dir>

Each mutant is the good batch with exactly one scripted edit; every one must
fail at least one judge gate. Writes <out_dir>/<name>/ and prints the names.
"""

import json
import os
import shutil
import sys

from PIL import Image


def load_meta(art):
    with open(os.path.join(art, "meta.json")) as fh:
        return json.load(fh)


def save_meta(art, meta):
    with open(os.path.join(art, "meta.json"), "w") as fh:
        json.dump(meta, fh, indent=2)


def copy_batch(good, out, name):
    dest = os.path.join(out, name)
    shutil.copytree(good, dest)
    return dest


def edit_swap_prompts(art):
    # 4-cycle: 0->1->2->3->0 among the first four images
    imgdir = os.path.join(art, "images")
    paths = [os.path.join(imgdir, f"img_{i:02d}.png") for i in range(4)]
    data = [open(p, "rb").read() for p in paths]
    for p, d in zip(paths, [data[3], data[0], data[1], data[2]]):
        with open(p, "wb") as fh:
            fh.write(d)


def edit_blank_image(art):
    p = os.path.join(art, "images/img_05.png")
    Image.new("RGB", (512, 512), (128, 128, 128)).save(p)


def edit_wrong_resolution(art):
    p = os.path.join(art, "images/img_07.png")
    with Image.open(p) as im:
        im.resize((256, 256), Image.LANCZOS).save(p)


def edit_wrong_seed(art):
    meta = load_meta(art)
    meta["seeds"] = [s + 1 for s in meta["seeds"]]
    save_meta(art, meta)


def edit_duplicate_image(art):
    src = os.path.join(art, "images/img_09.png")
    dst = os.path.join(art, "images/img_10.png")
    with open(src, "rb") as fh:
        data = fh.read()
    with open(dst, "wb") as fh:
        fh.write(data)


def edit_stale_rerender(art):
    # replace a re-render with a different image (another prompt's render)
    src = os.path.join(art, "images/img_00.png")
    dst = os.path.join(art, "rerenders/img_03.png")
    with open(src, "rb") as fh:
        data = fh.read()
    with open(dst, "wb") as fh:
        fh.write(data)


def edit_corrupt_png(art):
    p = os.path.join(art, "images/img_13.png")
    with open(p, "rb") as fh:
        data = fh.read()
    with open(p, "wb") as fh:
        fh.write(data[: len(data) // 2])


def edit_bad_contact_sheet(art):
    p = os.path.join(art, "contact_sheet.png")
    with Image.open(p) as im:
        im.resize((1024, 1024), Image.LANCZOS).save(p)


MUTANTS = [
    ("swap_prompts", edit_swap_prompts),
    ("blank_image", edit_blank_image),
    ("wrong_resolution", edit_wrong_resolution),
    ("wrong_seed", edit_wrong_seed),
    ("duplicate_image", edit_duplicate_image),
    ("stale_rerender", edit_stale_rerender),
    ("corrupt_png", edit_corrupt_png),
    ("bad_contact_sheet", edit_bad_contact_sheet),
]


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: mutants.py <good_batch> <out_dir>")
    good, out = os.path.abspath(sys.argv[1]), sys.argv[2]
    os.makedirs(out, exist_ok=True)
    for name, edit in MUTANTS:
        dest = copy_batch(good, out, name)
        edit(dest)
        print(name)


if __name__ == "__main__":
    main()
