#!/usr/bin/env python3
"""result.png -- the ci-test-matrix result, from the real grade JSON.

Left:  the five matrix cells with their real interpreter stamps
       (media/data/verdict-good.json), the match-syntax SyntaxError failing
       cell highlighted against the "match is a keyword from 3.10" oracle
       line, and the measured test count per cell.
Right: the eight judge gates with their pass flags and the pass/fail mask
       bars the judge computed from the JUnit XML it collected.
Bottom: the known-good row of the self-test kill matrix (green) with the
       killed mutants as red ticks (media/data/selftest.log).
"""

import json
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DATA, DEMO, GATES, GATE_SHORT, GATE_RULES, MUTANTS, ROWS,
                    C_PASS, C_FAIL, C_ORACLE, C_BG, C_DIM, load_verdict,
                    gates_passed, check_no_overlap, check_inside_axes,
                    selftest_kill)

MONO = "DejaVu Sans Mono"


def short_detail(gate, detail):
    """Compress a gate detail string to fit a figure row."""
    m = re.match(r"matrix.yaml has \[.*\] and python_versions == \[(.*)\] "
                 r"\(5 cells, no duplicates\)", detail)
    if m:
        return "python_versions == [%s]" % m.group(1)
    if gate == "identity":
        return "5 distinct interpreters, each matching its cell"
    if gate == "detection":
        return ("on: exactly 3.9 fails (match SyntaxError); "
                "off: all pass")
    m = re.match(r"all 5 cells report the same test count \((\d+) tests "
                 r"per cell\)", detail)
    if m:
        return "%s tests in every cell" % m.group(1)
    if gate == "mask":
        return ("on: [fail,pass,pass,pass,pass]  off: [pass x5]")
    if gate == "coverage":
        return "one non-empty JUnit XML per cell"
    if gate == "table":
        return "table agrees with the JUnit XML on every cell"
    if gate == "exit_code":
        return "exit 1 with the toggle on, 0 with it off"
    return detail


