#!/usr/bin/env python3
"""loop.png: mutant x gate matrix (the self-test's kill evidence) + kill rate.

Everything plotted comes from the judge's own outputs of the real self-test
run (media/data/):

  left  -- the matrix: one row per program the self-test graded (the
     known-good example plus the 7 single-edit mutants judge/mutate.py
     generates), one column per judge gate.  Green = that gate passed on
     that program, red = it failed, with the measured value vs the gate's
     limit in short text.  Sources: the verdict JSONs in media/data/replay/
     (one per program, written by grade.sh --json) and the self-test log
     media/data/selftest.log for the per-mutant catch lines.  inch_mode
     fails the units gate so early that the judge reports only 2 gates --
     its later columns stay blank (not run), never green.
  right -- the kill-rate bar the self-test prints: 7 of 7 mutants killed
     ("kill rate 7/7 (100%)" in selftest.log), drawn against the 90 %
     bar the cookbook's demo standard requires.

Layout: one canvas; a script-enforced check fails the build if any text
(figure texts, titles, tick labels, cell text, legend) leaves the canvas or
intersects other text.

Palette: dataviz reference instance (light mode), CVD-validated; green /
red are the status good / critical steps.
"""
import json
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_result import (DEMO, DATA, INK, INK2, MUTED, GRID, SURFACE,
                         GOOD, CRIT, check_layout, load)

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "text.color": INK, "axes.edgecolor": "#c3c2b7",
    "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.axisbelow": True, "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
})

# matrix columns: every gate the judge runs, in the verdict JSON's own order
GATES = ["artifact", "units", "program", "envelope", "stepdown", "stepover",
         "process", "rapid_safety", "residual", "gouge",
         "simulator_selfcheck", "reference"]

# rows: the known-good example, then each mutant in the self-test log order
ROWS = [("good (examples/good/cam.py)", "01_good")] + [
    (m, f"02_{m}") for m in
    ["deep_pass", "hot_feed", "inch_mode", "no_tool_offset",
     "rapid_into_stock", "swapped_arcs", "wide_stepover"]]


def fail_text(gate, g):
    """Short 'measured vs limit' label for a failing gate cell."""
    if gate == "units":
        return f"G20 line {g['g20_lines'][0]}\n(rule: G21 mm)"
    if gate == "stepdown":
        return (f"axial {g['max_axial_mm']:g} mm\n"
                f"(limit {g['limit_mm']:g})")
    if gate == "stepover":
        return (f"spacing {g['max_spacing_mm']:g} mm\n"
                f"(limit {g['limit_mm']:g})")
    if gate == "process":
        return (f"chip load {max(g['chip_load_mm_per_tooth']):g}\n"
                f"(limit {g['limits'][1]:g}); "
                f"{g['feed_moves_out_of_band']} moves")
    if gate == "rapid_safety":
        return (f"rapid {g['max_rapid_hit_mm']:g} mm deep\n"
                f"({g['rapids_below_safe_z']} below safe Z)")
    if gate == "residual":
        return (f"{g['worst_residual_mm']:g} mm left\n"
                f"({g['residual_cells']:,} cells)")
    if gate == "gouge":
        return (f"{g['worst_gouge_mm']:g} mm deep\n"
                f"({g['gouge_cells']:,} cells)")
    raise SystemExit(f"make_loop: no cell text rule for gate {gate}")


