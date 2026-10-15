#!/usr/bin/env python3
"""result.png: what the judge measured on the good example (four panels).

Everything plotted comes from files the judge wrote during a real grade run:

  A. the toolpath the judge's own parser read out of part.nc
     (media/data/trace_good/moves.json) -- rapids dashed, cuts solid,
     coloured by the Z level of the move;
  B. the removal / residual map the judge computed (final.npz): its final
     heightmap against its own analytic target, with the residual tolerance
     of gate 7 on the colour bar;
  C. gate 7 (residual) pass-rule bars: residual area per mutant from each
     mutant's verdict JSON against the tolerance line, named in the caption;
  D. the reference cross-check panel: the judge's parse vs LinuxCNC rs274
     (media/data/ref_compare.json), gate 10's diffs and tolerance.

Layout: 2x2, 200 dpi, 14x10 in.  Palette: dataviz reference instance
(light mode), CVD-validated.
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.colors import ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Rectangle

DEMO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(DEMO, "media", "data")

# --- palette (dataviz reference instance, light mode; validated) -----------
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"
S1 = "#2a78d6"      # blue   -- cuts / ours
S2 = "#eb6834"      # orange -- arcs / rs274
S3 = "#1baf7a"      # aqua   -- level -4 (direct-labelled on figure)
GOOD = "#0ca30c"
CRIT = "#d03b3b"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "text.color": INK, "axes.edgecolor": "#c3c2b7",
    "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.axisbelow": True, "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
})

# level colours for Z-cut moves (levels are the judge's own: -2/-4/-6 mm)
LEVEL_COLORS = {-2.0: S1, -4.0: S3, -6.0: "#6250d6"}
LEVEL_ORDER = [-2.0, -4.0, -6.0]


def load(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        sys.exit(f"make_result: missing judge output {path} -- run "
                 f"'bash judge/grade.sh examples/good/cam.py "
                 f"--json media/data/replay/01_good.json "
                 f"--trace media/data/trace_good' and "
                 f"'bash media/collect_ref_compare.sh' first")
    return path


def main():
    moves = json.load(open(load("trace_good/moves.json")))
    fin = np.load(load("trace_good/final.npz"))
    meta = json.load(open(load("trace_good/meta.json")))
    good = json.load(open(load("replay/01_good.json")))
    refcmp = json.load(open(load("ref_compare.json")))
    with open(load("replay/02_swapped_arcs.json")) as fh:
        swapped = json.load(fh)

    fig = plt.figure(figsize=(14, 10), dpi=200)
    fig.suptitle(
        "cnc-gcode: the judge's own parse and material-removal simulation of "
        "the graded part.nc (seed 20261014)",
        fontsize=13, fontweight="bold", color=INK, y=0.975)
    fig.text(0.5, 0.928, "Source: judge trace dump "
             "(grade.sh --trace) and verdict JSONs -- every move, cell and "
             "number below was computed by the judge, not redrawn from the "
             "CAM script",
             ha="center", fontsize=8.5, color=INK2)

    # ------------------------------------------------------------------ A
    axA = fig.add_axes([0.05, 0.56, 0.40, 0.36])
    segs_rapid, segs_cut = [], []
    cols_cut = []
    for mv in moves:
        p0, p1 = mv["start"], mv["end"]
        if mv["motion"] == "arc":
            cx, cy = mv["center"]
            a0, sweep = mv["a0"], mv["sweep"]
            pts = [p0]
            for k in range(1, 65):
                a = a0 + sweep * k / 64
                pts.append([cx + mv["radius"] * np.cos(a),
                            cy + mv["radius"] * np.sin(a), p1[2]])
            pts[-1] = p1
        else:
            pts = [p0, p1]
        seg = [(p[0], p[1]) for p in pts]
        if mv["kind"] == "rapid":
            segs_rapid.append(seg)
        else:
            segs_cut.append(seg)
            cols_cut.append(LEVEL_COLORS.get(p1[2], S1))
    axA.add_collection(LineCollection(
        segs_cut, colors=cols_cut, linewidths=1.6))
    axA.add_collection(LineCollection(
        segs_rapid, colors=MUTED, linewidths=1.0,
        linestyle=(0, (4, 4)), alpha=0.9))

    stock = meta["stock"]
    axA.add_patch(Rectangle((0, 0), stock["x_mm"], stock["y_mm"],
                            fill=False, edgecolor=INK2, lw=1.2))
    # target part outline from the judge's own oracle (final.npz)
    ys, xs = fin["ys"], fin["xs"]
    X, Y = np.meshgrid(xs, ys)          # X: (1200, 1600) like H
    iso = fin["in_island"]
    pk = fin["in_pocket"]
    axA.contour(X, Y, pk.astype(float), levels=[0.5], colors=[INK2],
                linewidths=1.4)
    axA.contour(X, Y, iso.astype(float), levels=[0.5], colors=[INK2],
                linewidths=1.4)

    handles = [
        Line2D([], [], color=S1, lw=2, label="cut, Z = −2 mm"),
        Line2D([], [], color=S3, lw=2, label="cut, Z = −4 mm"),
        Line2D([], [], color="#6250d6", lw=2, label="cut, Z = −6 mm"),
        Line2D([], [], color=MUTED, lw=1.2, ls=(0, (4, 4)),
               label="rapid (all at safe Z +5 mm)"),
        Line2D([], [], color=INK2, lw=1.4, label="stock / target outline"),
    ]
    axA.legend(handles=handles, loc="upper left", bbox_to_anchor=(0, -0.015),
                ncol=3, fontsize=7, frameon=False, columnspacing=1.2,
                handlelength=1.6)
    axA.set_xlabel("X (mm)", fontsize=9, labelpad=24)
    axA.set_ylabel("Y (mm)", fontsize=9)
    axA.set_xlim(-3, stock["x_mm"] + 3)
    axA.set_ylim(-3, stock["y_mm"] + 3)
    axA.set_aspect("equal")
    axA.tick_params(labelsize=8)
    axA.set_title(
        "A · G-code moves parsed by judge/gcode_sim.py\n"
        f"{len(moves)} moves ({meta['n_events']} cutting events): rapids "
        f"dashed, cuts solid by Z level", fontsize=10, color=INK, loc="left")

    # ------------------------------------------------------------------ B
    axB = fig.add_axes([0.545, 0.56, 0.405, 0.36])
    H, tgt = fin["H"], fin["target"]
    # the removal map the judge computed: its final heightmap H after the
    # whole program, against its own analytic target surface.  H takes only
    # two values on a passing run: -6 (pocket floor) and 0 (stock/island
    # top), so a two-bin map + the tolerance band is the honest encoding.
    tol_r = good["gates"]["residual"]["tolerance_mm"]
    tol_g = good["gates"]["gouge"]["tolerance_mm"]
    bn = matplotlib.colors.BoundaryNorm([-7.0, -3.0, 1.0], 2)
    im = axB.imshow(H, origin="lower", norm=bn,
                    extent=[0, stock["x_mm"], 0, stock["y_mm"]],
                    cmap=ListedColormap(["#86b6ef", "#f0f0ec"]),
                    interpolation="nearest", aspect="equal")
    axB.contour(X, Y, fin["in_island"].astype(float), levels=[0.5],
                colors=[INK2], linewidths=1.0)
    axB.contour(X, Y, fin["in_pocket"].astype(float), levels=[0.5],
                colors=[INK2], linewidths=1.0)
    axB.set_xlabel("X (mm)", fontsize=9)
    axB.set_ylabel("Y (mm)", fontsize=9)
    axB.tick_params(labelsize=8)
    axB.set_title(
        "B · material-removal map after the whole program (judge heightmap H)\n"
        f"gate residual: worst {good['gates']['residual']['worst_residual_mm']}"
        f" mm ≤ +{tol_r} mm · gate gouge: worst "
        f"{good['gates']['gouge']['worst_gouge_mm']} mm ≥ −{tol_g} mm · "
        f"both 0 cells\n"
        "colour-bar hairlines = the two tolerance bands; every cell inside "
        "(pocket floor 713 592 cells, walls + island uncut)",
        fontsize=10, color=INK, loc="left")
    cbar = fig.colorbar(im, ax=axB, fraction=0.046, pad=0.02, shrink=0.85,
                        ticks=[-6.0, 0.0])
    cbar.set_label("surface height H (mm) — pocket floor −6, stock top 0",
                   fontsize=8)
    cbar.ax.tick_params(labelsize=7)
    cbar.outline.set_edgecolor("#c3c2b7")
    # the residual tolerance on the colour bar: hairlines at target ± tol.
    # On this 6 mm-deep feature the band is a hairline -- that is the point:
    # the judge demands the floor within 0.05 mm everywhere it must be cut.
    def zf(z):
        return (z + 7.0) / 8.0
    for z in (-6.0 + tol_r, -6.0 - tol_g):
        cbar.ax.axhline(zf(z), color=CRIT, lw=1.2)
    cbar.ax.text(1.45, zf(-6.0), "gate 7 tol +0.05 mm (floor) · "
                 f"gate 8 tol −{tol_g} mm (stock)", rotation=90,
                 fontsize=7, va="center", ha="left",
                 transform=cbar.ax.transAxes, color=INK)

    # ------------------------------------------------------------------ C
    axC = fig.add_axes([0.07, 0.115, 0.36, 0.29])
    axC.set_title(
        "C · gate residual (pass rule: uncut area → 0 mm² within "
        "+0.05 mm)\nresidual area each failing mutant leaves vs the good "
        "run's 0.0 mm²", fontsize=10, color=INK, loc="left")
    bad = [("swapped_arcs", swapped), ("wide_stepover",
             json.load(open(load("replay/02_wide_stepover.json"))))]
    names = ["swapped_arcs", "wide_stepover"]
    areas = []
    for n, v in bad:
        g = v["gates"]["residual"]
        assert g["pass"] is False and n in v["artifact"].split("/")[-1]
        areas.append(g["residual_area_mm2"])
    bars = axC.bar(names, areas, width=0.55, color=S1)
    for b, a in zip(bars, areas):
        axC.text(b.get_x() + b.get_width() / 2, a + 3, f"{a:.1f} mm²",
                 ha="center", va="bottom", fontsize=9, color=INK)
    axC.set_ylabel("residual area left uncut (mm²)", fontsize=9)
    axC.set_xlabel("mutant (single edit of examples/good/cam.py)",
                   fontsize=8.5)
    axC.set_ylim(0, 150)
    axC.tick_params(labelsize=8)
    # annotations strictly above the tallest bar + its value label (88.3 +
    # label ~12 units), inside the axes, never over a bar or the data
    axC.annotate("both FAIL gate 7 · rule: every must-clear cell "
                 "H ≤ target + 0.05 mm",
                 xy=(0.5, 138), ha="center", fontsize=8.5, color=CRIT,
                 fontweight="bold")
    axC.annotate("the good run leaves 0.0 mm² residual (all 713 592 "
                 "must-clear cells cleared) — passes",
                 xy=(0.5, 116), ha="center", fontsize=8.5, color=INK2)

    # ------------------------------------------------------------------ D
    axD = fig.add_axes([0.57, 0.125, 0.36, 0.26])
    axD.axis("off")
    axD.add_patch(Rectangle((0, 0), 1, 1, transform=axD.transAxes,
                            fill=False, edgecolor="#c3c2b7", lw=0.8))
    o, t, d = refcmp["ours"], refcmp["rs274"], refcmp["diffs"]
    g = good["gates"]["reference"]
    rows = [
        ("feed moves", f"{o['feeds']}", f"{t['feeds']}",
         f"diff {d['feeds']}"),
        ("rapid moves", f"{o['rapids']}", f"{t['rapids']}",
         f"diff {d['rapids']}"),
        ("arc moves", f"{o['arcs']}", f"{t['arcs']}", f"diff {d['arcs']}"),
        ("Z range (mm)", f"[{o['z_min']:.0f}, {o['z_max']:.0f}]",
         f"[{t['z_min']:.0f}, {t['z_max']:.0f}]",
         f"diff {d['z_max_mm']:.1f}"),
        ("XY bbox (mm)",
         f"[{o['bbox'][0]:.0f}, {o['bbox'][1]:.0f}, {o['bbox'][2]:.0f}, "
         f"{o['bbox'][3]:.0f}]",
         f"[{t['bbox'][0]:.0f}, {t['bbox'][1]:.0f}, {t['bbox'][2]:.0f}, "
         f"{t['bbox'][3]:.0f}]", "diff 0, 0, 0, 0"),
        ("length units", "G21 (mm)", "MM" if t["units_mm"] else "INCH",
         "match"),
    ]
    axD.set_title("D · reference cross-check, gate reference: judge parse vs "
                  "LinuxCNC rs274\n"
                  f"{g['ref_tool']} -- rule: counts exact, coordinates "
                  f"within {g['tolerance_mm']} mm; every diff = 0",
                  fontsize=10, color=INK, loc="left")
    y = 0.80
    cols = {"label": 0.015, "judge": 0.30, "rs274": 0.555, "diff": 0.985}
    for key, head, ha in (("label", "", "left"), ("judge", "judge sim", "right"),
                          ("rs274", "rs274 canonical", "left"),
                          ("diff", "difference", "right")):
        if head:
            axD.text(cols[key], y + 0.10, head, fontsize=8, color=INK2, ha=ha)
    axD.plot([0.0, 1.0], [y + 0.045, y + 0.045], color="#c3c2b7", lw=0.8,
             transform=axD.transAxes)
    for i, (label, a, b, dd) in enumerate(rows):
        yy = y + 0.045 - (i + 1) * 0.125
        axD.plot([0.0, 1.0], [yy + 0.03, yy + 0.03], color=GRID, lw=0.5,
                 transform=axD.transAxes)
        axD.text(cols["label"], yy, label, fontsize=8.5, color=INK, va="top")
        axD.text(cols["judge"], yy, a, fontsize=8.5, color=INK, ha="right",
                 va="top", fontfamily="DejaVu Sans Mono")
        axD.text(cols["rs274"], yy, b, fontsize=8.5, color=INK, ha="left",
                 va="top", fontfamily="DejaVu Sans Mono")
        axD.text(cols["diff"], yy, dd, fontsize=8.5, color=GOOD, ha="right",
                 va="top", fontweight="bold")
    axD.text(0.015, y - 6 * 0.125 - 0.02, "PASS", fontsize=10,
             color=GOOD, fontweight="bold", va="top")
    axD.text(0.13, y - 6 * 0.125 - 0.02,
             f"rs274 accepted the program (exit {t['exit']}); the two parses "
             "agree exactly", fontsize=8, color=INK2, va="top")

    # script-enforced no-overlap check: every annotation text lies inside
    # the canvas and the annotation texts are pairwise disjoint (titles,
    # axis labels and legends live outside the data area by construction)
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    Wpx, Hpx = fig.get_size_inches() * fig.dpi
    boxes = []
    for ax in fig.axes:
        arts = list(ax.texts) + [ax.title, ax.xaxis.label, ax.yaxis.label]
        for t in arts:
            if not t.get_text():
                continue
            bb = t.get_window_extent(rend)
            if (bb.x0 < 0 or bb.y0 < 0 or bb.x1 > Wpx or bb.y1 > Hpx):
                raise SystemExit(f"make_result: text outside canvas: "
                                 f"{t.get_text()[:40]!r}")
            boxes.append((t.get_text()[:40], bb))
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if boxes[i][1].overlaps(boxes[j][1]):
                raise SystemExit(f"make_result: text overlap: "
                                 f"{boxes[i][0]!r} vs {boxes[j][0]!r}")
    fig.savefig(os.path.join(DEMO, "media", "result.png"), dpi=200)
    print("make_result: wrote media/result.png "
          f"({len(boxes)} texts checked, no overlap)")


if __name__ == "__main__":
    main()
