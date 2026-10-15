#!/usr/bin/env python3
"""Render the demo.mp4 frames into $FRAMES_DIR.

31 s, 1920x1080 at 30 fps: the equity curve and its drawdown/position panels
drawn day by day as the backtest runs, then the agent loop's deviation per
attempt, then the self-test kill-rate bars.  Every number comes from
media/data/*.json (make_data.py writes those from judge outputs).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

MEDIA = Path(__file__).resolve().parent
DATA = MEDIA / "data"
FRAMES = Path(os.environ.get("FRAMES_DIR", MEDIA / "master" / "frames"))

W, H = 19.2, 10.8          # inches at 100 dpi = 1920x1080
FPS = 30
REVEAL_SEC = 20.0
LOOP_SEC = 6.0
SELFTEST_SEC = 5.0

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT2 = "#52514e"
GRID = "#e8e8e6"
S1 = "#2a78d6"
S2 = "#eb6834"
GOOD = "#0ca30c"
CRIT = "#d03b3b"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "text.color": TEXT, "axes.labelcolor": TEXT,
    "xtick.color": TEXT2, "ytick.color": TEXT2,
    "axes.edgecolor": TEXT2, "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
})


def load(name):
    return json.loads((DATA / name).read_text())


def draw_scene(fig, series, metrics, upto):
    """The trading scene revealed up to trading day `upto` (inclusive)."""
    fig.clf()
    gs = fig.add_gridspec(3, 1, height_ratios=[2.2, 0.9, 0.9], hspace=0.22)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1], sharex=ax1)
    ax3 = fig.add_subplot(gs[2], sharex=ax1)

    n = len(series["equity"])
    x = np.arange(min(upto + 1, n))
    eq = np.array(series["equity"][:len(x)])
    dd = np.array(series["drawdown"][:len(x)])
    pos = np.array(series["position"][:len(x)])

    ax1.plot(x, eq, color=S1, lw=1.8)
    if len(x) > 1:
        ax1.fill_between(x, eq, 1.0, color=S1, alpha=0.12)
    ax1.axhline(1.0, color=TEXT2, lw=1.0, ls=":")
    if len(x) > 1:
        ax1.plot(x, [metrics["final_equity"]] * len(x), color=S2, lw=1.2,
                 ls="--", label=f"blind reference final equity "
                                f"{metrics['final_equity']:.4f} (G2 oracle)")
        ax1.legend(loc="upper left", fontsize=11, framealpha=0.9)
    ax1.set_ylabel("equity (normalised to 1.0 at day 0)")
    ax1.set_ylim(0.45, 1.65)
    ax1.set_title("12/26 dual-momentum backtest on the pinned OHLCV fixture",
                  fontsize=15)
    ax1.grid(alpha=0.3)

    if len(x) > 1:
        ax2.fill_between(x, dd, color=S2, alpha=0.35, lw=0)
        ax2.plot(x, dd, color=S2, lw=1.1)
        ax2.axhline(metrics["max_drawdown"], color=TEXT2, lw=1.0, ls=":")
        ax2.text(0.99, metrics["max_drawdown"],
                 f" max {metrics['max_drawdown']:.2%} (G4)", ha="right",
                 va="bottom", fontsize=10, color=TEXT2,
                 transform=ax2.get_yaxis_transform())
    ax2.set_ylabel("drawdown\n(fraction of peak)")
    ax2.set_ylim(0, 0.48)
    ax2.grid(alpha=0.3)

    if len(x) > 1:
        ax3.fill_between(x, pos, color=GOOD, alpha=0.45, lw=0, step="mid")
        ax3.plot(x, pos, color=GOOD, lw=0.9, drawstyle="steps-mid")
    ax3.set_ylabel("position\n(long / flat)")
    ax3.set_ylim(-0.08, 1.15)
    ax3.set_yticks([0.0, 1.0])
    ax3.set_xlabel(f"trading day of {n}  (0 = {series['dates'][0]})")
    ax3.set_xlim(0, n)
    ax3.grid(alpha=0.3)


def draw_loop(fig, replay, frac):
    """The agent loop: deviation per attempt, revealed to a fraction."""
    fig.clf()
    ax = fig.add_subplot(111)
    steps = [r["step"] for r in replay]
    errs = [r["error"] if r["error"] else 1e-9 for r in replay]
    colors = [GOOD if r["verdict"] == "PASS" else CRIT for r in replay]
    show = max(1, int(round(frac * len(steps))))
    ax.bar(range(show), errs[:show], color=colors[:show], alpha=0.88)
    ax.set_yscale("log")
    ax.set_xticks(range(len(steps)))
    ax.set_xticklabels(steps, rotation=32, ha="right", fontsize=11)
    ax.set_ylabel("the judge's measurement for that attempt,\n"
                  "as a deviation from its oracle (relative, log scale)")
    ax.set_ylim(1e-10, 3.0)
    ax.axhline(1e-3, color=TEXT2, lw=1.2, ls="--")
    ax.text(0.01, 1.3e-3, "G2 limit 1e-3", fontsize=11, color=TEXT2)
    ax.set_title("the agent loop: each failed attempt's deviation, "
                 "until the judge passes", fontsize=15)
    ax.grid(alpha=0.3, axis="y")
    for i in range(show):
        ax.text(i, errs[i] * 1.3, f"{errs[i]:.1e}", ha="center", fontsize=9,
                rotation=90, color=TEXT)


def draw_selftest(fig, selftest, frac):
    """The self-test kill-rate bars, revealed to a fraction."""
    fig.clf()
    ax = fig.add_subplot(111)
    muts = selftest["mutants"]
    names = sorted(muts)
    killed = [1 if muts[k]["verdict"] != "PASS" else 0 for k in names]
    show = max(1, int(round(frac * len(names))))
    cols = [GOOD if k else CRIT for k in killed[:show]]
    ax.bar(range(show), killed[:show], color=cols, alpha=0.88)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(names, rotation=32, ha="right", fontsize=11)
    ax.set_ylim(0, 1.45)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["PASS (miss)", "killed"])
    ax.set_title(f"self-test kill rate: "
                 f"{sum(killed[:show])}/{show} of the known-bad mutants "
                 f"killed  (requirement >= 90%)", fontsize=15)
    ax.grid(alpha=0.3, axis="y")
    for i in range(show):
        ax.text(i, 1.06, "killed" if killed[i] else "MISS", ha="center",
                fontsize=10, color=TEXT)
        gates = muts[names[i]]["failed"]
        ax.text(i, 0.06, ", ".join(g[3:] for g in gates[:2]), ha="center",
                va="bottom", fontsize=8, color=TEXT2, rotation=90)


def main():
    curve = load("curve.json")
    series = load("series.json")
    metrics = load("metrics.json")
    replay = load("replay.json")
    selftest = load("selftest.json")
    n = curve["n_days"]

    FRAMES.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(W, H), dpi=100)

    reveal = int(REVEAL_SEC * FPS)
    idx = 0

    # --- scene 1: the backtest running, day by day ----------------------
    # The long quiet stretches are stepped through so the whole 10-year
    # path is covered in 20 s; the trading days are shown one frame each.
    for f in range(reveal):
        upto = int(round((f + 1) / reveal * (n - 1)))
        draw_scene(fig, series, metrics, upto)
        fig.savefig(FRAMES / f"frame{idx:05d}.png")
        plt.close(fig)
        fig = plt.figure(figsize=(W, H), dpi=100)
        idx += 1

    # finale: the finished curve held for a beat
    hold = int(1.5 * FPS)
    for _ in range(hold):
        draw_scene(fig, series, metrics, n - 1)
        fig.savefig(FRAMES / f"frame{idx:05d}.png")
        plt.close(fig)
        fig = plt.figure(figsize=(W, H), dpi=100)
        idx += 1

    # --- scene 2: the agent loop -----------------------------------------
    loop_frames = int(LOOP_SEC * FPS)
    for f in range(loop_frames):
        draw_loop(fig, replay, (f + 1) / loop_frames)
        fig.savefig(FRAMES / f"frame{idx:05d}.png")
        plt.close(fig)
        fig = plt.figure(figsize=(W, H), dpi=100)
        idx += 1

    # --- scene 3: the self-test kill rate --------------------------------
    st_frames = int(SELFTEST_SEC * FPS)
    for f in range(st_frames):
        draw_selftest(fig, selftest, (f + 1) / st_frames)
        fig.savefig(FRAMES / f"frame{idx:05d}.png")
        plt.close(fig)
        fig = plt.figure(figsize=(W, H), dpi=100)
        idx += 1

    plt.close(fig)
    total = idx / FPS
    print(f"video: {idx} frames ({total:.1f} s at {FPS} fps) in {FRAMES}")


if __name__ == "__main__":
    main()
