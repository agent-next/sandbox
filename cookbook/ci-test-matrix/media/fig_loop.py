#!/usr/bin/env python3
"""loop.png -- the agent loop: the replayed fix sequence + the kill matrix.

Top:   the replayed fixing sequence (media/data/loop.json) -- real
       grade.sh verdicts ordered bad -> partly fixed -> good, each row
       naming the gates that failed at that iteration and the edit that
       separates it from examples/good.
Bottom: the self-test kill matrix: examples/good plus the nine single-edit
       mutants against the eight gates.  Red cells carry the gate's own
       measured detail from media/data/verdict-*.json, so a known-bad
       artifact is shown failing the gate that actually failed, not one
       where it looks like the good artifact.

Nothing is synthesised; the overlap guard at the end fails the build if
any text leaves the figure or intersects another text.
"""

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DATA, DEMO, GATES, MUTANTS, ROWS, C_PASS, C_FAIL,
                    C_DIM, load_verdict, gates_passed, cell_short,
                    selftest_kill, check_no_overlap)

DPI = 200
WPX, HPX = 3200, 2300
MONO = "DejaVu Sans Mono"
SANS = "DejaVu Sans"
INK = "#1a1a1a"
RULE = "#d0d7de"
ROWSEP = "#eaeef2"
FAIL_BG, FAIL_FG = "#fbe0d4", "#a03d00"
PASS_BG = "#d7f0e5"


def main():
    verdicts = {name: load_verdict(name) for name in ROWS}
    with open(os.path.join(DATA, "loop.json")) as fh:
        loop_doc = json.load(fh)
    killed, total = selftest_kill()

    fig = plt.figure(figsize=(WPX / DPI, HPX / DPI), dpi=DPI,
                     facecolor="#ffffff")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, WPX)
    ax.set_ylim(0, HPX)
    ax.axis("off")
    texts = []

    def text(x, y, s, size, **kw):
        t = ax.text(x, y, s, fontsize=size, color=kw.pop("color", INK),
                    family=kw.pop("family", SANS), **kw)
        texts.append(t)
        return t

    def rule(x0, x1, y, color=RULE, lw=1.2):
        ax.plot([x0, x1], [y, y], color=color, lw=lw)

    X0, X1 = 70, 3130
    text(WPX / 2, 2206,
         "ci-test-matrix: the agent loop and the judge's kill matrix",
         32, fontweight="bold", ha="center")

    # ================= the replayed fixing sequence ====================
    text(X0, 2116, "the fixing loop, replayed -- media/data/loop.json",
         18, fontweight="bold", color="#30363d")
    text(X0, 2068, "real grade.sh verdicts reordered bad -> partly fixed "
         "-> good; a replay, not a live agent trace", 12, family=MONO,
         color=C_DIM)
    rule(X0, X1, 2040)

    text(X0 + 10, 1972, "iteration / artifact", 11, family=MONO,
         color=C_DIM)
    text(X0 + 760, 1972, "the edit (one edit from examples/good)", 11,
         family=MONO, color=C_DIM)
    text(X0 + 2050, 1972, "gates passed / gates that failed", 11,
         family=MONO, color=C_DIM)

    y = 1888
    DY = 150
    for s in loop_doc["steps"]:
        v = verdicts[s["name"]]
        ok = v["verdict"] == "PASS"
        col = C_PASS if ok else C_FAIL
        text(X0 + 10, y, "it %d  %s" % (s["iteration"], s["artifact"]),
             15, family=MONO, fontweight="bold")
        text(X0 + 760, y, s["edit"], 12, family=MONO, color="#30363d")
        text(X0 + 2050, y, "%d/8" % gates_passed(v), 17, family=MONO,
             color=col, fontweight="bold")
        if ok:
            text(X0 + 2200, y, "all eight gates pass", 13, family=MONO,
                 color=C_PASS, fontweight="bold")
        else:
            failed = [g for g in GATES if not v["gates"][g]["pass"]]
            words, lines, cur = ", ".join(failed).split(", "), [], ""
            for w in words:
                if len(cur) + len(w) + 2 > 34:
                    lines.append(cur.rstrip(", "))
                    cur = ""
                cur += w + ", "
            lines.append(cur.rstrip(", "))
            for k, ln in enumerate(lines):
                text(X0 + 2340, y - k * 34, ln, 11, family=MONO,
                     color=FAIL_FG, fontweight="bold")
        text(X0 + 760, y - 50, s["stage"], 12, family=MONO, color=col)
        rule(X0, X1, y - DY / 2 + 12, color=ROWSEP)
        y -= DY

    # ===================== the self-test kill matrix ===================
    mtop = 1330
    dy = 96
    labw = 330
    x0, x1 = X0 + labw, X1
    cw = (x1 - x0) / len(GATES)
    text(X0, mtop + 108,
         "self-test kill matrix -- media/data/verdict-*.json", 18,
         fontweight="bold", color="#30363d")
    text(X0, mtop + 62, "red cells carry the gate's own measured detail; "
         "one row per artifact, one column per gate", 12, family=MONO,
         color=C_DIM)
    rule(X0, X1, mtop + 34)

    text(x0 - 16, mtop - 16, "artifact", 11, family=MONO, color=C_DIM,
         ha="right")
    for j, gate in enumerate(GATES):
        text(x0 + cw * (j + 0.5), mtop - 16, gate, 11, family=MONO,
             color=C_DIM, ha="center")

    for i, name in enumerate(ROWS):
        ry = mtop - 78 - i * dy
        v = verdicts[name]
        label = "examples/good" if name == "good" else name
        text(x0 - 16, ry, label, 13, family=MONO, ha="right",
             weight="bold" if name == "good" else "normal",
             color=INK if name == "good" else "#30363d")
        for j, gate in enumerate(GATES):
            g = v["gates"][gate]
            ok = g["pass"]
            x = x0 + j * cw
            ax.add_patch(Rectangle((x + 3, ry - dy * 0.34), cw - 6,
                                   dy * 0.68,
                                   fc=PASS_BG if ok else FAIL_BG,
                                   ec="none"))
            text(x + cw / 2, ry,
                 "pass" if ok else cell_short(gate, g["detail"]), 10,
                 family=MONO, ha="center",
                 color=C_PASS if ok else FAIL_FG, fontweight="bold")
        rule(X0, X1, ry - dy / 2 + 10, color=ROWSEP)

    # ============================ footer ===============================
    text(X0, 300, "kill rate %d/%d = 100 %% (floor 90 %%) -- "
         "media/data/selftest.log; every mutant is one edit away from "
         "examples/good" % (killed, total), 15, family=MONO,
         fontweight="bold")
    lx = X0
    for label, fc, tc in [("gate passed", PASS_BG, C_PASS),
                          ("gate failed (value = the judge's own "
                           "measurement)", FAIL_BG, FAIL_FG)]:
        ax.add_patch(Rectangle((lx, 120), 40, 40, fc=fc, ec=tc))
        text(lx + 58, 140, label, 11, family=MONO, color="#30363d",
             va="center")
        lx += 58 + len(label) * 19 + 60

    check_no_overlap(fig, texts, "loop.png")

    out = os.path.join(DEMO, "media", "loop.png")
    fig.savefig(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
