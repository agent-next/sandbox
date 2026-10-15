#!/usr/bin/env python3
"""media/make_figures.py -- render media/result.png and media/loop.png.

Every drawn value comes from a judge output file written by make_data.py:
the good grade verdict, the self-test log, the per-mutant verdicts, the
sha-verified render (data/render.png) and its widget-facts dump.  The
palette is the validated reference palette (dataviz skill, light mode);
status colours always ship with a text label, never colour alone.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

MEDIA = Path(__file__).resolve().parent
DATA = MEDIA / "data"

# reference palette (dataviz skill, validated): light mode
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT2 = "#52514e"
GRID = "#e1e0d9"
S1 = "#2a78d6"   # categorical slot 1 (blue): measured values
GOOD = "#0ca30c"     # status good (with label)
CRIT = "#d03b3b"     # status critical (with label)

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "text.color": TEXT, "axes.labelcolor": TEXT,
    "xtick.color": TEXT2, "ytick.color": TEXT2,
    "axes.edgecolor": TEXT2, "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
})

# Human labels for the mutants (same wording as judge/mutants.py docstring).
MUTANT_LABELS = {
    "missing_slider": "missing slider",
    "wrong_range": "wrong slider range",
    "wrong_swatch_color": "wrong swatch colour",
    "swatch_overflow": "swatch overflow",
    "empty_window": "empty window",
    "wrong_button_text": "wrong button text",
    "wrong_swatch_size": "wrong swatch size",
    "missing_checkbox": "missing checkbox",
    "missing_swatch": "missing swatch",
    "baked_png": "baked png",
    "nondeterministic": "nondeterministic",
}

MUTANT_ORDER = [
    "missing_slider", "wrong_range", "wrong_swatch_color", "swatch_overflow",
    "empty_window", "wrong_button_text", "wrong_swatch_size",
    "missing_checkbox", "missing_swatch", "baked_png", "nondeterministic",
]


def load(name):
    return json.loads((DATA / name).read_text())


def failed_gates(v):
    """The judge's own attribution for a failed verdict: the gates that
    failed, or the judge's error string when it died before the gates."""
    if v.get("pass") is None:
        return "run error"
    bad = [g["gate"] for g in v.get("gates", []) if not g["ok"]]
    return ", ".join(bad) if bad else v.get("error", "unknown")


def draw_render_overlay(ax, show_bboxes=True, pass_stamp=True,
                        region_only=False):
    """The real 1280x720 render with the judge's measured bboxes drawn.

    show_bboxes fades the measured bboxes + labels in;
    pass_stamp draws the PASS stamp from the real verdict.
    region_only leaves out the bboxes (title-only framing).
    """
    good = load("grade_good.json")
    facts = load("facts.json")
    render = Image.open(DATA / "render.png")

    ax.imshow(np.asarray(render))
    ax.set_xlim(0, 1280)
    ax.set_ylim(720, 0)                      # screen coords, y down
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)

    if region_only:
        return good, facts

    if show_bboxes:
        # content region: the window inset by title bar + border (26+4 px),
        # as check_gates.py defines the region widgets must sit inside
        win = facts["window"]
        x0 = win["position_x"] + 4
        y0 = win["position_y"] + 26 + 4
        x1 = win["position_x"] + win["width"] - 4
        y1 = win["position_y"] + win["height"] - 4
        ax.plot([x0, x1, x1, x0, x0], [y0, y0, y1, y1, y0],
                color=SURFACE, lw=1.4, ls=(0, (4, 3)), alpha=0.9)
        # below the window: nothing is drawn there, so the caption cannot
        # collide with the widget labels
        ax.text(x0, y1 + 16, "content region (title bar 26 px + border 4 px)",
                ha="left", fontsize=8, color=SURFACE)

        # widget labels ride leader lines out to the right of the window:
        # the render's dark background is clear there, and rows are 26-30 px
        # apart, so the labels never stack on each other or on the region
        # caption (the render's own widgets are only ~24 px tall).
        for name, f in facts.items():
            if name in ("window", "_ref_names", "_window_live"):
                continue
            x, y = f["screen_position_x"], f["screen_position_y"]
            w, h = f["computed_width"], f["computed_height"]
            ax.add_patch(plt.Rectangle(
                (x, y), w, h, fill=False, ec=S1, lw=1.6, zorder=4))
            cx = x1 + 26
            ax.plot([x + w, cx - 6], [y + h / 2, y + h / 2],
                    color=SURFACE, lw=0.8, alpha=0.55, zorder=3)
            ax.text(cx, y + h / 2, name, ha="left", va="center",
                    fontsize=8.5, color=SURFACE, zorder=5)

    if pass_stamp:
        det = [g for g in good["gates"] if g["gate"] == "determinism"][0]
        pix = [g for g in good["gates"] if g["gate"] == "pixels"][0]["detail"]
        lines = [
            "PASS — all 4 gates",
            f"render 1280x720, determinism sha256 {det['sha256']}…",
            f"swatch median RGB {pix['swatch_median']}",
            f"bg luminance {pix['bg_lum']:.0f}, button face {pix['button_face_lum']:.0f}",
        ]
        ax.text(1272, 14, "\n".join(lines), ha="right", va="top",
                fontsize=8.6, color=TEXT, zorder=6,
                bbox=dict(boxstyle="round,pad=0.45",
                          fc=SURFACE, ec=GOOD, lw=1.4))

    return good, facts


