#!/usr/bin/env python3
"""loop.png -- the agent loop: the replayed fix sequence + the kill matrix.

Left:  the replayed fixing sequence (media/data/loop.json) -- real grade.sh
       verdicts ordered bad -> partly fixed -> good, each row showing the
       gates that failed at that iteration.
Right: the self-test kill matrix: examples/good plus the nine single-edit
       mutants against the eight gates. Red cells carry the gate's own
       measured detail from media/data/verdict-*.json.
"""

import json
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DATA, GATES, GATE_SHORT, MUTANTS, ROWS, C_PASS, C_FAIL,
                    C_BG, C_DIM, load_verdict, gates_passed, cell_short,
                    selftest_kill, check_no_overlap)

MONO = "DejaVu Sans Mono"


def main():
    verdicts = {name: load_verdict(name) for name in ROWS}
    with open(os.path.join(DATA, "loop.json")) as fh:
        loop_doc = json.load(fh)
    killed, total = selftest_kill()

    fig = plt.figure(figsize=(16, 9.5), dpi=200, facecolor="#ffffff")
    fig.suptitle("ci-test-matrix: the agent loop and the judge's kill matrix",
                 fontsize=16, fontweight="bold", x=0.5, y=0.978)

    ax = fig.add_axes([0.0, 0.0, 1.0, 1.0])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

    # ================= left: replayed fix sequence ======================
    ax.text(0.02, 0.945, "replayed fix sequence -- media/data/loop.json",
            fontsize=11, fontweight="bold", color="#30363d", va="top")
    ax.text(0.02, 0.905, "(real grade.sh verdicts, reordered; not a live "
            "agent trace)", fontsize=8.6, color=C_DIM, va="top")

    y = 0.845
    dy = 0.062
    for i, s in enumerate(loop_doc["steps"]):
        name = s["artifact"].replace("examples/", "")
        v = verdicts.get(name) or load_verdict(name)
        failed = [k for k, g in v["gates"].items() if not g["pass"]]
        col = C_PASS if v["verdict"] == "PASS" else C_FAIL
        ax.text(0.02, y, "it %d" % s["iteration"], family=MONO, fontsize=9.6,
                color=C_DIM, va="center")
        ax.text(0.075, y, s["artifact"], family=MONO, fontsize=9.8,
                color="#1a1a1a", va="center", fontweight="bold")
        ax.text(0.30, y, "%d/8 gates" % gates_passed(v), family=MONO,
                fontsize=9.6, color=col, va="center", fontweight="bold")
        if v["verdict"] == "PASS":
            ax.text(0.40, y, "all gates pass", family=MONO, fontsize=9.4,
                    color=C_PASS, va="center")
        else:
            ax.text(0.40, y, "fails: " + ", ".join(failed[:4])
                    + (" ..." if len(failed) > 4 else ""), family=MONO,
                    fontsize=9.2, color=C_FAIL, va="center")
        ax.text(0.72, y, s["stage"], family=MONO, fontsize=8.8, color=C_DIM,
                va="center")
        y -= dy

    # ==================== right: the kill matrix ========================
    x0, x1 = 0.545, 0.965
    ytop, dy = 0.845, 0.052
    cw = (x1 - x0) / len(GATES)
    pad = 0.0035

    ax.text(x0, 0.945, "self-test kill matrix -- media/data/verdict-*.json",
            fontsize=11, fontweight="bold", color="#30363d", va="top")
    for j, gate in enumerate(GATES):
        ax.text(x0 + cw * (j + 0.5), ytop + 0.055, GATE_SHORT[gate],
                family=MONO, fontsize=8.8, fontweight="bold",
                color="#1a1a1a", ha="center", va="center")
    ax.text(x0 - 0.006, ytop + 0.055, "artifact", family=MONO, fontsize=8.8,
            fontweight="bold", color="#1a1a1a", ha="right", va="center")

    texts = []
    for i, name in enumerate(ROWS):
        y = ytop - i * dy
        v = verdicts[name]
        label = "examples/good" if name == "good" else name
        ax.text(x0 - 0.006, y, label, family=MONO, fontsize=8.8,
                color="#1a1a1a" if name == "good" else "#30363d",
                fontweight="bold" if name == "good" else "normal",
                ha="right", va="center")
        for j, gate in enumerate(GATES):
            g = v["gates"][gate]
            ok = g["pass"]
            x = x0 + j * cw
            if ok:
                fc, tc = "#d7f0e5", C_PASS
                txt = "pass"
            else:
                fc, tc = "#fbe0d4", "#a03d00"
                txt = cell_short(gate, g["detail"])
            ax.add_patch(Rectangle((x + pad, y - dy * 0.36),
                                   cw - 2 * pad, dy * 0.72,
                                   fc=fc, ec="none"))
            texts.append(ax.text(x + cw / 2, y, txt, family=MONO,
                         fontsize=6.8 if not ok else 7.8, color=tc,
                         ha="center", va="center", fontweight="bold"))

    # footer: kill rate + legend
    ax.text(0.02, 0.115,
            "kill rate %d/%d = 100%% (floor 90%%) -- media/data/selftest.log; "
            "every mutant is one edit away from examples/good"
            % (killed, total), family=MONO, fontsize=9.2, color="#1a1a1a",
            va="center", fontweight="bold")

    lx = 0.02
    for label, fc, tc in [("gate passed", "#d7f0e5", C_PASS),
                          ("gate failed (value = the judge's own "
                           "measurement)", "#fbe0d4", "#a03d00")]:
        ax.add_patch(Rectangle((lx, 0.055), 0.016, 0.024, fc=fc, ec=tc))
        ax.text(lx + 0.021, 0.067, label, family=MONO, fontsize=8,
                color="#30363d", va="center")
        lx += 0.021 + len(label) * 0.0062 + 0.02

    ax.text(0.02, 0.018,
            "Each cell comes from media/data/verdict-*.json written by "
            "judge/grade.sh --seed 42. Red-cell text is the gate's measured "
            "detail, e.g. identity 'cells 3.9, 3.10, ... share interpreter "
            ".3.12'.",
            family=MONO, fontsize=7.6, color="#57606a", va="center")

    check_no_overlap(fig, texts, "loop.png cell labels")

    out = os.path.join(os.path.dirname(DATA), "loop.png")
    fig.savefig(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
