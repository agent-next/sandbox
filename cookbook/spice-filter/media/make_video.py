#!/usr/bin/env python3
"""Render demo.mp4 frames for the spice-filter demo.

Animates:
1. Ideal and GBW-limited sweeps drawn against the spec mask
2. The finished result held, with the passband inset
3. Agent-loop replay, then the self-test kill-rate bars

Every frame comes from real judge data -- no invented traces.
"""
import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
import numpy as np

MEDIA = Path(__file__).resolve().parent
DATA = MEDIA / "data"
FRAMES_DIR = Path(os.environ.get("FRAMES_DIR", MEDIA / "frames"))

# reference palette (dataviz skill, validated): light mode
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT2 = "#52514e"
GRID = "#e8e8e6"
S1 = "#2a78d6"   # categorical slot 1 (blue): nominal response
S2 = "#eb6834"   # categorical slot 2 (orange): GBW macro-model
GOOD = "#0ca30c"     # status good (with label)
CRIT = "#d03b3b"     # status critical (with label)
MASK = TEXT2     # spec mask lines wear ink, not series color

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "text.color": TEXT, "axes.labelcolor": TEXT,
    "xtick.color": TEXT2, "ytick.color": TEXT2,
    "axes.edgecolor": TEXT2, "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
})

REPLAY_LABELS = {
    "r-decade-up": "R1 a decade too large",
    "off-series": "values off the E-series",
    "unrecognised-topology": "topology the oracle\n cannot verify",
    "good": "final design",
}

def load(name):
    return json.loads((DATA / name).read_text())


def draw_result_base(ax_main, ax_diff, sweep, show_analytic_note=True, show_mask=True):
    """Draw the static base of the Bode figure (mask, grid, labels)."""
    nom = sweep["nominal"]
    gbw = sweep["gbw_macromodel"]
    mask = sweep["mask"]
    f = nom["freq"]

    ax_main.set_xscale("log")
    ax_main.set_xlim(10, 100_000)
    ax_main.set_ylim(-145, 5)
    ax_main.set_xlabel("frequency (Hz)")
    ax_main.set_ylabel("gain (dB rel. DC)")
    ax_main.grid(True, which="major", color=GRID, lw=0.6)
    ax_main.set_axisbelow(True)

    if show_mask:
        # passband mask: +-1 dB around DC, 10 Hz..1 kHz
        ax_main.fill_between([10, 1000], -1.0, 1.0,
                             color=GRID, alpha=0.55, lw=0)
        # stopband mask: <= -40 dB for f >= 10 kHz
        ax_main.fill_between([10_000, 100_000], -145, mask["stop_max_db"],
                             color=GRID, alpha=0.55, lw=0)
        # Thinner, dark grey mask lines per LEAD VISUAL REVIEW v4
        ax_main.plot([10, 1000], [mask["ripple_max_db"]] * 2,
                     color=MASK, lw=1.0, ls=(0, (4, 3)))
        ax_main.plot([10, 1000], [-mask["ripple_max_db"]] * 2,
                     color=MASK, lw=1.0, ls=(0, (4, 3)))
        ax_main.plot([10_000, 100_000], [mask["stop_max_db"]] * 2,
                     color=MASK, lw=1.0, ls=(0, (4, 3)))
        ax_main.axvline(1000, color=GRID, lw=1.0)
        ax_main.axvline(10_000, color=GRID, lw=1.0)
        # Position ripple mask label at y = -12 dB, x = 15 Hz, left-aligned,
        # with white bbox so it overlaps no line
        ax_main.text(15, -12, "mask: ripple ≤ 1 dB to 1 kHz",
                     fontsize=9, color=TEXT2, ha="left",
                     bbox=dict(boxstyle="round,pad=0.2", fc=SURFACE, ec="none"))
        ax_main.text(10_400, -37, "mask: ≤ −40 dB from 10 kHz",
                     fontsize=9, color=TEXT2)

    if show_analytic_note:
        ax_main.plot([], [], color=MASK, lw=1.4, ls=(0, (4, 3)),
                     label="spec mask")

    # Diff panel base
    ax_diff.set_xscale("log")
    ax_diff.set_xlim(10, 100_000)
    ax_diff.set_ylim(-0.6, 0.6)
    ax_diff.set_xlabel("frequency (Hz)")
    ax_diff.set_ylabel("GBW − ideal (dB)")
    ax_diff.grid(True, which="major", color=GRID, lw=0.5)
    ax_diff.set_axisbelow(True)
    ax_diff.axhline(0, color=TEXT2, lw=0.5)
    ax_diff.axhline(0.5, color=CRIT, lw=0.7, ls=(0, (2, 2)))
    ax_diff.axhline(-0.5, color=CRIT, lw=0.7, ls=(0, (2, 2)))
    ax_diff.tick_params(labelsize=8)
    ax_main.tick_params(labelbottom=False)
    ax_main.set_xlabel("")


