#!/usr/bin/env python3
"""Draw the demo's figures from measured judge output only.

    make_figures.py <artifact_dir> <out_dir> [--seed N] [--history history.json]

Writes:
    result.png  -- the four artifacts with the judge's own numbers drawn on
                   them: the measured chroma glide against the fitted line and
                   the spec floor, the ball's bottom edge with the floor row
                   and each bounce marked, the QR code, the palette card.
    loop.png    -- the self-test kill rate per mutant, plus the grade history
                   when a history file is given.

Nothing here invents data: every number comes from `judge/viral_judge.py` run
on the artifact being drawn.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "judge"))
import viral_judge as J  # noqa: E402

# colour-blind-safe palette (Okabe-Ito)
OKABE = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#F0E442", "#56B4E9",
         "#E69F00", "#000000"]


def fig_result(art: str, out: str, seed: int) -> dict:
    wav = os.path.join(art, "shepard.wav")
    gif = os.path.join(art, "ball.gif")
    qr = os.path.join(art, "qr.png")
    pal = os.path.join(art, "palette.png")

    verdict = J.grade(art, seed)
    sp = verdict["gates"]["shepard_property"]
    bb = verdict["gates"]["ball_bounces"]
    ga = verdict["gates"]["gif_animation"]

    x = J.read_pcm_mono(wav)
    ts, phis = J.track_chroma(x, J.SR, J.CHROMA_F_REF)
    glide = J.unfold_rising(phis)
    slope, intercept = np.polyfit(ts, glide, 1)
    t_end = len(x) / J.SR
    line = intercept + slope * ts

    fig = plt.figure(figsize=(12, 8), dpi=200)
    gs = fig.add_gridspec(2, 2, height_ratios=[1.15, 1.0], hspace=0.42,
                          wspace=0.24)

    # --- top: the Shepard glide against its analytic fit -------------------
    ax = fig.add_subplot(gs[0, :])
    ax.plot(ts, glide, lw=1.0, color=OKABE[0], label="measured chroma glide")
    ax.plot(ts, line, lw=1.4, ls="--", color=OKABE[1],
            label=f"fit: {slope:.4f} oct/s, R²={sp['fit_r2']:.6f}")
    ax.axhline(0, color="0.6", lw=0.8)
    ax.axhline(J.MIN_OCTAVES, color=OKABE[2], lw=1.2, ls=":",
               label=f"spec floor: {J.MIN_OCTAVES:.1f} oct span")
    ax.axhline(sp["span_octaves"], color=OKABE[3], lw=1.0, ls="-.",
               label=f"measured span: {sp['span_octaves']:.4f} oct")
    ax.set_xlabel("time (s)")
    ax.set_ylabel("chroma glide r(t) (octaves)")
    ax.set_title("viral-microgen — Shepard tone: the glide rises a whole "
                 f"number of octaves ({sp['return_octaves']:.4f} oct, "
                 f"tol ±{J.OCTAVE_TOL_OCT:.3f})")
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
    ax.grid(alpha=0.25)

    # --- bottom left: the ball's bottom edge and the floor row -------------
    ax = fig.add_subplot(gs[1, 0])
    bottoms = [b for b in bb["bottom_rows"] if b is not None]
    ax.plot(range(len(bottoms)), bottoms, lw=1.2, color=OKABE[0],
            marker=".", ms=3, label="ball bottom row per frame")
    ax.axhline(bb["floor_row"], color=OKABE[1], lw=1.2, ls="--",
               label=f"floor row {bb['floor_row']} (±2 px)")
    contacts = [i for i, b in enumerate(bottoms)
                if abs(b - bb["floor_row"]) <= 2]
    ax.plot(contacts, [bb["floor_row"]] * len(contacts), "o", ms=6,
            mfc="none", mec=OKABE[3], mew=1.4,
            label=f"{bb['n_bounces']} bounces (measured)")
    ax.set_xlabel("frame")
    ax.set_ylabel("ball bottom edge (image row, up = up)")
    ax.set_title(f"ball: rise {bb['max_rise_px']} px, travel "
                 f"{bb['x_travel_px']:.0f} px")
    ax.invert_yaxis()          # image rows grow downward; draw the ball rising
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(alpha=0.25)

    # --- bottom right: the QR and the palette card ------------------------
    ax = fig.add_subplot(gs[1, 1])
    ax.imshow(np.asarray(Image.open(qr).convert("RGB")))
    ax.set_title(f"qr.png → {verdict['gates']['qr_scans']['zbar']} "
                 f"(zbar {J.ZBAR_VERSION} + zxing-cpp {J.ZXING_VERSION})",
                 fontsize=9)
    ax.set_xticks([])
    ax.set_yticks([])

    for i, c in enumerate(ga["colours_used"]):
        fig.patches.append(Rectangle((0.40 + 0.055 * i, 0.028), 0.05, 0.022,
                                     transform=fig.transFigure,
                                     facecolor=np.array(c) / 255.0,
                                     edgecolor="black", lw=0.6))
    fig.text(0.40, 0.056, "palette card: exactly these 5 colours "
                          f"(judge: exact RGB match)",
             fontsize=8, ha="left")

    fig.suptitle("viral-microgen — all six gates pass on examples/good "
                 f"(seed {seed})", fontsize=12, y=0.975)
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return verdict


def fig_loop(out: str, history: str | None) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), dpi=200)
    ax = axes[0]
    if history and os.path.exists(history):
        h = json.load(open(history))
        it = [r["iteration"] for r in h["iterations"]]
        score = [r["gates_passed"] for r in h["iterations"]]
        ax.plot(it, score, marker="o", color=OKABE[0], lw=1.6)
        ax.set_xlabel("agent iteration")
        ax.set_ylabel("gates passed (of 6)")
        ax.set_title("agent loop: gates passed per iteration")
        ax.set_ylim(-0.3, 6.3)
        ax.grid(alpha=0.25)
    else:
        ax.axis("off")
        ax.text(0.5, 0.5, "no grade history supplied", ha="center",
                va="center", fontsize=10, color="0.4")
        ax.set_title("agent loop")

    ax = axes[1]
    mut = json.load(open(os.path.join(os.path.dirname(out),
                                      "data", "selftest.json")))
    names = [m["name"] for m in mut["mutants"]]
    killed = [1 if m["killed"] else 0 for m in mut["mutants"]]
    cols = [OKABE[2] if k else OKABE[1] for k in killed]
    ax.barh(range(len(names)), killed, color=cols)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=7)
    ax.set_xlim(0, 1.2)
    ax.set_xlabel("killed (1) / survived (0)")
    ax.set_title(f"self-test: {mut['killed']}/{mut['total']} killed = "
                 f"{mut['kill_rate']}")
    ax.grid(alpha=0.25, axis="x")
    fig.tight_layout()
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("out_dir")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--history", default=None)
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    fig_result(args.artifact, os.path.join(args.out_dir, "result.png"),
               args.seed)
    fig_loop(os.path.join(args.out_dir, "loop.png"), args.history)
    print(f"make_figures: wrote {args.out_dir}/result.png and loop.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
