#!/usr/bin/env python3
"""Video frames for the code-interpreter-charts demo.

The analysis is not time-dependent, so the standard says: "a step-through of
the agent loop's figures with captions."  Each frame shows one of the three
charts with a caption explaining what the judge checks.  Frames are written
as lossless PNGs for ffmpeg to encode.

Usage: make_frames.py <outdir>
"""

import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

# Colour-blind-safe palette
INK = "#0b0b0b"
INK2 = "#52514e"
BLUE = "#2a78d6"
ORANGE = "#eb6834"
GREEN = "#0ca30c"

CAPTIONS = [
    ("c1_mauna_loa_trend.png",
     "C1: Mauna Loa monthly mean + OLS trend line",
     "G2/G4: slope = 2.098 ppm/yr (oracle: closed-form OLS)"),
    ("c2_seasonal_cycle.png",
     "C2: Mean seasonal cycle (12 months)",
     "G2/G4: amplitude = 5.834 ppm (max mean - min mean)"),
    ("c3_top_emitters_2024.png",
     "C3: Top 10 ISO-3166 emitters, 2024",
     "G2/G4: total = 37.398 Gt, top share = 0.3286 (China)"),
]

DEMO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOOD_DIR = os.path.join(DEMO_DIR, "examples", "good")


def make_frames(outdir):
    os.makedirs(outdir, exist_ok=True)
    frame = 0
    for png_name, title, caption in CAPTIONS:
        png_path = os.path.join(GOOD_DIR, "out", png_name)
        if not os.path.isfile(png_path):
            # Fall back to the mutant run directory
            alt = os.path.join(DEMO_DIR, "media", "judge_runs",
                               "replay", "good_out", png_name)
            if os.path.isfile(alt):
                png_path = alt
            else:
                sys.exit(f"make_frames: cannot find {png_name}")
        img = mpimg.imread(png_path)
        h, w = img.shape[:2]
        fig = plt.figure(figsize=(19.2, 10.8), dpi=100)
        fig.patch.set_facecolor("white")
        # Image in the upper portion, caption below
        ax = fig.add_axes([0.04, 0.22, 0.92, 0.72])
        ax.imshow(img)
        ax.axis("off")
        ax.set_title(title, fontsize=20, color=INK, pad=12)
        # Caption area
        fig.text(0.5, 0.10, caption, fontsize=16, color=INK2,
                 ha="center", va="center",
                 bbox=dict(facecolor="#f5f5f3", edgecolor="#cccccc",
                           boxstyle="round,pad=0.6"))
        fig.text(0.5, 0.03,
                 "code-interpreter-charts demo — agent-next sandbox judge",
                 fontsize=12, color=INK2, ha="center", va="center")
        out = os.path.join(outdir, f"frame_{frame:04d}.png")
        fig.savefig(out, dpi=100)
        plt.close(fig)
        frame += 1
    # Hold the last frame for a few seconds (duplicate it)
    last = os.path.join(outdir, f"frame_{frame - 1:04d}.png")
    for i in range(1, 5):
        import shutil
        shutil.copy2(last, os.path.join(outdir, f"frame_{frame:04d}.png"))
        frame += 1
    print(f"make_frames: wrote {frame} frames to {outdir}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: make_frames.py <outdir>")
    make_frames(sys.argv[1])