def draw_nominal_curve(ax_main, sweep, progress):
    """Draw the nominal (ideal op-amp) curve up to progress fraction."""
    nom = sweep["nominal"]
    f = nom["freq"]
    n = max(2, int(len(f) * progress))
    fs, dbs = f[:n], nom["gain_db"][:n]
    ax_main.plot(fs, dbs, color=S1, lw=2.2, zorder=2,
                 label="ngspice AC response (ideal op-amp)")


def draw_gbw_curve(ax_main, sweep, progress):
    """Draw the 1 MHz-GBW macro-model curve up to progress fraction."""
    gbw = sweep["gbw_macromodel"]
    f = gbw["freq"]
    n = max(2, int(len(f) * progress))
    fs, dbs = f[:n], gbw["gain_db"][:n]
    ax_main.plot(fs, dbs, color=S2, lw=2.0, ls=(0, (4, 3)), zorder=3,
                 label=f"1 MHz-GBW op-amp macro-model (dev {gbw['max_dev_vs_analytic_db']:.3f} dB)")


def draw_diff_curve(ax_diff, sweep, progress):
    """Draw the difference curve (GBW - ideal) up to progress fraction."""
    nom = sweep["nominal"]
    gbw = sweep["gbw_macromodel"]
    n = max(2, int(len(nom["freq"]) * progress))
    fs = nom["freq"][:n]
    diff_db = [g - i for g, i in zip(gbw["gain_db"][:n], nom["gain_db"][:n])]
    ax_diff.plot(fs, diff_db, color=S2, lw=1.5, zorder=3)
    # Mark max deviation point
    if n > 1:
        max_dev_idx = max(range(n), key=lambda i: abs(diff_db[i]))
        ax_diff.plot(fs[max_dev_idx], diff_db[max_dev_idx], 'o', color=S2, ms=4)


def draw_legend(ax):
    ax.legend(loc="lower left", fontsize=9, frameon=False)


def draw_stamp(ax, stamp_text, color=GOOD):
    ax.text(0.985, 0.90, stamp_text, transform=ax.transAxes, ha="right",
            fontsize=11, fontweight="bold", color=color,
            bbox=dict(boxstyle="round,pad=0.35", fc=SURFACE,
                      ec=color, lw=1.6))


