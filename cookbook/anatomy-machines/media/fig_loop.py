#!/usr/bin/env python3
"""loop.png -- known-good + 7 mutants x the 6 judge gates.

Every cell is read from media/data/verdict-*.json (real grade.sh output,
seed 42, collected by media/collect_data.sh).  Green = pass; red = the
gate fired, with the measured value that broke the threshold.
"""

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.path.join(HERE, "loop.png")

BG = "#20242e"
FG = "#d7dae3"
DIM = "#8b90a0"
C_PASS = "#24513a"
C_FAIL = "#7d3030"
MONO = "DejaVu Sans Mono"

GATES = ["1 loads clean", "2 rotates", "3 parts", "4 interaction",
         "5 frame rate", "6 capture"]
ROWS = ["good", "blank_canvas", "missing_parts", "console_error",
        "static_camera", "wrong_labels", "no_interaction", "tiny_capture"]


def load(name):
    with open(os.path.join(DATA, "verdict-%s.json" % name)) as f:
        return json.load(f)


def detail(g, timing):
    """Short measured reason a gate failed."""
    n = g["gate"]
    if n == 1:
        return "%d errs" % g.get("console_errors", -1)
    if n == 2:
        if min(g["variances"]) < g["variance_min"]:
            return "var %.0f" % min(g["variances"])
        if min(g["mean_abs_diffs"]) < g["mad_min"]:
            return "mad %.1f" % min(g["mean_abs_diffs"])
        return "chg %.1f%%" % (100 * min(g["changed_fractions"]))
    if n == 3:
        if g.get("duplicates"):
            return "%d dup" % g["duplicates"]
        return "rec %.2f" % g["recall"]
    if n == 4:
        return "%d/%d" % (g["info_ok"], g["info_total"])
    if n == 5:
        return "%.0f fps" % timing.get("measured_fps", 0)
    if n == 6:
        if g["w"] < g["width_min"]:
            return "%d px" % g["w"]
        if g["nonbg_fraction"] < g["nonbg_min"]:
            return "%.0f%% bg" % (100 * g["nonbg_fraction"])
        return "%d ovl" % g["label_overlaps"]
    return "fail"


def main():
    verdicts = {r: load(r) for r in ROWS}
    nr, nc = len(ROWS), len(GATES)

    fig, ax = plt.subplots(figsize=(12.8, 5.6), dpi=200)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, nc + 2.15)
    ax.set_ylim(0, nr + 1.6)
    ax.axis("off")

    cw, ch, gap = 1.0, 0.86, 0.14
    x0 = 2.05                     # row-label gutter width

    for c, name in enumerate(GATES):
        ax.text(x0 + c + cw / 2, nr + 0.72, name, fontsize=9.5,
                color=DIM, family=MONO, ha="center", va="center")

    for r, row in enumerate(ROWS):
        y = (nr - 1 - r) * (ch + gap) + 0.9
        v = verdicts[row]
        timing = v.get("timing", {})
        good = row == "good"
        ax.text(0.05, y + ch / 2, row, fontsize=10, family=MONO,
                color=FG if good else DIM, ha="left", va="center")
        killed = not v["all_gates_passed"]
        for c, g in enumerate(v["gates"]):
            ok = g["passed"]
            ax.add_patch(FancyBboxPatch(
                (x0 + c, y), cw - gap, ch,
                boxstyle="round,pad=0.012,rounding_size=0.05",
                facecolor=C_PASS if ok else C_FAIL,
                edgecolor="none"))
            ax.text(x0 + c + (cw - gap) / 2, y + ch / 2,
                    "pass" if ok else detail(g, timing),
                    fontsize=8.2, family=MONO, ha="center", va="center",
                    color=FG)
        ax.text(x0 + nc + 0.25, y + ch / 2,
                "PASSES" if not killed else "killed",
                fontsize=9.5, family=MONO, va="center",
                color="#7dd48a" if not killed else "#e08585",
                weight="bold")

    ax.text(0.05, 0.32,
            "self-test: good figure passes all 6 gates; %d/%d mutants "
            "killed; same-seed verdicts byte-identical outside timing "
            "(media/data/verdict-*.json, seed %d)"
            % (sum(1 for r in ROWS[1:] if not verdicts[r]["all_gates_passed"]),
               len(ROWS) - 1, verdicts["good"]["seed"]),
            fontsize=9.5, family=MONO, color=DIM)

    fig.savefig(OUT, dpi=200, facecolor=BG, bbox_inches="tight")
    print("fig_loop: wrote", OUT)


if __name__ == "__main__":
    sys.exit(main())
