#!/usr/bin/env python3
"""Render media/result.png and media/loop.png from media/data/*.json.

Every plotted value comes from a judge output file (grade verdict JSONs or
the judge engine's own ngspice sweeps written by make_data.py).  Palette:
the validated reference categorical palette (blue/orange slots 1-2) plus
the status palette for pass/killed states; labels always accompany color.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.gridspec import GridSpec  # noqa: E402

MEDIA = Path(__file__).resolve().parent
DATA = MEDIA / "data"

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


def draw_result(ax_main, ax_diff, sweep, show_analytic_note=True,
                show_gbw=1.0, show_mask=True, stamp=None, add_inset=True):
    """The key Bode figure. show_gbw (0..1) the macro-model curve.
    The diff panel shows GBW - ideal in dB (shared x-axis).
    """
    nom = sweep["nominal"]
    gbw = sweep["gbw_macromodel"]
    mask = sweep["mask"]
    f = nom["freq"]
    dbs = nom["gain_db"]
    gdbs = gbw["gain_db"]
    fs = f
    gs = gbw["freq"]

    # Data-driven annotations for inset (passband edge @ 1 kHz, -3 dB corner)
    idx_1k = min(range(len(fs)), key=lambda i: abs(fs[i] - 1000))
    gain_1k = dbs[idx_1k]
    idx_3db = min(range(len(dbs)), key=lambda i: abs(dbs[i] + 3))
    f_3db = fs[idx_3db]
    gain_3db = dbs[idx_3db]

    # Main plot
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

    # Draw ideal curve first (lower zorder)
    if fs:
        ax_main.plot(fs, dbs, color=S1, lw=2.2, zorder=2,
                     label="ngspice AC response (ideal op-amp)")

    # Draw GBW curve dashed and on top (higher zorder)
    if gs:
        ax_main.plot(gs, gdbs, color=S2, lw=2.0, ls=(0, (4, 3)), zorder=3,
                     label=f"1 MHz-GBW op-amp macro-model "
                           f"(dev {gbw['max_dev_vs_analytic_db']:.3f} dB)")

    if show_analytic_note:
        ax_main.plot([], [], color=MASK, lw=1.4, ls=(0, (4, 3)),
                     label="spec mask")
    ax_main.legend(loc="lower left", fontsize=9, frameon=False)

    # PASS stamp inside axes, top-right, below title
    if stamp:
        ax_main.text(0.985, 0.90, stamp, transform=ax_main.transAxes, ha="right",
                     fontsize=11, fontweight="bold", color=GOOD,
                     bbox=dict(boxstyle="round,pad=0.35", fc=SURFACE,
                               ec=GOOD, lw=1.6))

    # Difference panel (shared x-axis)
    # Compute difference: GBW - ideal (in dB)
    diff_db = [g - i for g, i in zip(gdbs, dbs)]
    ax_diff.set_xscale("log")
    ax_diff.set_xlim(10, 100_000)
    ax_diff.set_ylim(-0.6, 0.6)
    ax_diff.set_xlabel("frequency (Hz)")
    ax_diff.set_ylabel("GBW − ideal (dB)")
    ax_diff.grid(True, which="major", color=GRID, lw=0.5)
    ax_diff.set_axisbelow(True)
    ax_diff.axhline(0, color=TEXT2, lw=0.5)
    ax_diff.plot(fs, diff_db, color=S2, lw=1.5, zorder=3)
    # Add reference lines at ±0.5 dB
    ax_diff.axhline(0.5, color=CRIT, lw=0.7, ls=(0, (2, 2)))
    ax_diff.axhline(-0.5, color=CRIT, lw=0.7, ls=(0, (2, 2)))
    # Mark max deviation
    max_dev_idx = max(range(len(diff_db)), key=lambda i: abs(diff_db[i]))
    ax_diff.plot(fs[max_dev_idx], diff_db[max_dev_idx], 'o', color=S2, ms=4)
    ax_diff.annotate(f"max {abs(diff_db[max_dev_idx]):.3f} dB",
                     (fs[max_dev_idx], diff_db[max_dev_idx]),
                     textcoords="offset points", xytext=(5, 5),
                     fontsize=7, color=S2)
    ax_diff.tick_params(labelsize=8)
    # Remove xtick labels from main (shared axis)
    ax_main.tick_params(labelbottom=False)

    # Add inset zoom showing passband/corner where GBW deviation is visible
    if add_inset and fs and gs:
        # Inset axes: focus on 100 Hz .. 10 kHz, -3 dB .. 0.5 dB
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
        inset.plot(gs, gdbs, color=S2, lw=1.8, ls=(0, (3, 2)), zorder=3,
                   label="1 MHz-GBW macro-model")
        inset.plot(fs, dbs, color=S1, lw=1.8, zorder=2,
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


def result_png(sweep, verdict):
    fig = plt.figure(figsize=(10, 6.5), dpi=200)
    # Two rows: main plot (larger) + diff panel (smaller)
    gs = GridSpec(2, 1, height_ratios=[3, 1], hspace=0.05)
    ax_main = fig.add_subplot(gs[0])
    ax_diff = fig.add_subplot(gs[1])

    mc = verdict["gates"]["mask"]
    # Shortened title
    ax_main.set_title("4th-order Sallen-Key low-pass — ngspice AC response",
                      fontsize=11.5, pad=10)
    stamp = (f"PASS  ·  ripple {mc['ripple_db']} dB ≤ 1.0\n"
             f"stopband {mc['stopband_max_db']} dB ≤ −40")
    draw_result(ax_main, ax_diff, sweep, stamp=stamp)

    # --- Overlap check (LEAD VISUAL REVIEW v4) ---
    fig.canvas.draw()
    # Find the ripple mask label by text content
    ripple_label = None
    for artist in ax_main.get_children():
        if hasattr(artist, "get_text") and "mask: ripple" in artist.get_text():
            ripple_label = artist
            break
    assert ripple_label is not None, "ripple mask label not found"

    # Get window extents in display coordinates
    label_extent = ripple_label.get_window_extent(fig.canvas.get_renderer())
    pass_box = None
    for artist in ax_main.get_children():
        if hasattr(artist, "get_text") and "PASS" in artist.get_text():
            pass_box = artist.get_window_extent(fig.canvas.get_renderer())
            break
    # Inset axes extent
    inset_extent = None
    for child in ax_main.get_children():
        if isinstance(child, plt.Axes) and child != ax_main and child.get_label() == "inset_axes":
            inset_extent = child.get_window_extent(fig.canvas.get_renderer())
            break
    # Legend extent
    legend_extent = None
    leg = ax_main.get_legend()
    if leg:
        legend_extent = leg.get_window_extent(fig.canvas.get_renderer())

    def intersects(ext1, ext2):
        if ext1 is None or ext2 is None:
            return False
        return not (ext1.x1 < ext2.x0 or ext1.x0 > ext2.x1 or
                    ext1.y1 < ext2.y0 or ext1.y0 > ext2.y1)

    assert not intersects(label_extent, pass_box), "ripple label overlaps PASS box"
    assert not intersects(label_extent, inset_extent), "ripple label overlaps inset"
    assert not intersects(label_extent, legend_extent), "ripple label overlaps legend"

    fig.savefig(MEDIA / "result.png", bbox_inches="tight")
    plt.close(fig)
    print("make_figures: result.png")


def loop_png(replay, selftest, good_verdict):
    fig = plt.figure(figsize=(10, 7.4), dpi=200)
    gs = fig.add_gridspec(2, 1, height_ratios=[1, 1.15], hspace=0.42)

    # --- top: the agent-loop replay --------------------------------------
    ax = fig.add_subplot(gs[0])
    ax.set_title("Agent-loop replay: the gate that failed per iteration "
                 "(scripted replay, not a live trace)", fontsize=11)
    ys, labels, colors = [], [], []
    for i, v in enumerate(replay):
        ok = v["passed"]
        ys.append(1 if ok else 0)
        gate = v.get("failed_gate", "all gates")
        labels.append(f"it {i+1}: {REPLAY_LABELS[v['label']]}\n"
                      f"{'PASS — all gates' if ok else 'fail: ' + gate}")
        colors.append(GOOD if ok else CRIT)
    ax.plot(range(1, len(ys) + 1), ys, color=GRID, lw=1.5, zorder=1)
    ax.scatter(range(1, len(ys) + 1), ys, s=90, c=colors, zorder=3)
    for x, y, lab, c in zip(range(1, len(ys) + 1), ys, labels, colors):
        ax.annotate(lab, (x, y), textcoords="offset points",
                    xytext=(0, 14),
                    ha="center", fontsize=8.6,
                    color=TEXT if y == 0 else TEXT2, zorder=4,
                    bbox=dict(fc=SURFACE, ec="none", pad=1))
    ax.set_xticks(range(1, len(ys) + 1))
    ax.set_xticklabels([f"iteration {i+1}" for i in range(len(ys))],
                       fontsize=9)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["fail", "pass"], fontsize=9)
    ax.set_ylim(-0.75, 1.75)
    ax.set_xlim(0.45, len(ys) + 0.55)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    # --- bottom: self-test kill strip -------------------------------------
    ax = fig.add_subplot(gs[1])
    rate = selftest["kill_rate"]
    ax.set_title(f"Self-test kill rate: {selftest['mutants']}/"
                 f"{selftest['mutants']} = {rate:.0%}  "
                 "(requirement ≥ 90%)", fontsize=11)
    kills = selftest["kills"]
    xs = list(range(len(kills) + 1))
    ax.bar([0], [1], width=0.72, color=GOOD, edgecolor=SURFACE, lw=2)
    ax.text(0, 1.06, "known-good\npasses", ha="center", fontsize=8,
            color=TEXT2)
    for i, k in enumerate(kills, 1):
        ax.bar([i], [1], width=0.72, color=CRIT, edgecolor=SURFACE, lw=2)
        ax.text(i, 0.5, "killed", ha="center", fontsize=7.4,
                color=SURFACE, rotation=90)
        ax.text(i, -0.13, k["mutant"].replace("-", "\n", 1),
                ha="center", fontsize=6.8, color=TEXT2)
        ax.text(i, -0.40, k["failed_gate"], ha="center", fontsize=7,
                color=CRIT, fontweight="bold")
    ax.set_xlim(-0.6, len(kills) + 0.6)
    ax.set_ylim(-0.55, 1.3)
    ax.set_yticks([])
    ax.set_xticks([])
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)

    fig.tight_layout()
    fig.savefig(MEDIA / "loop.png")
    plt.close(fig)
    print("make_figures: loop.png")


def main():
    sweep = load("sweep_good.json")
    replay = load("replay.json")
    selftest = load("selftest.json")
    good = [v for v in replay if v["passed"]][0]
    result_png(sweep, good)
    loop_png(replay, selftest, good)


if __name__ == "__main__":
    main()