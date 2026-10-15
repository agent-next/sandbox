#!/usr/bin/env python3
"""Draw media/result.png and media/loop.png from media/data/*.json.

    make_figures.py

result.png: the judge's two measured gates with their pass lines drawn on --
the burned frame counter decoded back out of both renditions against the
analytic frame index, and the caption word error rate against its limit.
loop.png: the scripted agent loop (verdict per iteration until pass) and the
self-test kill-rate bars (known-good vs each single-edit mutant).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

# Colour-blind-safe palette (Okabe-Ito).
BLUE, ORANGE, GREEN, PINK, GREY = "#0072B2", "#E69F00", "#009E73", "#CC79A7", "#999999"
plt.rcParams.update({"font.size": 11, "figure.dpi": 200,
                     "axes.grid": True, "grid.alpha": 0.3,
                     "axes.axisbelow": True})


def load(name: str) -> dict:
    return json.loads((DATA / name).read_text())


def fig_result() -> None:
    good = load("good.json")
    counter = load("counter.json")
    gates = good["gates"]

    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(12, 5))

    # --- left: counter decoded from the renditions -------------------------
    ax0.plot([0, 480], [0, 480], color=GREY, lw=1.4, ls="--",
             label="expected = frame index (analytic)")
    tol = counter["tolerance"]
    ax0.fill_between([0, 480], [-tol, 480 - tol], [tol, 480 + tol],
                     color=GREY, alpha=0.25, lw=0, label=f"±{tol}-frame tolerance")
    for name, style in (("360p", dict(color=BLUE, marker="o")),
                        ("720p", dict(color=ORANGE, marker="s"))):
        r = counter["renditions"][name]
        ax0.plot(r["index"], r["decoded"], ls="none", ms=4.5, alpha=0.85,
                 label=f"{name} decoded ({r['matched']}/{r['samples']} match)",
                 **style)
    ax0.set_xlabel("frame index in the rendition")
    ax0.set_ylabel("frame counter decoded from the pixels")
    ax0.set_title("G5 · burned frame counter read back out of the renditions\n"
                  "(a dropped segment shifts every later reading)", fontsize=11)
    ax0.set_xlim(0, 480)
    ax0.set_ylim(-10, 490)
    ax0.legend(fontsize=8, loc="upper left")

    # --- right: caption WER against its limit ------------------------------
    wer = gates["captions"]["wer"]
    limit = 0.20
    bars = [("examples/good", wer, GREEN), ("limit (fail above)", limit, PINK)]
    ax1.barh([0, 1], [b[1] for b in bars], height=0.42,
             color=[b[2] for b in bars])
    for y, (label, value, _) in zip([0, 1], bars):
        ax1.text(value + 0.006, y, f"{value:.4f}", va="center", fontsize=11)
    ax1.axvline(limit, color=PINK, lw=2, ls="--")
    ax1.set_yticks([0, 1], [b[0] for b in bars])
    ax1.set_xlabel("caption word error rate vs the known transcript")
    ax1.set_xlim(0, 0.26)
    ax1.set_title(f"G8 · caption accuracy\n"
                  f"{gates['captions']['cues']} cues, "
                  f"{gates['captions']['coverage']:.0%} timeline coverage, "
                  f"{gates['captions']['errors']}/{gates['captions']['ref_words']} "
                  f"word errors", fontsize=11)
    ax1.grid(axis="y", visible=False)

    fig.suptitle("video-transcode-pipeline · judge gates on examples/good "
                 "(seed 0, Debian sandbox, 2 vCPU)", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(HERE / "result.png")
    plt.close(fig)
    print("figures: wrote result.png")


def fig_loop() -> None:
    replay = load("replay.json")["replay"]
    mut = load("mutants.json")

    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(12, 5),
                                   gridspec_kw={"width_ratios": [1.25, 1]})

    # --- left: the loop ----------------------------------------------------
    labels = [r["artifact"].replace("examples/good (fixed)", "good (fixed)")
              for r in replay]
    gate_names = list(replay[0]["gates"])
    for i, r in enumerate(replay):
        for j, g in enumerate(gate_names):
            ok = r["gates"].get(g, False)
            ax0.scatter([i], [j], s=520,
                        color=(GREEN if ok else PINK),
                        marker="o" if ok else "X", zorder=3)
    ax0.set_xticks(range(len(replay)), labels, rotation=25, ha="right", fontsize=9)
    ax0.set_yticks(range(len(gate_names)), gate_names)
    ax0.set_xlim(-0.6, len(replay) - 0.4)
    ax0.set_ylim(-0.6, len(gate_names) - 0.4)
    ax0.invert_yaxis()
    for i, r in enumerate(replay):
        ax0.text(i, -0.45, "PASS" if r["passed"] else r["failed_gate"],
                 ha="center", va="center", fontsize=8,
                 color=(GREEN if r["passed"] else PINK), fontweight="bold")
    ax0.set_title("agent loop · gate outcome per iteration\n"
                  "(scripted replay of real judge verdicts, in fixing order)",
                  fontsize=11)
    ax0.legend(handles=[Patch(color=GREEN, label="gate passed"),
                        Patch(color=PINK, label="gate failed")],
               fontsize=8, loc="lower right")
    ax0.grid(alpha=0.25)

    # --- right: kill rate --------------------------------------------------
    names = ["known-good"] + [m["name"] for m in mut["mutants"]]
    vals = [1.0] + [0.0 if m["passed"] else 1.0 for m in mut["mutants"]]
    colors = [GREEN] + [BLUE] * len(mut["mutants"])
    ax1.barh(range(len(names)), vals, color=colors, height=0.6)
    ax1.set_yticks(range(len(names)), names, fontsize=9)
    ax1.invert_yaxis()
    ax1.set_xlim(0, 1.05)
    ax1.set_xlabel("judge verdict (1 = killed / failed, 0 = passed)")
    for i, (v, m) in enumerate(zip(vals, [None] + mut["mutants"])):
        tag = "passed all gates" if i == 0 else f"killed by {m['failed_gate']}"
        ax1.text(v + 0.02, i, tag, va="center", fontsize=8)
    ax1.set_title(f"self-test kill rate {mut['killed']}/{mut['total']} = "
                  f"{mut['kill_rate']:.0%}\n(requirement ≥ 90 %)", fontsize=11)
    ax1.grid(axis="y", visible=False)

    fig.suptitle("video-transcode-pipeline · does the judge fail bad pipelines?",
                 fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(HERE / "loop.png")
    plt.close(fig)
    print("figures: wrote loop.png")


def main() -> int:
    for need in ("good.json", "mutants.json", "replay.json", "counter.json"):
        if not (DATA / need).is_file():
            print(f"figures: {DATA / need} missing; run make_data.py first",
                  file=sys.stderr)
            return 1
    fig_result()
    fig_loop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
