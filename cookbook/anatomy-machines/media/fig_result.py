#!/usr/bin/env python3
"""result.png -- exploded showcase capture + the judge's verdict band.

The photograph is media/master/exploded.png, a real screenshot of
examples/good/four-stroke-engine rendered by Chrome Headless Shell +
SwiftShader at 1920x1080 (?shot&labels&explode=0.72&yaw=35, written by
render_media.py).  The band under it reports the measured gate values
from media/data/verdict-good.json -- nothing is invented.
"""

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
RAW = os.path.join(HERE, "master", "exploded.png")
OUT = os.path.join(HERE, "result.png")

BG = "#20242e"          # the shot-mode page background
FG = "#d7dae3"
DIM = "#8b90a0"
PASS = "#7dd48a"


def gate(v, n):
    return next(g for g in v["gates"] if g["gate"] == n)


def main():
    with open(os.path.join(DATA, "verdict-good.json")) as f:
        v = json.load(f)
    img = mpimg.imread(RAW)
    h, w = img.shape[:2]

    g2, g3, g4, g6 = (gate(v, n) for n in (2, 3, 4, 6))
    fps = v["timing"]["measured_fps"]
    cells = [
        ("loads clean",      "%d console errs" % gate(v, 1)["console_errors"]),
        ("rotates",          "var %d | mad %.1f" % (min(g2["variances"]),
                                                    min(g2["mean_abs_diffs"]))),
        ("parts",            "recall %d/%d" % (round(g3["recall"] *
                                                     g3["n_reference"]),
                                               g3["n_reference"])),
        ("interaction",      "%d/%d" % (g4["info_ok"], g4["info_total"])),
        ("frame rate",       "%.0f fps" % fps),
        ("capture quality",  "%d px | %.0f%% non-bg | %d ovl" %
                             (g6["w"], 100 * g6["nonbg_fraction"],
                              g6["label_overlaps"])),
    ]

    band = 118                      # px of verdict band under the image
    fig = plt.figure(figsize=(w / 100, (h + band) / 100), dpi=100)
    ax_img = fig.add_axes([0, band / (h + band), 1, h / (h + band)])
    ax_img.imshow(img)
    ax_img.axis("off")

    ax = fig.add_axes([0, 0, 1, band / (h + band)])
    ax.set_facecolor(BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.axhline(1.0, color="#3a3f4e", lw=1)

    ax.text(0.015, 0.62, "judge verdict", fontsize=12.5, color=DIM,
            family="DejaVu Sans Mono", va="center")
    ax.text(0.015, 0.24, "6/6 gates PASS", fontsize=16, color=PASS,
            family="DejaVu Sans Mono", va="center", weight="bold")
    x = 0.185
    step = (1 - x - 0.012) / len(cells)
    for name, val in cells:
        ax.text(x + step / 2, 0.62, name, fontsize=10.5, color=DIM,
                family="DejaVu Sans Mono", ha="center", va="center")
        ax.text(x + step / 2, 0.24, val, fontsize=11.5, color=FG,
                family="DejaVu Sans Mono", ha="center", va="center")
        x += step

    fig.savefig(OUT, dpi=100, facecolor=BG)
    print("fig_result: wrote", OUT)


if __name__ == "__main__":
    sys.exit(main())