def draw_inset(ax_main, sweep):
    """Draw inset zoom showing passband/corner where GBW deviation is visible."""
    nom = sweep["nominal"]
    gbw = sweep["gbw_macromodel"]
    mask = sweep["mask"]
    fs = nom["freq"]
    gs = gbw["freq"]
    dbs = nom["gain_db"]

    # Data-driven annotations for inset (passband edge @ 1 kHz, -3 dB corner)
    idx_1k = min(range(len(fs)), key=lambda i: abs(fs[i] - 1000))
    gain_1k = dbs[idx_1k]
    idx_3db = min(range(len(dbs)), key=lambda i: abs(dbs[i] + 3))
    f_3db = fs[idx_3db]
    gain_3db = dbs[idx_3db]

    # Between the ripple-mask label (top) and the legend (bottom left)
    inset = ax_main.inset_axes([0.18, 0.40, 0.32, 0.30])
    inset.set_xscale("log")
    inset.set_xlim(100, 10_000)
    inset.set_ylim(-3.5, 0.5)
    inset.grid(True, which="major", color=GRID, lw=0.4)
    inset.set_axisbelow(True)
    inset.tick_params(labelsize=9)  # fontsize >= 9 per review
    inset.set_xlabel("frequency (Hz)", fontsize=9)
    inset.set_ylabel("dB", fontsize=9)
    # Plot both curves in inset: GBW dashed on top
    inset.plot(gs, gbw["gain_db"], color=S2, lw=1.8, ls=(0, (3, 2)), zorder=3,
               label="1 MHz-GBW macro-model")
    inset.plot(fs, nom["gain_db"], color=S1, lw=1.8, zorder=2,
               label="ideal op-amp")
    # Mask lines in inset
    inset.plot([100, 1000], [mask["ripple_max_db"]] * 2,
               color=MASK, lw=1.0, ls=(0, (3, 2)))
    inset.plot([100, 1000], [-mask["ripple_max_db"]] * 2,
               color=MASK, lw=1.0, ls=(0, (3, 2)))
    # Vertical dotted line at 1 kHz passband edge
    inset.axvline(1000, color=MASK, lw=1.0, ls=(0, (4, 3)))
    inset.axvline(10_000, color=GRID, lw=0.5)
    # Connection lines from main to inset
    inset.plot([100, 100], [-3.5, 0.5], color=GRID, lw=0.3)
    inset.plot([10_000, 10_000], [-3.5, 0.5], color=GRID, lw=0.3)

    # Annotations: passband edge @ 1 kHz and -3 dB corner
    # Passband edge marker and label
    inset.plot(1000, gain_1k, 'o', color=S1, ms=4, zorder=4)
    inset.annotate(f"−{abs(gain_1k):.3f} dB @ 1 kHz",
                   (1000, gain_1k),
                   textcoords="offset points", xytext=(-8, -14), ha="right",
                   fontsize=7, color=S1,
                   bbox=dict(boxstyle="round,pad=0.2", fc=SURFACE, ec=S1, lw=0.5))
    # -3 dB point marker and label
    inset.plot(f_3db, gain_3db, 'o', color=S2, ms=4, zorder=4)
    inset.annotate(f"−3 dB @ {f_3db:.0f} Hz",
                   (f_3db, gain_3db),
                   textcoords="offset points", xytext=(-10, 0), va="center", ha="right",
                   fontsize=7, color=S2,
                   bbox=dict(boxstyle="round,pad=0.2", fc=SURFACE, ec=S2, lw=0.5))
    # Passband edge label on the vertical line
    inset.annotate("passband edge\n1 kHz",
                   (1000, 0.5),
                   textcoords="offset points", xytext=(0, 3), va="bottom",
                   fontsize=7, color=MASK, ha="center",
                   bbox=dict(boxstyle="round,pad=0.2", fc=SURFACE, ec=MASK, lw=0.5))