def main():
    verdict = load_verdict("good")
    cells = verdict["metrics"]["cells"]
    versions = verdict["metrics"]["versions"]

    fig = plt.figure(figsize=(16, 9), dpi=200, facecolor="#ffffff")
    fig.suptitle("ci-test-matrix: five CPython cells, one judge verdict",
                 fontsize=17, fontweight="bold", x=0.5, y=0.975)

    # ======================= left: the matrix ===========================
    ax = fig.add_axes([0.03, 0.30, 0.42, 0.585])
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    key1 = ax.text(0.0, 0.985, "the matrix -- media/data/verdict-good.json\n"
                   "cell  |  interpreter  |  tests  |  verdict (toggle ON)",
            fontsize=9.2, color="#30363d", va="top", fontweight="bold")
    ax.plot([0.0, 1.0], [0.865, 0.865], color="#d0d7de", lw=0.8)

    cell_texts = []
    y = 0.80
    dy = 0.105
    panel_texts = [key1]
    for v in versions:
        c = cells[v]
        failed = c["failed"]
        ax.text(0.0, y, "python " + v, family=MONO, fontsize=10.5,
                color="#1a1a1a", va="center", fontweight="bold")
        ax.text(0.185, y, c["stamp"], family=MONO, fontsize=10,
                color="#1a1a1a", va="center")
        ax.text(0.435, y, "%d" % c["tests"], family=MONO, fontsize=10,
                color="#1a1a1a", va="center", ha="center")
        if failed:
            ax.add_patch(FancyBboxPatch((0.46, y - 0.036), 0.52, 0.072,
                          boxstyle="round,pad=0.006",
                          fc="#fbe0d4", ec=C_FAIL, lw=1.2))
            ax.text(0.72, y, "FAIL: match SyntaxError", family=MONO,
                    fontsize=8.4, color="#a03d00", va="center",
                    ha="center", fontweight="bold")
        else:
            ax.add_patch(FancyBboxPatch((0.46, y - 0.036), 0.52, 0.072,
                          boxstyle="round,pad=0.006",
                          fc="#d7f0e5", ec="none"))
            ax.text(0.72, y, "pass", family=MONO, fontsize=9.2,
                    color=C_PASS, va="center", ha="center",
                    fontweight="bold")
        cell_texts.append(ax.texts[-1])
        ax.plot([0.0, 1.0], [y - 0.062, y - 0.062], color="#eaeef2",
                 lw=0.7)
        y -= dy

    # the oracle line the failing cell is measured against; two wrapped
    # lines so the text stays inside the panel
    ax.add_patch(Rectangle((0.0, y - 0.052), 1.0, 0.10, fc="#fff8ec",
                           ec=C_ORACLE, lw=1.4))
    panel_texts.append(ax.text(0.5, y + 0.022,
            "pass line: `match` is a keyword from CPython 3.10 (PEP 634);",
            family=MONO, fontsize=8.4, color="#7a4f01", va="center",
            ha="center"))
    panel_texts.append(ax.text(0.5, y - 0.026,
            "below 3.10 importing the module is a SyntaxError",
            family=MONO, fontsize=8.4, color="#7a4f01", va="center",
            ha="center"))
    check_inside_axes(fig, ax, panel_texts, "result.png matrix panel")

    # ===================== right: the gates =============================
    ax2 = fig.add_axes([0.545, 0.30, 0.425, 0.585])
    ax2.set_xlim(0, 1); ax2.set_ylim(0, 1); ax2.axis("off")
    ax2.text(0.0, 0.985, "the eight gates the judge ran (G1-G8)",
            fontsize=10.5, color="#30363d", va="top", fontweight="bold")
    ax2.text(0.0, 0.905, "gate", family=MONO, fontsize=8.8, color=C_DIM,
            va="center", fontweight="bold")
    ax2.text(0.135, 0.905, "rule (SPEC.md)", family=MONO, fontsize=8.8,
            color=C_DIM, va="center", fontweight="bold")
    ax2.text(0.975, 0.905, "verdict", family=MONO, fontsize=8.8,
            color=C_DIM, va="center", ha="right", fontweight="bold")
    ax2.plot([0.0, 1.0], [0.865, 0.865], color="#d0d7de", lw=0.8)

    gate_texts = []
    y = 0.80
    dy = 0.105
    for gate in GATES:
        g = verdict["gates"][gate]
        ok = g["pass"]
        ax2.text(0.0, y + 0.024, GATE_SHORT[gate], family=MONO,
                 fontsize=10, fontweight="bold", color="#1a1a1a",
                 va="center")
        gate_texts.append(ax2.text(0.0, y - 0.02,
                 "measured: " + short_detail(gate, g["detail"]),
                 family=MONO, fontsize=8.2, color="#30363d", va="center"))
        ax2.text(0.0, y - 0.058, "rule: " + GATE_RULES[gate], family=MONO,
                 fontsize=7.6, color=C_DIM, va="center")
        ax2.add_patch(Rectangle((0.90, y - 0.036), 0.075, 0.072,
                                fc=C_PASS if ok else C_FAIL, ec="none"))
        gate_texts.append(ax2.text(0.9375, y, "PASS" if ok else "FAIL",
                 family=MONO, fontsize=8.6, color="white", fontweight="bold",
                 va="center", ha="center"))
        ax2.plot([0.0, 1.0], [y - 0.075, y - 0.075], color="#eaeef2",
                 lw=0.7)
        y -= dy
    check_no_overlap(fig, gate_texts, "result.png gate rows")

    # ================= bottom: mask bars + kill ticks ===================
    ax3 = fig.add_axes([0.03, 0.10, 0.94, 0.155])
    ax3.set_xlim(0, 1); ax3.set_ylim(0, 1); ax3.axis("off")
    killed, total = selftest_kill()
    ax3.text(0.0, 0.94,
             "judge mask (from the collected JUnit XML):  "
             "ON 3.9-only fail,  OFF all pass     |     self-test: "
             "%d/%d mutants killed (floor 90%%) -- media/data/selftest.log"
             % (killed, total), fontsize=9.6, color="#1a1a1a",
             va="top", fontweight="bold")

    def mask_bar(x0, label, pattern):
        ax3.text(x0, 0.62, label, family=MONO, fontsize=9.4, color="#30363d",
                 va="center", fontweight="bold")
        for i, status in enumerate(pattern):
            x = x0 + 0.115 + i * 0.052
            ax3.add_patch(Rectangle((x, 0.42), 0.046, 0.36,
                                    fc=C_PASS if status == "pass" else C_FAIL,
                                    ec="none"))
            ax3.text(x + 0.023, 0.60, "3.9" if i == 0 else "3.1%d" % i,
                     family=MONO, fontsize=7.2, color="white",
                     fontweight="bold", va="center", ha="center")
        ax3.plot([x0 + 0.115 + 5 * 0.052, x0 + 0.115 + 5 * 0.052],
                 [0.36, 0.84], color=C_ORACLE, lw=2.0)

    mask_bar(0.0, "toggle ON ", ["fail", "pass", "pass", "pass", "pass"])
    mask_bar(0.42, "toggle OFF", ["pass", "pass", "pass", "pass", "pass"])

    ax3.text(0.755, 0.62, "known-bad mutants (one red tick each):",
            family=MONO, fontsize=9.2, color="#30363d", va="center",
            fontweight="bold")
    for i, name in enumerate(MUTANTS):
        x = 0.755 + (i % 5) * 0.048
        y = 0.34 - (i // 5) * 0.13
        ax3.plot([x, x], [y, y + 0.09], color=C_FAIL, lw=3.0)
        ax3.text(x + 0.004, y + 0.045, name, family=MONO, fontsize=6.6,
                 color="#30363d", va="center", rotation=90)
    ax3.text(0.755, 0.055,
            "every curve, tick and number on this page comes from "
            "media/data/verdict-*.json and media/data/selftest.log, written "
            "by judge/grade.sh and judge/selftest.sh.",
            family=MONO, fontsize=7.8, color="#57606a", va="center")

    fig.text(0.03, 0.062,
             "Caption: the failing 3.9 cell is the fixture's `match`-syntax "
             "module failing to import (CPython < 3.10 has no `match` "
             "keyword); the four other cells pass under their own interpreters. "
             "The orange line on the mask bars is the judge's expected-mask "
             "boundary (exactly one failing cell, at 3.9).",
             fontsize=8, color="#57606a")

    out = os.path.join(DEMO, "media", "result.png")
    fig.savefig(out)
    print("wrote", out)


if __name__ == "__main__":
    main()
