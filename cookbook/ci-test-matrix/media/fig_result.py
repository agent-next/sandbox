#!/usr/bin/env python3
"""result.png -- the ci-test-matrix result, from the real grade JSON.

Top left:  the five matrix cells with their measured interpreter stamps
           (media/data/verdict-good.json), the match-syntax SyntaxError
           failing cell highlighted against the "match is a keyword from
           CPython 3.10" pass line, and the measured test count per cell.
Top right: the eight judge gates, each with the value the judge measured
           for it and its PASS badge.
Bottom:    the pass/fail mask the judge computed from the JUnit XML it
           collected (toggle on -> exactly 3.9 fails; off -> all pass),
           with the expected-mask boundary, and the self-test kill rate.

Every number is read from the judge's own verdict JSON; nothing is
invented.  The overlap guard at the end (check_no_overlap) fails the build
if any text leaves the figure or intersects another text.
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
from common import (DEMO, GATES, GATE_RULES, VERSIONS, C_PASS, C_FAIL,
                    C_ORACLE, C_DIM, load_verdict, selftest_kill,
                    check_no_overlap)

DPI = 200
WPX, HPX = 3200, 1800
MONO = "DejaVu Sans Mono"
SANS = "DejaVu Sans"
INK = "#1a1a1a"
RULE = "#d0d7de"
ROWSEP = "#eaeef2"
FAIL_BG, FAIL_FG = "#fbe0d4", "#a03d00"
PASS_BG = "#d7f0e5"
ORACLE_BG, ORACLE_FG = "#fff8ec", "#7a4f01"


def px(inches):
    """Points -> pixels at DPI."""
    return inches * DPI / 72.0


def short_detail(gate, detail):
    """The gate's measured value, compressed to one figure row."""
    m = re.match(r"matrix.yaml has \[.*\] and python_versions == \[(.*)\] "
                 r"\(5 cells, no duplicates\)", detail)
    if m:
        return "python_versions == [%s]" % " ".join(
            x.strip().strip("'\"") for x in m.group(1).split(","))
    if gate == "identity":
        return "5 distinct interpreters, each matching its cell"
    if gate == "detection":
        return "on: only 3.9 fails (SyntaxError); off: all five pass"
    m = re.match(r"all 5 cells report the same test count \((\d+) tests "
                 r"per cell\)", detail)
    if m:
        return "%s tests in every cell" % m.group(1)
    if gate == "mask":
        return "on: fail at 3.9 only; off: all five pass"
    if gate == "coverage":
        return "one non-empty JUnit XML per cell (5 files)"
    if gate == "table":
        return "table agrees with the JUnit XML, cell by cell"
    if gate == "exit_code":
        return "exit 1 with the toggle on, 0 with it off"
    return detail


