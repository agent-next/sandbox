#!/usr/bin/env python3
"""Render the demo.mp4 frames into $FRAMES_DIR.

~35 s, 1920x1080 at 30 fps, four scenes separated by hard black cuts:

  1. the market tape: a rolling window of the strategy's daily net returns
     marching through the fixture day by day (the equity curve so far and
     the position strip underneath) -- a real animation, not a slide show
  2. the whole backtest held for a beat (the finished equity curve)
  3. the agent loop's deviation per attempt
  4. the self-test kill-rate bars, then a static end card

Every number comes from media/data/*.json (make_data.py writes those from
judge outputs).
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
TAPE_SEC = 18.0
TAPE_DAYS = 63             # trading days visible in the rolling window
HOLD_SEC = 1.5
CUT_SEC = 0.6
LOOP_SEC = 6.0
SELFTEST_SEC = 5.0
ENDCARD_SEC = 3.0

SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT2 = "#52514e"
GRID = "#e8e8e6"
S1 = "#2a78d6"
S2 = "#eb6834"
GOOD = "#0ca30c"
CRIT = "#d03b3b"
CARD_BG = "#0b0b0b"
CARD_FG = "#f5f4f2"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "text.color": TEXT, "axes.labelcolor": TEXT,
    "xtick.color": TEXT2, "ytick.color": TEXT2,
    "axes.edgecolor": TEXT2, "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
})


def load(name):
    return json.loads((DATA / name).read_text())


def draw_tape(fig, series, upto):
    """Scene 1: the rolling market tape ending at trading day `upto`.

    The window shifts a few days every frame, so every frame redraws the
    whole bar panel -- the video-gate's motion check sees real movement,
    not a slide show.
    """
    fig.clf()
    fig.patch.set_facecolor(SURFACE)
    gs = fig.add_gridspec(3, 1, height_ratios=[2.4, 0.7, 1.0], hspace=0.24)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1])
    ax3 = fig.add_subplot(gs[2])

    n = len(series["equity"])
    hi = min(upto + 1, n)
    lo = max(0, hi - TAPE_DAYS)
    x = np.arange(lo, hi)
    net = np.array(series["net"][lo:hi])
    pos = np.array(series["position"][lo:hi])

    up = net >= 0
    ax1.bar(x[up], net[up], width=1.0, color=GOOD, alpha=0.9)
    ax1.bar(x[~up], net[~up], width=1.0, color=CRIT, alpha=0.9)
    ax1.axhline(0.0, color=TEXT2, lw=0.8)
    m = max(abs(v) for v in series["net"]) * 1.08
    ax1.set_ylim(-m, m)
    ax1.set_xlim(lo - 0.5, lo + TAPE_DAYS - 0.5)
    ax1.set_ylabel("strategy net return\non the day")
    ax1.set_title(f"the market tape: {series['dates'][lo]} .. "
                  f"{series['dates'][hi - 1]}  (day {hi} of {n})",
                  fontsize=15)
    ax1.grid(alpha=0.3)
    ax1.tick_params(labelbottom=False)

    ax2.fill_between(x, pos, color=GOOD, alpha=0.5, lw=0, step="mid")
    ax2.plot(x, pos, color=GOOD, lw=0.9, drawstyle="steps-mid")
    ax2.set_ylim(-0.08, 1.15)
    ax2.set_yticks([0.0, 1.0])
    ax2.set_xlim(lo - 0.5, lo + TAPE_DAYS - 0.5)
    ax2.set_ylabel("position")
    ax2.grid(alpha=0.3)
    ax2.tick_params(labelbottom=False)

    xe = np.arange(hi)
    eq = np.array(series["equity"][:hi])
    ax3.plot(xe, eq, color=S1, lw=1.8)
    ax3.axhline(1.0, color=TEXT2, lw=1.0, ls=":")
    ax3.set_xlim(0, n)
    ax3.set_ylim(0.45, 1.65)
    ax3.set_ylabel("equity so far\n(1.0 at day 0)")
    ax3.set_xlabel(f"trading day of {n}  (0 = {series['dates'][0]})")
    ax3.grid(alpha=0.3)


def draw_scene(fig, series, metrics, upto):
    """Scene 2: the whole backtest, equity/drawdown/position panels."""
    fig.clf()
    fig.patch.set_facecolor(SURFACE)
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
    """Scene 3: the agent loop, deviation per attempt, to a fraction."""
    fig.clf()
    fig.patch.set_facecolor(SURFACE)
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
    """Scene 4: the self-test kill-rate bars, revealed to a fraction."""
    fig.clf()
    fig.patch.set_facecolor(SURFACE)
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


def draw_cut(fig):
    """A hard-cut frame: solid black, no content."""
    fig.clf()
    fig.patch.set_facecolor(CARD_BG)
    ax = fig.add_subplot(111)
    ax.set_facecolor(CARD_BG)
    ax.set_axis_off()


def draw_endcard(fig, metrics, selftest):
    """The static end card: the judge's verdict, held to the last frame."""
    fig.clf()
    fig.patch.set_facecolor(CARD_BG)
    ax = fig.add_subplot(111)
    ax.set_facecolor(CARD_BG)
    ax.set_axis_off()
    muts = selftest["mutants"]
    killed = sum(1 for m in muts.values() if m["verdict"] != "PASS")
    ax.text(0.5, 0.78, "backtest-equity", ha="center", va="center",
            fontsize=34, color=CARD_FG, weight="bold",
            transform=ax.transAxes)
    ax.text(0.5, 0.64, f"verdict {selftest['good_verdict']} -- all 6 gates",
            ha="center", va="center", fontsize=24, color=CARD_FG,
            transform=ax.transAxes)
    ax.text(0.5, 0.52,
            f"final equity {metrics['final_equity']:.4f} = the blind "
            f"reference's   |   Sharpe {metrics['sharpe']:.4f}   |   "
            f"max drawdown {metrics['max_drawdown']:.2%}",
            ha="center", va="center", fontsize=18, color=CARD_FG,
            transform=ax.transAxes)
    ax.text(0.5, 0.41, f"self-test: {killed}/{len(muts)} known-bad mutants "
            f"killed (requirement >= 90%)", ha="center", va="center",
            fontsize=18, color=CARD_FG, transform=ax.transAxes)
    ax.text(0.5, 0.18, "cookbook/backtest-equity  --  "
            "judge/grade.sh examples/good --seed 42",
            ha="center", va="center", fontsize=15, color="#9a9891",
            transform=ax.transAxes)