def render_frame(idx, total, sweep, replay, selftest, good_verdict):
    """Render a single frame."""
    fig = plt.figure(figsize=(19.2, 10.8), dpi=100)  # 1920x1080

    # Two rows: main plot (larger) + diff panel (smaller)
    gs = GridSpec(2, 1, height_ratios=[3, 1], hspace=0.05)
    ax_main = fig.add_subplot(gs[0])
    ax_diff = fig.add_subplot(gs[1])

    # Phase 1: Frequency sweep animation (frames 0-299 = 10s at 30fps)
    # Phase 2: Hold the finished result (frames 300-599 = 10s)
    # Phase 3: Kill-rate bars (frames 600-899 = 10s)
    # Phase 4: Final static (frames 900-1199 = 10s)

    mc = good_verdict["gates"]["mask"]
    stamp = (f"PASS  ·  ripple {mc['ripple_db']} dB ≤ 1.0\n"
             f"stopband {mc['stopband_max_db']} dB ≤ −40")

    if idx < 300:
        # Phase 1: Sweep drawing
        progress = (idx + 1) / 300
        draw_result_base(ax_main, ax_diff, sweep)
        draw_nominal_curve(ax_main, sweep, progress)

        if idx >= 150:
            gbw_progress = min(1.0, (idx - 150) / 150)
            draw_gbw_curve(ax_main, sweep, gbw_progress)
            draw_diff_curve(ax_diff, sweep, gbw_progress)

        draw_legend(ax_main)

        if progress >= 1.0:
            draw_stamp(ax_main, stamp)
            draw_inset(ax_main, sweep)

    elif idx < 600:
        # Phase 2: hold the finished result
        draw_result_base(ax_main, ax_diff, sweep)
        draw_nominal_curve(ax_main, sweep, 1.0)
        draw_gbw_curve(ax_main, sweep, 1.0)
        draw_diff_curve(ax_diff, sweep, 1.0)
        draw_legend(ax_main)
        draw_stamp(ax_main, stamp)
        draw_inset(ax_main, sweep)

    elif idx < 900:
        # Phase 3: Kill-rate bars animation
        progress = (idx - 600) / 300
        # Replay on top, kill-rate bars below, each on its own axes
        ax_main.remove()
        ax_diff.remove()
        gs3 = GridSpec(2, 1, height_ratios=[1, 1], hspace=0.45)
        ax_main = fig.add_subplot(gs3[0])
        ax_kill = fig.add_subplot(gs3[1])
        ax_main.set_xlim(0.45, 4.55)
        ax_main.set_ylim(-0.75, 1.75)
        ax_main.set_yticks([0, 1])
        ax_main.set_yticklabels(["fail", "pass"], fontsize=12)
        ax_main.set_xticks([1, 2, 3, 4])
        ax_main.set_xticklabels(["iteration 1", "iteration 2", "iteration 3", "iteration 4"], fontsize=11)
        for s in ("top", "right"):
            ax_main.spines[s].set_visible(False)

        # Animate points appearing
        ys, labels, colors = [], [], []
        for i, v in enumerate(replay):
            if progress > i / 4:
                ok = v["passed"]
                ys.append(1 if ok else 0)
                gate = v.get("failed_gate", "all gates")
                labels.append(f"it {i+1}: {REPLAY_LABELS[v['label']]}\n"
                              f"{'PASS — all gates' if ok else 'fail: ' + gate}")
                colors.append(GOOD if ok else CRIT)

        if ys:
            xs = range(1, len(ys) + 1)
            ax_main.plot(xs, ys, color=GRID, lw=2, zorder=1)
            ax_main.scatter(xs, ys, s=120, c=colors, zorder=3)
            for x, y, lab, c in zip(xs, ys, labels, colors):
                ax_main.annotate(lab, (x, y), textcoords="offset points",
                                 xytext=(0, 18),
                                 ha="center", fontsize=10,
                                 color=TEXT if y == 0 else TEXT2, zorder=4,
                                 bbox=dict(fc=SURFACE, ec="none", pad=1))
        ax_main.set_title("Agent-loop replay: the gate that failed per iteration "
                          "(scripted replay, not a live trace)", fontsize=14)

        kills = selftest["kills"]
        ax_kill.set_xlim(-0.6, len(kills) + 0.6)
        ax_kill.set_ylim(-0.6, 1.35)
        ax_kill.axis("off")
        n_bars = max(1, int((len(kills) + 1) * progress))
        for i in range(n_bars):
            if i == 0:
                ax_kill.bar([0], [1], width=0.72, color=GOOD, edgecolor=SURFACE, lw=3)
                ax_kill.text(0, 1.08, "known-good\npasses", ha="center", fontsize=10, color=TEXT2)
            else:
                k = kills[i-1]
                ax_kill.bar([i], [1], width=0.72, color=GOOD if k["passed"] else CRIT,
                            edgecolor=SURFACE, lw=3)
                ax_kill.text(i, 0.5, "survived" if k["passed"] else "killed", ha="center", va="center", fontsize=9,
                             color=SURFACE, rotation=90)
                ax_kill.text(i, -0.08, k["mutant"].replace("-", "\n", 1),
                             ha="center", va="top", fontsize=8, color=TEXT2)
                ax_kill.text(i, -0.45, k["failed_gate"], ha="center", fontsize=9,
                             color=CRIT, fontweight="bold")
        killed = sum(1 for k in kills if not k["passed"])
        ax_kill.set_title(f"Self-test kill rate: {killed}/{len(kills)}", fontsize=14)

    else:
        # Phase 4: Final composite
        draw_result_base(ax_main, ax_diff, sweep)
        draw_nominal_curve(ax_main, sweep, 1.0)
        draw_gbw_curve(ax_main, sweep, 1.0)
        draw_diff_curve(ax_diff, sweep, 1.0)
        draw_legend(ax_main)
        draw_stamp(ax_main, stamp)
        draw_inset(ax_main, sweep)

    fig.tight_layout()
    frame_path = FRAMES_DIR / f"frame{idx:05d}.png"
    fig.savefig(frame_path, dpi=100, facecolor=SURFACE)
    plt.close(fig)
    if idx % 30 == 0:
        print(f"  frame {idx}/{total-1}")


def main():
    sweep = load("sweep_good.json")
    replay = load("replay.json")
    selftest = load("selftest.json")
    good = [v for v in replay if v["passed"]][0]

    FRAMES_DIR.mkdir(parents=True, exist_ok=True)

    # 40 seconds at 30fps = 1200 frames
    total_frames = 1200
    print(f"Rendering {total_frames} frames...")
    for i in range(total_frames):
        render_frame(i, total_frames, sweep, replay, selftest, good)
    print("Done rendering frames")


if __name__ == "__main__":
    main()