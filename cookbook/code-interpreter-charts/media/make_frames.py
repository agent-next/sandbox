#!/usr/bin/env python3
"""Video frames for the code-interpreter-charts demo.

The analysis is not time-dependent, so the standard asks for "a step-through
of the agent loop's figures with captions": each frame shows one judged
chart with the gate numbers beside it, then the verdict summary and the
self-test kill rate.  Every caption number is read from the judge outputs of
this run (good.json, selftest_output.txt) — nothing is hardcoded.

Usage: make_frames.py <judge_runs_dir> <outdir>   (run via make_media.sh)
Writes frame_0000.png ... as lossless 1920x1080 PNGs for ffmpeg.
"""

import json
import os
import re
import shutil
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg

# dataviz reference palette (validated) — status + ink only here
GREEN = "#0ca30c"
RED = "#d03b3b"
BLUE = "#2a78d6"
INK = "#0b0b0b"
INK2 = "#52514e"


def need(path):
    if not os.path.isfile(path):
        sys.exit(f"make_frames: missing source file {path} — run the judge "
                 "first (see make_media.sh)")
    return path


def load_json(path):
    with open(path) as f:
        return json.load(f)


def chart_frames(good_out, verdict):
    """One frame per judged chart, captioned with its gate numbers."""
    g2 = verdict["gates"]["G2"]
    g3 = verdict["gates"]["G3"]
    frames = [
        ("c1_mauna_loa_trend.png",
         "C1: Mauna Loa monthly mean + OLS trend line",
         f"G2/G4: slope = {g2['mauna_loa_trend_ppm_per_year']['got']:.4f} "
         "ppm/yr (oracle: closed-form OLS) — "
         f"G3 plot variance {g3['C1']['plot_area_variance']:.0f}"),
        ("c2_seasonal_cycle.png",
         "C2: Mean seasonal cycle (12 months)",
         f"G2/G4: amplitude = "
         f"{g2['mauna_loa_seasonal_amplitude_ppm']['got']:.4f} ppm "
         f"(oracle: max mean − min mean) — G3 plot variance "
         f"{g3['C2']['plot_area_variance']:.0f}"),
        ("c3_top_emitters_2024.png",
         "C3: Top 10 ISO-3166 emitters, 2024",
         f"G2/G4: total = {g2['owid_world_emissions_2024_gt']['got']:.3f} Gt, "
         f"top share = {g2['owid_top_emitter_2024_share']['got']:.4f} — "
         "oracle: ISO-3166 regex sum"),
    ]
    for png_name, title, caption in frames:
        yield os.path.join(good_out, png_name), title, caption


def summary_frame(verdict, kill_line):
    """The verdict summary as a text frame (rendered, not an image)."""
    g2 = verdict["gates"]["G2"]
    lines = [
        ("Agent loop complete — judge verdict", 30, INK, "bold"),
        (f"passed: {verdict['passed']}   (gates G1–G5)", 20,
         GREEN if verdict["passed"] else RED, "bold"),
        (f"G2 trend      {g2['mauna_loa_trend_ppm_per_year']['got']:.6f} ppm/yr"
         f"   oracle {g2['mauna_loa_trend_ppm_per_year']['oracle']:.6f}", 17,
         INK, "normal"),
        (f"G2 amplitude  {g2['mauna_loa_seasonal_amplitude_ppm']['got']:.6f} ppm"
         f"   oracle {g2['mauna_loa_seasonal_amplitude_ppm']['oracle']:.6f}",
         17, INK, "normal"),
        (f"G2 total 2024 {g2['owid_world_emissions_2024_gt']['got']:.6f} Gt"
         f"   oracle {g2['owid_world_emissions_2024_gt']['oracle']:.6f}",
         17, INK, "normal"),
        (kill_line, 20, BLUE, "normal"),
        ("a judge it cannot fool: every number recomputed from the raw CSV",
         15, INK2, "normal"),
    ]
    fig = plt.figure(figsize=(19.2, 10.8), dpi=100)
    fig.patch.set_facecolor("white")
    for i, (text, size, color, weight) in enumerate(lines):
        fig.text(0.5, 0.78 - i * 0.09, text, fontsize=size, color=color,
                 ha="center", va="center", fontweight=weight)
    return fig


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: make_frames.py <judge_runs_dir> <outdir>")
    runs, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)

    verdict = load_json(need(os.path.join(runs, "good.json")))
    good_out = os.path.join(runs, "good_out")
    selftest_txt = open(
        need(os.path.join(runs, "selftest_output.txt"))).read()
    m = re.search(r"selftest: kill rate (\d+)/(\d+) = (\d+%)", selftest_txt)
    if not m:
        sys.exit("make_frames: no kill-rate line in selftest_output.txt")
    kill_line = f"self-test kill rate {m.group(1)}/{m.group(2)} = {m.group(3)}"

    frame = 0
    for png_path, title, caption in chart_frames(good_out, verdict):
        img = mpimg.imread(need(png_path))
        fig = plt.figure(figsize=(19.2, 10.8), dpi=100)
        fig.patch.set_facecolor("white")
        ax = fig.add_axes([0.14, 0.24, 0.72, 0.66])
        ax.imshow(img)
        ax.axis("off")
        ax.set_title(title, fontsize=22, color=INK, pad=14)
        fig.text(0.5, 0.11, caption, fontsize=17, color=INK2,
                 ha="center", va="center",
                 bbox=dict(facecolor="#f5f5f3", edgecolor="#cccccc",
                           boxstyle="round,pad=0.6"))
        fig.text(0.5, 0.035,
                 "code-interpreter-charts — agent-next sandbox judge",
                 fontsize=13, color=INK2, ha="center", va="center")
        fig.savefig(os.path.join(outdir, f"frame_{frame:04d}.png"), dpi=100)
        plt.close(fig)
        frame += 1

    fig = summary_frame(verdict, kill_line)
    fig.savefig(os.path.join(outdir, f"frame_{frame:04d}.png"), dpi=100)
    plt.close(fig)
    frame += 1

    # Hold the summary frame: 4 extra copies at the 4 s frame rate (the
    # encode's tpad adds 3 s more; total 35 s, inside the 20-60 s standard).
    last = os.path.join(outdir, f"frame_{frame - 1:04d}.png")
    for _ in range(4):
        shutil.copy2(last, os.path.join(outdir, f"frame_{frame:04d}.png"))
        frame += 1
    print(f"make_frames: wrote {frame} frames to {outdir}")


if __name__ == "__main__":
    main()
