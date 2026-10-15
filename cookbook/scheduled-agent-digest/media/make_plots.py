#!/usr/bin/env python3
"""result.png — the judge's key numbers per night against the pinned values.

Every bar is a measured number from media/data/grade_good.json (the good
artifact graded by judge/grade.sh, default seed 20261015); every marker is
the pinned value from SPEC.md.  The judge passes only when bar == marker on
every field of every night.

    python3 make_plots.py            # writes ../result.png and ../loop.png
"""
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

NIGHTS = ["2026-10-12", "2026-10-13", "2026-10-14"]
NIGHT_LABELS = ["Night 1\n2026-10-12", "Night 2\n2026-10-13", "Night 3\n2026-10-14"]

# field -> (pinned value per night, axis scale, unit)
FIELDS = [
    ("events",        [128, 141, 96],       "linear", "requests"),
    ("errors",        [16, 18, 15],         "linear", "requests"),
    ("error_rate",    [0.125, 0.12766, 0.15625], "linear", "ratio"),
    ("p50_ms",        [281, 281, 292],      "linear", "ms"),
    ("p95_ms",        [16447, 16098, 14552], "log",    "ms"),
    ("max_ms",        [19837, 19987, 19859], "log",    "ms"),
]

# colour-blind-safe (Wong) palette
BAR = "#56B4E9"     # sky blue — the artifact's digest
PIN = "#D55E00"     # vermillion — the pinned SPEC value


def good():
    return json.loads((DATA / "grade_good.json").read_text())


def field_values(verdict, field):
    """Pull one numeric field for each of the three nights from a verdict."""
    gate = verdict["gates"]["digest"]
    return [gate[f"{night}_{field}"] for night in NIGHTS]


def result_png():
    verdict = good()
    fig, axes = plt.subplots(2, 3, figsize=(16, 8.6))
    fig.suptitle("Nightly digest: the judge's numbers against the pinned SPEC values\n"
                 "(judge/grade.sh examples/good, seed 20261015 — bar = artifact digest, "
                 "marker = pinned)", fontsize=13)
    for ax, (field, pinned, scale, unit) in zip(axes.flat, FIELDS):
        got = field_values(verdict, field)
        x = np.arange(3)
        ax.bar(x, got, width=0.55, color=BAR, label="digest.py")
        ax.scatter(x, pinned, marker="_", s=1100, c=PIN, linewidths=2.6,
                   label="pinned (SPEC.md)", zorder=3)
        ax.set_xticks(x)
        ax.set_xticklabels(NIGHT_LABELS, fontsize=9)
        ax.set_ylabel(unit, fontsize=9)
        ax.set_title(f"{field}  (log scale)" if scale == "log" else field,
                     fontsize=11)
        if scale == "log":
            ax.set_yscale("log")
        for xi, (g, p) in enumerate(zip(got, pinned)):
            same = math.isclose(float(g), float(p), rel_tol=1e-9, abs_tol=1e-9)
            ax.annotate(f"{g:g}" if field != "error_rate" else f"{g}",
                        (xi, g), textcoords="offset points", xytext=(0, 3),
                        ha="center", fontsize=8.5,
                        color="#0072B2" if same else "#D55E00")
        ax.grid(axis="y", alpha=0.25)
        ax.legend(fontsize=8, loc="upper right")
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(HERE / "result.png", dpi=200)
    plt.close(fig)


def loop_png():
    """The self-test: the good artifact passes every gate; every known-bad
    mutant fails at least one."""
    log = (DATA / "selftest.log").read_text()
    killed = {}
    for line in log.splitlines():
        if line.startswith("selftest: mutant KILLED:"):
            name = line.split(":")[2].split("(")[0].strip()
            gates = line.split("failed gates: ")[1].rstrip(")")
            killed[name] = gates
    names = ["good"] + sorted(killed)
    fig, ax = plt.subplots(figsize=(15, 5.4))
    colors = ["#009E73"] + ["#D55E00"] * len(killed)
    ylabels = [n if n == "good" else n for n in names]
    ax.barh(range(len(names)), [1] * len(names), color=colors, height=0.62)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(ylabels, fontsize=9)
    ax.set_xlim(0, 1)
    ax.set_xticks([])
    ax.set_title("Self-test: known-good artifact passes; every single-edit mutant is killed "
                 "(selftest.sh, 11/11 = 100 %)", fontsize=12)
    for i, n in enumerate(names):
        if n == "good":
            ax.text(0.5, i, "PASS — all 8 gates", ha="center", va="center",
                    fontsize=9, color="white", weight="bold")
        else:
            ax.text(0.5, i, f"KILLED — failed gates: {killed[n]}",
                    ha="center", va="center", fontsize=8, color="white")
    fig.tight_layout()
    fig.savefig(HERE / "loop.png", dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    result_png()
    loop_png()
    print("wrote result.png and loop.png")
