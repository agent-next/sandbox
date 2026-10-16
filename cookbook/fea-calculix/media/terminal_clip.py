#!/usr/bin/env python3
"""clips/terminal.mp4 -- this run's real console output, replayed at Nx.

The frames are a matplotlib-rendered terminal window scrolling through
work/run_logs/{setup,selftest,grade}.log -- captured live by
make_media.sh from this sandbox's own `bash judge/setup.sh`,
`judge/selftest.sh` and `judge/grade.sh examples/good --seed 42`
invocations, so every character on screen is real output of this run.

The "Nx" badge is computed: sum of the steps' measured wall seconds
(work/run_logs/timing.json, written alongside the logs) divided by the
clip's length in seconds. Never typed by hand.

Interface: main(fps, w, h, clips_dir, encode) -- called by
render_clips.py; `encode(frames_glob, out)` is its ffmpeg wrapper
(ffmpeg only encodes; matplotlib draws every pixel).
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

MEDIA = os.path.dirname(os.path.abspath(__file__))
LOGS = os.path.join(MEDIA, "work", "run_logs")

BG = "#0d1117"        # composition background
PANEL = "#010409"     # terminal body
CHROME = "#161b22"    # title bar
EDGE = "#30363d"
FG = "#c9d1d9"
DIM = "#7d8590"
GREEN = "#3fb950"
AMBER = "#d29922"

STEPS = [
    ("setup", "bash judge/setup.sh"),
    ("selftest", "bash judge/selftest.sh"),
    ("grade", "bash judge/grade.sh examples/good --seed 42"),
]
CLIP_S = 4.5
LINE_H = 26            # px of terminal body per text line
VISIBLE = 24           # lines visible in the window at once


def load_replay():
    """(lines, real_seconds): lines = [(text, style)] from the real logs."""
    timing = json.load(open(os.path.join(LOGS, "timing.json")))
    lines, real_s = [], 0.0
    for name, cmd in STEPS:
        real_s += float(timing[name + "_s"])
        lines.append((f"$ {cmd}", "cmd"))
        log = os.path.join(LOGS, name + ".log")
        for raw in open(log, encoding="utf-8", errors="replace"):
            lines.append((raw.rstrip("\n"), "out"))
        lines.append(("", "out"))
    return lines, real_s


def main(fps, w, h, clips_dir, encode):
    lines, real_s = load_replay()
    speed = real_s / CLIP_S                 # e.g. 283 s / 5 s = 57x
    n = int(CLIP_S * fps)

    # panel geometry (fraction of frame)
    px0, py0, pw, ph = 0.075, 0.10, 0.85, 0.80
    top_bar = 0.045 * ph

    fig = plt.figure(figsize=(w / 100, h / 100), dpi=100, facecolor=BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(BG)
    ax.axis("off")
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)

    # terminal panel
    ax.add_patch(FancyBboxPatch((px0 * w, py0 * h), pw * w, ph * h,
                                boxstyle="round,pad=0,rounding_size=18",
                                linewidth=1.5, edgecolor=EDGE,
                                facecolor=PANEL, zorder=1))
    ax.add_patch(FancyBboxPatch((px0 * w, (py0 + ph - top_bar) * h),
                                pw * w, top_bar * h,
                                boxstyle="round,pad=0,rounding_size=18",
                                linewidth=0, facecolor=CHROME, zorder=2))
    for i, c in enumerate(("#ff5f57", "#febc2e", "#28c840")):
        ax.add_patch(plt.Circle(((px0 + 0.018 + i * 0.018) * w,
                                 (py0 + ph - top_bar / 2) * h),
                                9, color=c, zorder=3))
    ax.text((px0 + 0.075) * w, (py0 + ph - top_bar / 2) * h,
            "agent sandbox -- fea-calculix", color=DIM, fontsize=17,
            family="monospace", va="center", zorder=3)

    # Nx badge -- computed, not typed
    badge = f"replayed at {speed:.0f}x speed"
    ax.text((px0 + pw - 0.02) * w, (py0 + ph - top_bar / 2) * h,
            badge, color="#0d1117", fontsize=16, family="monospace",
            fontweight="bold", va="center", ha="right", zorder=4,
            bbox=dict(boxstyle="round,pad=0.35", facecolor=AMBER,
                      edgecolor="none"))

    # text area inside panel
    tx = (px0 + 0.02) * w
    ty_top = (py0 + ph - top_bar) * h - 18
    ty_bot = py0 * h + 18
    line_px = (ty_top - ty_bot) / VISIBLE

    # scroll: whole log sweeps through over the clip, ease at the ends
    total = len(lines)
    scroll = np_lines_scroll(total)
    scr = scroll(n)

    texts = [ax.text(tx, 0, "", family="monospace", fontsize=15.5,
                     color=FG, va="center", zorder=5,
                     clip_on=True)
             for _ in range(VISIBLE + 2)]
    clip_rect = plt.Rectangle((px0 * w, py0 * h), pw * w,
                              (ph - top_bar) * h,
                              transform=ax.transData, fill=False)
    for t in texts:
        t.set_clip_path(clip_rect)

    d = os.path.join(MEDIA, "work", "clip_frames", "terminal")
    os.makedirs(d, exist_ok=True)
    for i in range(n):
        head = scr[i]
        for k, t in enumerate(texts):
            idx = int(head) - VISIBLE + k
            y = ty_bot + (VISIBLE - k - (head - int(head))) * line_px
            if 0 <= idx < total:
                txt, style = lines[idx]
                t.set_text(txt[:110])
                t.set_color({"cmd": GREEN, "out": FG}[style])
                t.set_fontweight("bold" if style == "cmd" else "normal")
                t.set_y(y)
                t.set_alpha(1.0)
            else:
                t.set_alpha(0.0)
        fig.savefig(os.path.join(d, f"f{i:04d}.png"), facecolor=BG)

    plt.close(fig)
    out = os.path.join(clips_dir, "terminal.mp4")
    encode(os.path.join(d, "f%04d.png"), out)
    print(f"clip terminal: {n} frames, {real_s:.0f}s real -> "
          f"{speed:.0f}x -> {out} ({os.path.getsize(out) / 1e6:.1f} MB)")


def np_lines_scroll(total):
    """Ease-in-out scroll of `total` log lines across VISIBLE rows."""
    import numpy as np
    span = max(1, total - VISIBLE)
    xs = np.linspace(0, 1, int(CLIP_S * 30))
    e = xs * xs * (3 - 2 * xs)                     # smoothstep
    head = VISIBLE + e * span                      # bottom line index

    def per_frame(n):
        return np.interp(np.linspace(0, 1, n), xs, head)
    return per_frame


if __name__ == "__main__":
    import subprocess
    main(30, 1920, 1080, os.path.join(MEDIA, "clips"),
         lambda g, o: subprocess.run(
             ["ffmpeg", "-y", "-v", "error", "-framerate", "30", "-i", g,
              "-c:v", "libx264", "-qp", "0", "-preset", "fast",
              "-pix_fmt", "yuv420p", o], check=True))