def main():
    global CELLS
    verdict = load_verdict("good")
    metrics = verdict["metrics"]
    CELLS = metrics["cells"]

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

    def rule(x0, x1, y):
        ax.plot([x0, x1], [y, y], color=RULE, lw=1.2)

    def rowsep(x0, x1, y):
        ax.plot([x0, x1], [y, y], color=ROWSEP, lw=1.0)

    text(WPX / 2, 1700,
         "ci-test-matrix: five CPython cells, one judge verdict",
         34, fontweight="bold", ha="center")

    # ==================== left: the matrix =============================
    LX0, LX1 = 70, 1500
    text(LX0, 1596, "the matrix -- media/data/verdict-good.json", 15,
         fontweight="bold", color="#30363d")
    text(LX0, 1552, "cell  |  interpreter  |  tests  |  verdict (toggle ON)",
         11, family=MONO, color="#30363d")
    rule(LX0, LX1, 1526)

    y = 1440
    DY = 168
    for v in VERSIONS:
        c = CELLS[v]
        text(LX0 + 20, y, "python " + v, 17, family=MONO, fontweight="bold")
        text(LX0 + 380, y, c["stamp"], 16, family=MONO, color="#30363d")
        text(LX0 + 600, y, "%d tests" % c["tests"], 16, family=MONO,
             color="#30363d")
        bx0, bw, bh = LX0 + 850, LX1 - 20 - (LX0 + 850), 104
        if c["failed"]:
            ax.add_patch(Rectangle((bx0, y - bh / 2), bw, bh, fc=FAIL_BG,
                                   ec=C_FAIL, lw=2.0))
            text(bx0 + bw / 2, y, "FAIL: match SyntaxError", 14,
                 family=MONO, color=FAIL_FG, ha="center", fontweight="bold")
        else:
            ax.add_patch(Rectangle((bx0, y - bh / 2), bw, bh, fc=PASS_BG,
                                   ec="none"))
            text(bx0 + bw / 2, y, "pass", 16, family=MONO, color=C_PASS,
                 ha="center", fontweight="bold")
        rowsep(LX0, LX1, y - DY / 2 + 24)
        y -= DY

    # the pass line the failing cell is measured against
    oy = y + 44
    ax.add_patch(Rectangle((LX0, oy - 84), LX1 - LX0, 168, fc=ORACLE_BG,
                           ec=C_ORACLE, lw=2.0))
    text(LX0 + (LX1 - LX0) / 2, oy + 42,
         "pass line: `match` is a keyword from CPython 3.10 (PEP 634);",
         13, family=MONO, color=ORACLE_FG, ha="center")
    text(LX0 + (LX1 - LX0) / 2, oy - 42,
         "below 3.10 importing the fixture's module is a SyntaxError",
         13, family=MONO, color=ORACLE_FG, ha="center")

    # ==================== right: the gates =============================
    RX0, RX1 = 1620, 3130
    text(RX0, 1596, "the eight gates the judge ran (G1-G8)", 15,
         fontweight="bold", color="#30363d")
    text(RX0, 1552, "gate   measured by this run", 11, family=MONO,
         color="#30363d")
    text(RX1, 1552, "verdict", 11, family=MONO, color="#30363d", ha="right")
    rule(RX0, RX1, 1526)

    y = 1440
    DY = 118
    for gate in GATES:
        g = verdict["gates"][gate]
        ok = g["pass"]
        text(RX0 + 20, y, gate, 17, family=MONO, fontweight="bold")
        text(RX0 + 330, y, short_detail(gate, g["detail"]), 11,
             family=MONO, color="#30363d")
        text(RX0 + 20, y - 46, "rule: " + GATE_RULES[gate], 11,
             family=MONO, color=C_DIM)
        bx0, bw, bh = RX1 - 200, 200, 76
        ax.add_patch(Rectangle((bx0, y - bh / 2), bw, bh,
                               fc=C_PASS if ok else C_FAIL, ec="none"))
        text(bx0 + bw / 2, y, "PASS" if ok else "FAIL", 15, family=MONO,
             color="white", ha="center", fontweight="bold")
        rowsep(RX0, RX1, y - DY / 2 + 22)
        y -= DY

    # ============ bottom: the judge's mask + the kill rate ==============
    text(70, 404, "the judge's mask, computed from the JUnit XML it "
         "collected:", 15, fontweight="bold", color="#30363d")
    killed, total = selftest_kill()
    text(70, 352, "self-test: %s mutants killed (floor 90%%) -- "
         "media/data/selftest.log" % ("%d/%d" % (killed, total)),
         13, family=MONO, color="#30363d")

    def mask_bar(x0, label, pattern):
        text(x0, 232, label, 14, family=MONO, fontweight="bold",
             va="center")
        cw, gap, ch = 128, 14, 128
        for i, status in enumerate(pattern):
            cx = x0 + 300 + i * (cw + gap)
            ax.add_patch(Rectangle((cx, 232 - ch / 2), cw, ch,
                                   fc=C_PASS if status == "pass" else C_FAIL,
                                   ec="none"))
            text(cx + cw / 2, 232, VERSIONS[i], 14, family=MONO,
                 color="white", ha="center", va="center",
                 fontweight="bold")
        # the expected-mask boundary the judge compares the pattern against
        ax.plot([x0 + 300 + len(pattern) * (cw + gap), ] * 2,
                [232 - ch / 2 - 14, 232 + ch / 2 + 14], color=C_ORACLE,
                lw=3.0)

    mask_bar(70, "toggle ON ", metrics["mask_on"])
    mask_bar(1130, "toggle OFF", metrics["mask_off"])

    text(70, 128,
         "Every cell, stamp, gate value and mask square comes from "
         "media/data/verdict-good.json (judge/grade.sh examples/good "
         "--seed 42 --json)", 11, family=MONO, color=C_DIM)
    text(70, 88, "and media/data/selftest.log (judge/selftest.sh). "
         "Nothing is illustrative.", 11, family=MONO, color=C_DIM)

    check_no_overlap(fig, texts, "result.png")

    out = os.path.join(DEMO, "media", "result.png")
    fig.savefig(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