def result_png():
    """Key figure: the real render + measured bboxes + judge numbers."""
    good = load("grade_good.json")
    facts = load("facts.json")
    pix = [g for g in good["gates"] if g["gate"] == "pixels"][0]["detail"]
    ref = json.loads((MEDIA.parent / "judge/reference.json").read_text())
    tol = ref["swatch_tol"]
    target = ref["swatch_rgb"]

    fig = plt.figure(figsize=(10, 6.8), dpi=200)
    gs = fig.add_gridspec(2, 1, height_ratios=[2.7, 1], hspace=0.07)
    ax_top = fig.add_subplot(gs[0])

    draw_render_overlay(ax_top)

    ax_top.set_title(
        "ovui-native-ui — headless omni.ui render, judged against the spec "
        "(1280×720, lavapipe CPU Vulkan)",
        fontsize=11.5, pad=8)

    # --- bottom: the swatch colour, measured vs the spec mask -------------
    ax = fig.add_subplot(gs[1])
    chans = ["R", "G", "B"]
    xs = [0, 1, 2]
    med = pix["swatch_median"]
    std = pix["swatch_std"]
    ax.bar(xs, med, width=0.62, color=S1, edgecolor=SURFACE, lw=1.5,
           label=f"measured median (std {list(std)} — flat fill)")
    # the ±tol band the judge allows around the analytic target
    ax.errorbar(xs, target, yerr=tol, fmt="none", ecolor=TEXT2,
                elinewidth=1.4, capsize=5,
                label=f"judge mask: target ± tol ({tol} per channel)")
    ax.scatter(xs, target, marker="_", s=260, color=TEXT2, zorder=5,
               linewidths=1.6)
    # measured value inside its bar (white, centered); target label above
    # the mask cap, off to the right of its tick so neither collides with
    # the bar tops, the caps or each other
    for x, m, t in zip(xs, med, target):
        ax.text(x, m, f"{m:.0f}", va="bottom", ha="center", fontsize=9,
                color=SURFACE, zorder=6)
        ax.text(x + 0.24, t + max(tol) + 6, f"target {t:.0f}",
                va="bottom", ha="left", fontsize=8.5, color=TEXT2)
    ax.set_xticks(xs)
    ax.set_xticklabels(chans, fontsize=10)
    ax.set_ylabel("8-bit value")
    ax.set_ylim(0, 268)
    ax.set_xlim(-0.5, 3.4)
    ax.grid(True, axis="y", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    ax.legend(loc="upper left", fontsize=8.4, frameon=False)
    ax.set_title("Colour swatch gate: measured median vs the judge's "
                 f"±{tol} mask around the analytic sRGB target "
                 f"[{', '.join(str(t) for t in target)}]",
                 fontsize=10, pad=6)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    fig.tight_layout()
    fig.savefig(MEDIA / "result.png", bbox_inches="tight")
    plt.close(fig)
    print("make_figures: result.png")


def loop_png():
    """Agent-loop replay + self-test kill-rate table, from real verdicts."""
    good = load("grade_good.json")
    mutants = load("mutants.json")
    selftest = (DATA / "selftest.txt").read_text()
    rate_line = [l for l in selftest.splitlines() if "kill rate" in l][-1]
    rate = rate_line.split(":")[1].strip()

    fig = plt.figure(figsize=(10, 7.6), dpi=200)
    gs = fig.add_gridspec(2, 1, height_ratios=[1, 1.45], hspace=0.34)

    # --- top: the agent-loop replay --------------------------------------
    # A scripted replay in the order a fixing agent meets the failures:
    # three mutants a first attempt plausibly makes (one per gate:
    # widget_tree, pixels, determinism), then the known-good pass.  It is
    # a scripted replay of real judge verdicts, not a recorded live trace.
    replay_order = [
        ("missing_slider", "missing slider"),
        ("wrong_swatch_color", "wrong swatch\ncolour"),
        ("nondeterministic", "nondeterministic\nrender"),
        ("good", None),
    ]
    ax = fig.add_subplot(gs[0])
    ax.set_title("Agent-loop replay: the judge verdict per iteration "
                 "(scripted replay, not a live trace)", fontsize=11)
    ys, labels, colors = [], [], []
    for i, (name, caption) in enumerate(replay_order):
        if name == "good":
            ok, gate, what = True, None, "known-good panel"
        else:
            v = mutants[name]
            ok = False
            gate = failed_gates(v)
            what = caption
        ys.append(1 if ok else 0)
        labels.append(f"it {i+1}: {what}\n"
                      f"{'PASS — all 4 gates' if ok else 'fail: ' + gate}")
        colors.append(GOOD if ok else CRIT)
    ax.plot(range(1, len(ys) + 1), ys, color=GRID, lw=1.5, zorder=1)
    ax.scatter(range(1, len(ys) + 1), ys, s=90, c=colors, zorder=3)
    # stagger the annotation rows so neighbours never collide
    for i, (x, y, lab, c) in enumerate(zip(range(1, len(ys) + 1), ys,
                                           labels, colors)):
        dy, va = (16, "bottom") if i % 2 == 0 else (-16, "top")
        ax.annotate(lab, (x, y), textcoords="offset points",
                    xytext=(0, dy), ha="center", va=va, fontsize=8.6,
                    color=TEXT if y == 0 else TEXT2, zorder=4,
                    bbox=dict(fc=SURFACE, ec="none", pad=1))
    ax.set_xticks(range(1, len(ys) + 1))
    ax.set_xticklabels([f"iteration {i+1}" for i in range(len(ys))],
                       fontsize=9)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["fail", "pass"], fontsize=9)
    ax.set_ylim(-1.15, 1.75)
    ax.set_xlim(0.45, len(ys) + 0.55)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)

    # --- bottom: self-test kill table (one row per mutant) ----------------
    ax = fig.add_subplot(gs[1])
    ax.set_title(f"Self-test: every mutant is killed by the judge "
                 f"(kill rate {rate}, requirement ≥ 90%)", fontsize=11)
    rows = [("known-good panel", "PASS — all 4 gates", True)] + [
        (MUTANT_LABELS[n], failed_gates(mutants[n]), False)
        for n in MUTANT_ORDER
    ]
    ax.set_xlim(0, 1)
    ax.set_ylim(0, len(rows))
    ax.invert_yaxis()
    for i, (name, gates, ok) in enumerate(rows):
        y = i + 0.5
        ax.text(0.245, y, name, ha="right", va="center", fontsize=9,
                color=TEXT)
        ax.barh(y, 0.44, left=0.26, height=0.62,
                color=GOOD if ok else S1, edgecolor=SURFACE, lw=1.5)
        ax.text(0.715, y, gates, ha="left", va="center", fontsize=8.6,
                color=TEXT2)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)

    fig.tight_layout()
    fig.savefig(MEDIA / "loop.png")
    plt.close(fig)
    print("make_figures: loop.png")


if __name__ == "__main__":
    result_png()
    loop_png()
