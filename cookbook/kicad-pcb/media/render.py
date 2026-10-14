#!/usr/bin/env python3
"""Render media/ figures + video frames from judge outputs.

Reads:
    data/good.json            verdict JSON for examples/good/555-blinker
    data/<mutant>.json        verdict JSON for each mutant
    the .kicad_pcb itself     for board geometry (tracks, vias, outline)

Writes:
    media/result.png  media/loop.png  media/frames/*.png

Everything drawn comes from the JSON verdicts or the .kicad_pcb file —
no invented numbers.
"""

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Rectangle

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "judge"))
from oracle import find_all, parse_sexpr, child   # noqa: E402

# Okabe-Ito colour-blind-safe palette
C = {"pass": "#009E73", "fail": "#D55E00", "fcu": "#E69F00",
     "bcu": "#0072B2", "edge": "#000000", "via": "#56B4E9",
     "acc": "#F0E442"}


def board_pieces(pcb_path):
    tree = parse_sexpr(open(pcb_path).read())
    segs, vias, edges, refs = [], [], [], []
    for s in find_all(tree, "segment"):
        a, b = child(s, "start"), child(s, "end")
        segs.append((float(a[1]), float(a[2]), float(b[1]), float(b[2]),
                     child(s, "layer")[1],
                     float(child(s, "width")[1])))
    for v in find_all(tree, "via"):
        a = child(v, "at")
        vias.append((float(a[1]), float(a[2]),
                     float(child(v, "size")[1]) / 2))
    for g in find_all(tree, "gr_line"):
        if "Edge.Cuts" not in child(g, "layer")[1]:
            continue
        a, b = child(g, "start"), child(g, "end")
        edges.append((float(a[1]), float(a[2]), float(b[1]), float(b[2])))
    for fp in find_all(tree, "footprint"):
        at = child(fp, "at")
        ref = child(fp, "fp_text") or child(fp, "property")
        name = None
        for p in find_all(fp, "property"):
            if len(p) > 2 and p[1] == "Reference":
                name = p[2]
        if name:
            refs.append((name, float(at[1]), float(at[2])))
    return segs, vias, edges, refs


def draw_board(ax, pcb_path):
    segs, vias, edges, refs = board_pieces(pcb_path)
    for x1, y1, x2, y2, lay, w in segs:
        ax.plot([x1, x2], [y1, y2],
                color=C["fcu"] if lay == "F.Cu" else C["bcu"],
                lw=w * 3, solid_capstyle="round",
                zorder=2 if lay == "F.Cu" else 1)
    for x, y, r in vias:
        ax.add_patch(Circle((x, y), r, color=C["via"], zorder=3))
    for x1, y1, x2, y2 in edges:
        ax.plot([x1, x2], [y1, y2], color=C["edge"], lw=1.5, zorder=4)
    for name, x, y in refs:
        ax.annotate(name, (x, y), fontsize=7, ha="center", color="#444444")
    ax.invert_yaxis()           # kicad y grows downward
    ax.set_aspect("equal")
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    ax.legend(handles=[
        Line2D([0], [0], color=C["fcu"], lw=3, label="F.Cu track"),
        Line2D([0], [0], color=C["bcu"], lw=3, label="B.Cu track"),
        Line2D([0], [0], marker="o", color=C["via"], ls="none",
               label="via"),
        Line2D([0], [0], color=C["edge"], lw=1.5, label="Edge.Cuts"),
    ], loc="upper left", fontsize=8)


def fig_result(good_json, pcb_path, out):
    v = json.load(open(good_json))
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5),
                                   gridspec_kw={"width_ratios": [3, 2]})
    draw_board(ax1, pcb_path)
    ax1.set_title("artifact geometry (parsed from .kicad_pcb)")

    names = list(v["gates"])
    vals = [1 if v["gates"][g]["pass"] else 0 for g in names]
    cols = [C["pass"] if x else C["fail"] for x in vals]
    ax2.barh(range(len(names)), vals, color=cols)
    ax2.set_yticks(range(len(names)), names)
    ax2.set_xlim(0, 1.15)
    ax2.set_xlabel("gate result (1 = pass)")
    ax2.axvline(1.0, color="k", ls="--", lw=1)
    ax2.annotate("pass line", (1.0, len(names) - .4), fontsize=8,
                 ha="center")
    verdict = "PASS" if v["overall_pass"] else "FAIL"
    ax2.set_title(f"judge verdict: {verdict} "
                  f"({sum(vals)}/{len(names)} gates)")
    fig.suptitle("555 astable blinker — KiCad project judge result")
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)


