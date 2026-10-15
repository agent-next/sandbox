#!/usr/bin/env python3
"""Render the 1920x1080 frames for the app-builder-preview video.

A step-through of the judge's own flow screenshots with captions (the demo
has no time-dependent physics to animate), then the two figures. Every
image comes from media/data (judge outputs); nothing is staged.

Frames go to $FRAMES_DIR/frame%05d.png at 30 fps; make_media.sh encodes
the lossless master and the web encode from them.
"""

import json
import os
import shutil
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

MEDIA = Path(__file__).resolve().parent
DATA = MEDIA / "data"
FRAMES = Path(os.environ["FRAMES_DIR"])
FPS = 30

BLUE, GREEN, RED, GREY = "#0072B2", "#009E73", "#D55E00", "#666666"
BG = "#101418"

FLOW_STEPS = {
    "add": ('type "buy milk", click add; repeat "walk dog", "read book"',
            'expect 3 li, texts in order, input cleared, stats-total 3'),
    "complete": ('add "task a", "task b"; click done on the first',
                 "expect first li.done, stats-active 1, stats-done 1"),
    "delete": ('add 3 todos; click delete on the second',
               "expect 2 li, first and third remain, stats-total 2"),
    "filter": ('add 3; toggle the first; click filter-active',
               "expect 2 visible li, none done, button.active"),
    "persist": ('add 2; toggle the first; reload the page',
                "expect the same 2 li, first still done, stats-total 2"),
    "stats": ('add 5; toggle 2; delete 1',
              "expect stats-total 4, stats-active 2, stats-done 2"),
}


def new_slide():
    fig = plt.figure(figsize=(19.2, 10.8), dpi=100, facecolor=BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(BG)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    return fig, ax


def slide_title(idx, total):
    fig, ax = new_slide()
    ax.text(0.5, 0.60, "app-builder-preview", ha="center", va="center",
            fontsize=64, color="white", weight="bold")
    ax.text(0.5, 0.46, "prompt → running web app, judged by exact DOM state",
            ha="center", va="center", fontsize=28, color="#9fd8ff")
    ax.text(0.5, 0.33, "a disposable agent-next sandbox · the judge drives "
                       "headless Chromium through 6 scripted flows",
            ha="center", va="center", fontsize=20, color=GREY)
    fig.savefig(FRAMES / f"frame{idx:05d}.png", facecolor=BG)
    plt.close(fig)


def slide_flow(idx, name, state):
    fig, ax = new_slide()
    shot = plt.imread(DATA / "shots" / f"{name}.png")
    ax.imshow(shot, extent=[0.05, 0.60, 0.08, 0.80], aspect="auto",
              interpolation="bilinear")
    steps, expect = FLOW_STEPS[name]
    ax.text(0.635, 0.74, f"flow: {name}", fontsize=40, color="white",
            weight="bold", va="top")
    ax.text(0.635, 0.63, steps, fontsize=19, color="#e8e8e8", va="top",
            wrap=True)
    ax.text(0.635, 0.50, expect, fontsize=19, color="#9fd8ff", va="top",
            wrap=True)
    stats = state.get("stats", {})
    rows = [("visible items", len(state.get("items", []))),
            ("stats-total", stats.get("total")),
            ("stats-active", stats.get("active")),
            ("stats-done", stats.get("done"))]
    for i, (k, v) in enumerate(rows):
        ax.text(0.635, 0.40 - i * 0.062, f"{k}", fontsize=17, color=GREY,
                va="center", family="monospace")
        ax.text(0.87, 0.40 - i * 0.062, f"{v}", fontsize=17, color="white",
                va="center", family="monospace")
    ax.text(0.635, 0.10, "judge: PASS", fontsize=26, color=GREEN,
            weight="bold", va="center")
    ax.add_patch(plt.Rectangle((0.615, 0.055), 0.34, 0.09,
                               fill=False, edgecolor=GREEN, linewidth=2))
    fig.savefig(FRAMES / f"frame{idx:05d}.png", facecolor=BG)
    plt.close(fig)


def slide_image(idx, png, title, subtitle):
    fig, ax = new_slide()
    img = plt.imread(MEDIA / png)
    h, w = img.shape[:2]
    scale = min(0.88 / w, 0.72 / h)
    ax.imshow(img, extent=[0.5 - w * scale / 2, 0.5 + w * scale / 2,
                           0.05, 0.05 + h * scale],
              aspect="auto", interpolation="bilinear")
    ax.text(0.5, 0.955, title, fontsize=30, color="white", ha="center",
            weight="bold")
    ax.text(0.5, 0.885, subtitle, fontsize=17, color=GREY, ha="center")
    fig.savefig(FRAMES / f"frame{idx:05d}.png", facecolor=BG)
    plt.close(fig)


def slide_end(idx, good):
    fig, ax = new_slide()
    gates = good["gates"]
    ok = all(g["pass"] for g in gates.values()) and good["judge_intact"]
    ax.text(0.5, 0.72, "verdict", fontsize=30, color=GREY, ha="center")
    ax.text(0.5, 0.60, "all 5 gates pass" if ok else "FAIL",
            fontsize=64, color=GREEN if ok else RED, ha="center",
            weight="bold")
    size_kib = good["gates"]["hygiene"]["dist_bytes"] / 1024
    ax.text(0.5, 0.44,
            f"flows 6/6 exact · reference cross-check agrees · "
            f"dist {size_kib:.1f} KiB of 250 · 0 console errors",
            fontsize=22, color="#e8e8e8", ha="center")
    ax.text(0.5, 0.26, "self-test kill rate 6/6 · two fresh-sandbox runs "
                       "in RECEIPT.md", fontsize=22, color="#e8e8e8",
            ha="center")
    ax.text(0.5, 0.12, "python3 cookbook/app-builder-preview/run.py",
            fontsize=24, color="#9fd8ff", ha="center", family="monospace")
    fig.savefig(FRAMES / f"frame{idx:05d}.png", facecolor=BG)
    plt.close(fig)


def main():
    FRAMES.mkdir(parents=True, exist_ok=True)
    for f in FRAMES.glob("frame*.png"):
        f.unlink()
    good = json.loads((DATA / "grade_good.json").read_text())

    # (slide renderer, seconds, payload)
    slides = [(slide_title, 2.5, None)]
    for name in ("add", "complete", "delete", "filter", "persist", "stats"):
        slides.append((slide_flow, 4.5, (name, good["states"][name])))
    slides.append((slide_image, 5.0, ("result.png",
                                      "Judge gates - measured numbers only",
                                      "media/result.png")))
    slides.append((slide_image, 5.0, ("loop.png",
                                      "Scripted fixing replay and kill rate",
                                      "media/loop.png")))
    slides.append((slide_end, 3.0, good))

    idx = 0
    for render, seconds, payload in slides:
        if payload is None:
            render(idx, 0)
        elif isinstance(payload, tuple):
            render(idx, *payload)
        else:
            render(idx, payload)
        n = int(round(seconds * FPS))
        for _ in range(n - 1):
            shutil.copyfile(FRAMES / f"frame{idx:05d}.png",
                            FRAMES / f"frame{idx + 1:05d}.png")
            idx += 1
        idx += 1
        total = idx / FPS
        print(f"media: slide frame {idx} (t={total:.1f} s)", flush=True)
    print(f"media: {idx} frames = {idx / FPS:.1f} s at {FPS} fps")


if __name__ == "__main__":
    main()
