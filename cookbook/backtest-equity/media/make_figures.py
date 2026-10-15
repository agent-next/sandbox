#!/usr/bin/env python3
"""Render media/result.png and media/loop.png from media/data/*.json.

result.png -- the equity curve of the known-good artifact against the blind
reference (the two lie on top of each other, which is the point: the G2
oracle agreement), with the drawdown panel underneath and the pass line at
final equity 1.0.

loop.png -- the self-test kill rate per known-bad mutant (every bar "killed")
plus the agent-loop replay's equity error per iteration until pass.

Every plotted value comes from a judge output file written by make_data.py.
Palette: the validated reference categorical palette (blue slot 1) plus the
status palette for pass/killed states; labels always accompany color.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

MEDIA = Path(__file__).resolve().parent
DATA = MEDIA / "data"

# reference palette (dataviz skill, validated): light mode
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT2 = "#52514e"
GRID = "#e8e8e6"
S1 = "#2a78d6"   # categorical slot 1 (blue): the artifact's equity curve
S2 = "#eb6834"   # categorical slot 2 (orange): the blind reference
GOOD = "#0ca30c"     # status good (always with a label)
CRIT = "#d03b3b"     # status critical (always with a label)

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "text.color": TEXT, "axes.labelcolor": TEXT,
    "xtick.color": TEXT2, "ytick.color": TEXT2,
    "axes.edgecolor": TEXT2, "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
})


def load(name):
    return json.loads((DATA / name).read_text())


def make_result(series, metrics):
    equity = series["equity"]
    position = series["position"]
    drawdown = series["drawdown"]
    dates = series["dates"]
    n = len(equity)
    x = np.arange(n)

    fig, (ax1, ax2, ax3) = plt.subplots(
        3, 1, figsize=(11.2, 8.4), sharex=True,
        gridspec_kw={"height_ratios": [2.2, 0.9, 0.9]})

    # --- equity curve: artifact series == reference series ---------------
    ax1.plot(x, equity, color=S1, lw=1.6,
             label=f"known-good artifact equity (final {equity[-1]:.4f})")
    ax1.plot(x, [metrics["final_equity"]] * n, color=S2, lw=1.2, ls="--",
             label=f"blind reference final equity {metrics['final_equity']:.4f} "
                   "(G2 oracle)")
    ax1.axhline(1.0, color=TEXT2, lw=0.9, ls=":")
    ax1.text(n * 0.995, 1.0, " final equity 1.0 (spec pass line)",
             va="center", ha="right", fontsize=9, color=TEXT2)
    eq_hi = max(equity)
    eq_lo = min(equity)
    ax1.fill_between(x, equity, 1.0, color=S1, alpha=0.10)
    ax1.set_ylabel("equity (normalised to 1.0 at day 0)")
    ax1.set_ylim(min(0.45, eq_lo * 1.05), max(1.6, eq_hi * 1.05))
    ax1.set_title(
        "12/26 dual-momentum backtest on the pinned OHLCV fixture — "
        f"judge verdict PASS (all six gates)\n"
        f"final equity {equity[-1]:.6f}, Sharpe {metrics['sharpe']:.4f}, "
        f"max drawdown {metrics['max_drawdown']:.2%}, "
        f"{metrics['n_trades']} trades, 10 bps per side")
    ax1.legend(loc="upper left", fontsize=9, framealpha=0.9)
    ax1.grid(alpha=0.3)

    # --- drawdown panel, normalised 0..1 --------------------------------
    ax2.fill_between(x, drawdown, color=S2, alpha=0.35, lw=0)
    ax2.plot(x, drawdown, color=S2, lw=1.0)
    ax2.set_ylabel("drawdown\n(fraction of peak)")
    ax2.set_ylim(0, max(0.02, max(drawdown) * 1.15))
    ax2.grid(alpha=0.3)
    ax2.axhline(metrics["max_drawdown"], color=TEXT2, lw=0.9, ls=":")
    ax2.text(n * 0.995, metrics["max_drawdown"],
             f" max {metrics['max_drawdown']:.2%} (G4)", va="bottom",
             ha="right", fontsize=9, color=TEXT2)

    # --- position panel -------------------------------------------------
    ax3.fill_between(x, position, color=GOOD, alpha=0.45, lw=0, step="mid")
    ax3.plot(x, position, color=GOOD, lw=0.8, drawstyle="steps-mid")
    ax3.set_ylabel("position\n(long / flat)")
    ax3.set_ylim(-0.08, 1.15)
    ax3.set_yticks([0.0, 1.0])
    ax3.set_xlabel(f"trading day  (0 = {dates[0]}, {n - 1} = {dates[-1]})")
    ax3.grid(alpha=0.3)

    fig.tight_layout()
    fig.savefig(MEDIA / "result.png", dpi=200)
    plt.close(fig)
    print("figures: media/result.png")


def make_loop(replay, selftest):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11.2, 4.6),
                                   gridspec_kw={"width_ratios": [1.25, 1]})

    # --- agent loop: the judge's own failing measurement per attempt ----
    # an attempt the judge rejected at the schema gate never reached a
    # numeric oracle, so it has no measured deviation: its bar is annotated
    # with the failing gate instead of a number.
    steps = [r["step"] for r in replay]
    errs = [r["error"] if r["error"] is not None else 1e-12 for r in replay]
    colors = [GOOD if r["verdict"] == "PASS" else CRIT for r in replay]
    labels = [f"{r['error']:.1e}" if r["error"] is not None
              else "rejected: " + ", ".join(g[3:] for g in r["failed_gates"][:2])
              for r in replay]
    bars = ax1.bar(range(len(steps)), errs, color=colors, alpha=0.85)
    ax1.set_yscale("log")
    ax1.set_xticks(range(len(steps)))
    ax1.set_xticklabels(steps, rotation=35, ha="right", fontsize=8)
    ax1.set_ylabel("the judge's own measurement for that attempt,\n"
                   "as a deviation from its oracle (relative, log scale)")
    ax1.set_title("agent loop: the judge's failing measurement per attempt,\n"
                  "until the final attempt's verdict is PASS", fontsize=10)
    ax1.axhline(1e-3, color=TEXT2, lw=1.0, ls="--")
    ax1.axhline(1e-6, color=TEXT2, lw=1.0, ls="--")
    ax1.text(0.02, 1.2e-3, "G2 limit 1e-3", fontsize=8, color=TEXT2,
             transform=ax1.get_yaxis_transform())
    ax1.text(0.02, 1.2e-6, "G3/G4 limit 1e-6", fontsize=8, color=TEXT2,
             transform=ax1.get_yaxis_transform())
    for b, lb in zip(bars, labels):
        ax1.text(b.get_x() + b.get_width() / 2,
                 b.get_height() * 1.15, lb, ha="center", va="bottom",
                 fontsize=7, rotation=90, color=TEXT)
    ax1.grid(alpha=0.3, axis="y")

    # --- self-test kill rate per mutant ---------------------------------
    muts = selftest["mutants"]
    names = sorted(muts)
    killed = [1 if muts[k]["verdict"] != "PASS" else 0 for k in names]
    cols = [GOOD if k else CRIT for k in killed]
    ax2.bar(range(len(names)), killed, color=cols, alpha=0.85)
    ax2.set_xticks(range(len(names)))
    ax2.set_xticklabels(names, rotation=35, ha="right", fontsize=8)
    ax2.set_ylim(0, 1.4)
    ax2.set_yticks([0, 1])
    ax2.set_yticklabels(["PASS (miss)", "killed"])
    rate = 100 * sum(killed) / len(killed)
    ax2.set_title(f"self-test kill rate: {sum(killed)}/{len(killed)} "
                  f"= {rate:.0f}%  (requirement >= 90%)", fontsize=10)
    ax2.grid(alpha=0.3, axis="y")
    for i, k in enumerate(killed):
        ax2.text(i, 1.05, "killed" if k else "MISS", ha="center",
                 fontsize=8, color=TEXT)

    fig.tight_layout()
    fig.savefig(MEDIA / "loop.png", dpi=200)
    plt.close(fig)
    print("figures: media/loop.png")


def main():
    series = load("series.json")
    metrics = load("metrics.json")
    replay = load("replay.json")
    selftest = load("selftest.json")
    make_result(series, metrics)
    make_loop(replay, selftest)


if __name__ == "__main__":
    main()
