#!/usr/bin/env python3
"""Render the terminal-task-bench figures and video frames.

Everything plotted is measured: the two grade.sh verdicts and the
selftest.sh log written by make_media.sh.  No invented data.

Colour-blind-safe palette (Okabe-Ito).  Figures: 200 dpi, readable at
1200 px wide.  Video frames: 1920x1080 (a step-through of the agent
loop's figures with captions -- the bench has no time-dependent physics).
"""

from __future__ import annotations

import json
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

# Okabe-Ito colour-blind-safe palette
GREEN = "#009E73"    # solved / passed
VERM = "#D55E00"     # killed / failed
BLUE = "#0072B2"
ORANGE = "#E69F00"
SKY = "#56B4E9"
GREY = "#BBBBBB"
INK = "#1A1A1A"

GATES = ["G1_solve_count", "G2_pristine_fails", "G3_negative_control",
         "G4_budget", "G5_judge_untouched"]
GATE_LABELS = ["G1\nsolve ≥ 8/10", "G2\npristine\nrejected",
               "G3\nnegctl\n0/10", "G4\nverify\n≤ 300 s", "G5\noracle\nuntouched"]

plt.rcParams.update({
    "font.size": 10,
    "axes.edgecolor": INK,
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": INK,
    "ytick.color": INK,
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
})


def load(name):
    with open(os.path.join(DATA, name)) as fh:
        return json.load(fh)


def arms():
    """(label, verdict, colour) for the three agent arms, from the data."""
    good = load("grade_good.json")
    cheat = load("grade_cheat.json")
    return [
        ("known-good\n(examples/good)", good, GREEN),
        ("negative control\n(runs `true` only)", good, BLUE),
        ("adversarial\n(rewrites verifiers)", cheat, VERM),
    ], good, cheat


def solved_count(label, verdict):
    if label.startswith("negative"):
        return verdict["gates"]["G3_negative_control"]["negctl_solved"]
    return verdict["gates"]["G1_solve_count"]["solved"]


def verify_seconds(label, verdict):
    return verdict["timing"]["total_verify_seconds"]


def passed_verdict(label, verdict):
    return verdict["passed"] if not label.startswith("negative") else \
        verdict["gates"]["G3_negative_control"]["passed"]


# ---------------------------------------------------------------- result --
def draw_result(ax1, ax2):
    triple, good, cheat = arms()
    labels = ["known-good", "negative\ncontrol", "adversarial\n(verifier rewrite)"]

    solved = [solved_count(l, v) for l, v, _ in triple]
    colours = [GREEN if passed_verdict(l, v) else VERM
               for l, v, _ in triple]
    bars = ax1.bar(range(3), solved, color=colours, width=0.6,
                   edgecolor=INK, linewidth=0.8)
    ax1.axhline(8, color=VERM, linestyle="--", linewidth=1.6)
    ax1.text(2.45, 8.3, "G1 pass line = 8/10", ha="right",
             color=VERM, fontsize=9, fontweight="bold")
    for b, s in zip(bars, solved):
        ax1.text(b.get_x() + b.get_width() / 2, s + 0.25, f"{s}/10",
                 ha="center", fontsize=11, fontweight="bold")
    ax1.set_ylim(0, 11.5)
    ax1.set_xlim(-0.6, 2.6)
    ax1.set_xticks(range(3))
    ax1.set_xticklabels(labels, fontsize=8)
    ax1.set_ylabel("tasks solved (verify.sh exit 0)")
    ax1.set_title("Tasks solved per agent arm", fontsize=11,
                  fontweight="bold")

    secs = [verify_seconds(l, v) for l, v, _ in triple]
    used = [s / 300.0 * 100 for s in secs]
    ax2.barh(range(3), used, color=[t[2] for t in triple], height=0.6,
             edgecolor=INK, linewidth=0.8)
    ax2.axvline(100, color=VERM, linestyle="--", linewidth=1.6)
    ax2.text(100, 2.55, "G4 budget = 300 s", ha="right", va="bottom",
             color=VERM, fontsize=9, fontweight="bold")
    for i, s in enumerate(secs):
        ax2.text(max(used[i] + 1.5, 2), i, f"{s:.1f} s", va="center",
                 fontsize=11, fontweight="bold")
    ax2.set_xlim(0, 130)
    ax2.set_ylim(-0.6, 2.9)
    ax2.set_yticks(range(3))
    ax2.set_yticklabels(labels, fontsize=8)
    ax2.set_xlabel("verifier wall time, % of the 300 s budget", fontsize=9)
    ax2.set_title("Verifier budget (G4)", fontsize=11, fontweight="bold")

    note = (f"verdict: known-good {'PASS' if good['passed'] else 'FAIL'}"
            f" · adversarial {'PASS' if cheat['passed'] else 'FAIL'}"
            f" · seed {good['seed']}")
    ax2.text(0.5, -0.28, note, transform=ax2.transAxes, ha="center",
             fontsize=8, color="#555555")