def main():
    verdicts = {key: json.load(open(load(f"replay/{key}.json")))
                for _, key in ROWS}
    log = open(load("selftest.log")).read()
    kills = re.findall(r"KILLED: (\w+)\s+\(caught by: ([\w, ]+)\)", log)
    rate = re.search(r"kill rate (\d+)/(\d+) \((\d+)%\)", log)
    if not kills or not rate:
        raise SystemExit("make_loop: could not read the kill report from "
                         "media/data/selftest.log")
    n_killed, n_mutants, pct = (int(rate.group(i)) for i in (1, 2, 3))

    fig = plt.figure(figsize=(16, 9), dpi=175)
    fig.text(0.03, 0.965,
             "cnc-gcode: every mutant the self-test plants is caught by "
             "the judge",
             fontsize=15, fontweight="bold", color=INK, va="baseline")
    fig.text(0.03, 0.936,
             "Source: verdict JSONs from the real grade run "
             "(grade.sh --json, one per program) and the self-test log; "
             "each red cell is a gate that program failed, with the value "
             "the judge measured against the gate's limit",
             fontsize=9.5, color=INK2, va="baseline")

    # ---------------------------------------------------------------- matrix
    axM = fig.add_axes([0.185, 0.16, 0.545, 0.705])
    axM.grid(visible=False)
    axM.set_aspect("auto")
    for r, (name, key) in enumerate(ROWS):
        v = verdicts[key]
        gates = v["gates"]
        for c, gate in enumerate(GATES):
            if gate not in gates:
                continue        # inch_mode aborts after the units gate
            g = gates[gate]
            ok = bool(g["pass"])
            axM.add_patch(plt.Rectangle((c, len(ROWS) - 1 - r), 0.94, 0.94,
                                        facecolor=GOOD if ok else CRIT,
                                        alpha=0.16, edgecolor="none"))
            if not ok:
                axM.text(c + 0.47, len(ROWS) - 1 - r + 0.47,
                         fail_text(gate, g), ha="center", va="center",
                         fontsize=7.6, color=CRIT, linespacing=1.25,
                         fontweight="bold")
    axM.set_xlim(0, len(GATES))
    axM.set_ylim(-0.03, len(ROWS))
    axM.set_xticks(np.arange(len(GATES)) + 0.47)
    axM.set_xticklabels(GATES, fontsize=8, color=INK2)
    for tick in axM.get_xticklabels():
        tick.set_rotation(90)
        tick.set_va("top")
    axM.set_yticks(np.arange(len(ROWS)) + 0.5)
    axM.set_yticklabels([n for n, _ in ROWS][::-1], fontsize=9.5, color=INK)
    axM.tick_params(length=0)
    axM.set_title(
        "the judge's 12 gates x the 8 programs the self-test grades  "
        "(green = gate passed, red = failed)",
        fontsize=11, color=INK, loc="left", pad=8)
    axM.legend(handles=[
        Patch(facecolor=GOOD, alpha=0.25, label="gate passed"),
        Patch(facecolor=CRIT, alpha=0.25, label="gate failed (value shown)"),
        Patch(facecolor=SURFACE, edgecolor="#c3c2b7",
              label="gate not run (verdict already final)"),
    ], loc="upper center", bbox_to_anchor=(0.5, -0.145), ncol=3,
        fontsize=9, frameon=False, handlelength=1.4)

    # ------------------------------------------------------------ kill-rate
    axK = fig.add_axes([0.775, 0.39, 0.19, 0.23])
    axK.grid(axis="y", visible=False)
    axK.barh([0], [pct], height=0.42, color=GOOD)
    axK.barh([0], [100 - pct], left=[pct], height=0.42, color=SURFACE)
    axK.axvline(90, color=CRIT, lw=1.6, ls=(0, (4, 3)))
    axK.text(88.5, 0.5, "90% -- the demo\nstandard's floor ", fontsize=8.5,
             color=CRIT, va="center", ha="right", linespacing=1.3)
    axK.text(pct - 2, 0, f"{pct}%", va="center", ha="right", fontsize=15,
             fontweight="bold", color=GOOD)
    axK.set_xlim(0, 104)
    axK.set_ylim(-0.55, 0.75)
    axK.set_yticks([])
    axK.set_xticks([0, 25, 50, 75])
    axK.tick_params(axis="x", labelsize=8.5)
    axK.set_xlabel("self-test kill rate", fontsize=9.5)
    axK.set_title(
        f"kill rate: {n_killed}/{n_mutants} mutants\ncaught by at least "
        "one gate", fontsize=11, color=INK, loc="left", pad=8)

    caught = ", ".join(f"{m}: {g}" for m, g in kills)
    fig.text(0.775, 0.30,
             "each mutant caught by (selftest.log):\n" +
             "\n".join(re.sub(r"\s+", " ", f"{m} -- {g}")
                       for m, g in kills),
             fontsize=9.3, color=INK2, va="top", linespacing=1.65)

    n = check_layout(fig)
    fig.savefig(os.path.join(DEMO, "media", "loop.png"), dpi=175)
    print(f"make_loop: wrote media/loop.png ({n} texts checked, "
          "none outside the canvas, no overlap)")


if __name__ == "__main__":
    main()