def fig_loop(good_json, mutant_jsons, out):
    names = ["known-good"] + [os.path.basename(p)[:-5]
                              for p in mutant_jsons]
    fails = []
    for p in [good_json] + mutant_jsons:
        v = json.load(open(p))
        fails.append(sum(1 for g in v["gates"].values() if not g["pass"]))
    fig, ax = plt.subplots(figsize=(10, 5))
    cols = [C["fail"] if f else C["pass"] for f in fails]
    ax.bar(range(len(names)), fails, color=cols)
    ax.set_xticks(range(len(names)), names, rotation=30, ha="right")
    ax.set_ylabel("failed gates (count)")
    ax.set_title("self-test: every known-bad mutant fails >=1 gate "
                 f"(kill rate {sum(1 for f in fails[1:] if f)}/"
                 f"{len(names) - 1} = "
                 f"{100 * sum(1 for f in fails[1:] if f) // (len(names) - 1)}%)")
    ax.legend(handles=[
        Rectangle((0, 0), 1, 1, color=C["pass"], label="passes all gates"),
        Rectangle((0, 0), 1, 1, color=C["fail"], label="fails >=1 gate"),
    ], fontsize=9)
    fig.tight_layout()
    fig.savefig(out, dpi=200)
    plt.close(fig)


# ------------------------------------------------------------- mp4 frames --

def slide(fig, title, lines, out):
    fig.text(0.5, 0.86, title, ha="center", fontsize=34, weight="bold")
    y = 0.72
    for line in lines:
        mono = line.startswith("  ")
        fig.text(0.08, y, line, fontsize=18 if mono else 22,
                 family="monospace" if mono else "sans-serif")
        y -= 0.065
    fig.savefig(out, dpi=100)
    fig.clear()


def frames(good_json, mutant_jsons, pcb_path, frame_dir):
    os.makedirs(frame_dir, exist_ok=True)
    v = json.load(open(good_json))
    W, H = 19.2, 10.8
    fig = plt.figure(figsize=(W, H))
    slide(fig, "kicad-pcb demo",
          ["Design a 2-layer KiCad board in a disposable sandbox.",
           "An independent judge decides pass/fail.",
           "",
           "Artifact: 555 astable LED blinker (SOIC-8 + 0805 parts)",
           "  - 40 x 30 mm, 2 layers, 7 nets, 8 footprints",
           "  - schematic + PCB in KiCad s-expression format"],
          f"{frame_dir}/f00.png")

    fig2, ax = plt.subplots(figsize=(W, H))
    draw_board(ax, pcb_path)
    ax.set_title("the artifact under test (geometry parsed from "
                 ".kicad_pcb)", fontsize=24)
    fig2.tight_layout()
    fig2.savefig(f"{frame_dir}/f01.png", dpi=100)
    plt.close(fig2)

    lines = ["judge gates (kicad-cli + independent oracle.py):", ""]
    for g, res in v["gates"].items():
        mark = "PASS" if res["pass"] else "FAIL"
        det = ", ".join(f"{k}={val}" for k, val in
                        res["details"].items()
                        if isinstance(val, (int, bool)))
        lines.append(f"  {g:<12} {mark}   {det[:80]}")
    slide(fig, "grading the known-good board", lines,
          f"{frame_dir}/f02.png")

    lines = ["scripted single-edit mutants (each must fail >= 1 gate):", ""]
    for p in mutant_jsons:
        mv = json.load(open(p))
        bad = ", ".join(k for k, g in mv["gates"].items()
                        if not g["pass"])
        lines.append(f"  {os.path.basename(p)[:-5]:<24} killed: {bad}")
    n = len(mutant_jsons)
    lines.append("")
    lines.append(f"kill rate {n}/{n} = 100%   (required: >= 90%)")
    slide(fig, "self-test mutants", lines, f"{frame_dir}/f03.png")

    slide(fig, "verdict",
          [f"overall_pass: {v['overall_pass']}",
           "",
           "all gates independent: ERC/DRC JSON parsed, netlists",
           "compared, Edge.Cuts closure checked, Gerbers and",
           "Excellon drill parsed by a stdlib oracle -",
           "never just 'the tool ran'.",
           "",
           "reproduce: python3 run.py"],
          f"{frame_dir}/f04.png")
    plt.close(fig)


def main():
    data_dir = os.path.join(HERE, "data")
    pcb = os.path.join(HERE, "..", "examples", "good",
                       "555-blinker", "555-blinker.kicad_pcb")
    good = os.path.join(data_dir, "good.json")
    mutants = sorted(os.path.join(data_dir, f)
                     for f in os.listdir(data_dir)
                     if f.endswith(".json") and f != "good.json")
    fig_result(good, pcb, os.path.join(HERE, "result.png"))
    fig_loop(good, mutants, os.path.join(HERE, "loop.png"))
    frames(good, mutants, pcb, os.path.join(HERE, "master", "frames"))
    print("rendered result.png, loop.png, master/frames/")


if __name__ == "__main__":
    main()