# ------------------------------------------------------------------ loop --
def mutants_from_log():
    """(name, task, killed) per mutant, from the selftest log."""
    with open(os.path.join(DATA, "selftest.log")) as fh:
        text = fh.read()
    out = []
    for m in re.finditer(
            r"^mutants: (\S+)\s+\((\S+)\)", text, re.M):
        out.append({"name": m.group(1), "task": m.group(2), "killed": None})
    for m in re.finditer(
            r"^selftest:\s+(killed|SURVIVED)\s+(\S+) \(task (\S+?):", text, re.M):
        for row in out:
            if row["name"] == m.group(2):
                row["killed"] = m.group(1) == "killed"
    return [r for r in out if r["killed"] is not None]


def draw_loop(ax1, ax2):
    good = load("grade_good.json")
    rows = mutants_from_log()

    names = ["known-good"] + [r["name"] for r in rows]
    killed_flag = [False] + [r["killed"] for r in rows]  # False = not killed
    colours = [GREEN if not s else VERM for s in killed_flag]
    y = list(range(len(names)))[::-1]
    ax1.barh(y, [1] * len(names), color=colours, height=0.68,
             edgecolor=INK, linewidth=0.6)
    ax1.set_yticks(y)
    ax1.set_yticklabels(names, fontsize=6.5)
    ax1.set_xlim(0, 1)
    killed = sum(1 for r in rows if r["killed"])
    ax1.set_xticks([])
    ax1.set_title(f"Self-test: {killed}/{len(rows)} mutants killed"
                  f" = {killed / len(rows):.0%}",
                  fontsize=10, fontweight="bold")
    ax1.text(0.5, y[0], "passes", color="white", fontsize=7,
             fontweight="bold", va="center", ha="center")
    ax1.text(0.5, y[1], "killed", color="white", fontsize=7,
             fontweight="bold", va="center", ha="center")

    good = load("grade_good.json")
    cheat = load("grade_cheat.json")
    matrix_arms = [("known-good", good), ("adversarial", cheat)]
    for i, gate in enumerate(GATES):
        for j, (_, verdict) in enumerate(matrix_arms):
            passed = verdict["gates"][gate]["passed"]
            ax2.add_patch(Rectangle((i, j), 1, 1,
                                    facecolor=GREEN if passed else VERM,
                                    edgecolor="white", linewidth=2))
    ax2.set_xlim(0, len(GATES))
    ax2.set_ylim(0, len(matrix_arms))
    ax2.set_xticks([i + 0.5 for i in range(len(GATES))])
    ax2.set_xticklabels(GATE_LABELS, fontsize=7)
    ax2.set_yticks([j + 0.5 for j in range(len(matrix_arms))])
    ax2.set_yticklabels([a[0] for a in matrix_arms], fontsize=8)
    ax2.tick_params(length=0)
    for spine in ax2.spines.values():
        spine.set_visible(False)
    ax2.set_title("Gate outcomes (green = pass)", fontsize=10,
                  fontweight="bold")


def save(fig, name):
    path = os.path.join(HERE, name)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    print(f"make_media: wrote {path}")


def main():
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.4, 4.2))
    draw_result(ax1, ax2)
    fig.tight_layout()
    save(fig, "result.png")
    plt.close(fig)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.4, 4.6),
                                   gridspec_kw={"width_ratios": [1, 1.1]})
    draw_loop(ax1, ax2)
    fig.tight_layout(w_pad=3.0)
    save(fig, "loop.png")
    plt.close(fig)

    import make_frames
    make_frames.render(os.path.join(HERE, "master"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