def main():
    curve = load("curve.json")
    series = load("series.json")
    metrics = load("metrics.json")
    replay = load("replay.json")
    selftest = load("selftest.json")
    n = curve["n_days"]

    FRAMES.mkdir(parents=True, exist_ok=True)
    fig = plt.figure(figsize=(W, H), dpi=100)
    idx = 0

    def shoot(draw, facecolor=SURFACE):
        nonlocal idx
        draw()
        fig.savefig(FRAMES / f"frame{idx:05d}.png", facecolor=facecolor)
        idx += 1

    # --- scene 1: the market tape, marching day by day --------------------
    # The whole 10-year path is covered in TAPE_SEC; the window shifts most
    # days, so each frame is a real redraw of the bar panel.
    tape_frames = int(TAPE_SEC * FPS)
    for f in range(tape_frames):
        upto = int(round((f + 1) / tape_frames * (n - 1)))
        shoot(lambda: draw_tape(fig, series, upto))

    # payoff: the finished curve held for a beat
    for _ in range(int(HOLD_SEC * FPS)):
        shoot(lambda: draw_scene(fig, series, metrics, n - 1))

    # hard cut
    for _ in range(int(CUT_SEC * FPS)):
        shoot(lambda: draw_cut(fig), facecolor=CARD_BG)

    # --- scene 2: the agent loop ------------------------------------------
    loop_frames = int(LOOP_SEC * FPS)
    for f in range(loop_frames):
        shoot(lambda f=f: draw_loop(fig, replay, (f + 1) / loop_frames))

    # hard cut
    for _ in range(int(CUT_SEC * FPS)):
        shoot(lambda: draw_cut(fig), facecolor=CARD_BG)

    # --- scene 3: the self-test kill rate ---------------------------------
    st_frames = int(SELFTEST_SEC * FPS)
    for f in range(st_frames):
        shoot(lambda f=f: draw_selftest(fig, selftest, (f + 1) / st_frames))

    # --- static end card ---------------------------------------------------
    for _ in range(int(ENDCARD_SEC * FPS)):
        shoot(lambda: draw_endcard(fig, metrics, selftest),
              facecolor=CARD_BG)

    plt.close(fig)
    total = idx / FPS
    print(f"video: {idx} frames ({total:.1f} s at {FPS} fps) in {FRAMES}")


if __name__ == "__main__":
    main()
