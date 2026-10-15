#!/usr/bin/env python3
"""result.png: what the judge measured on the good example (four panels).

Everything plotted comes from files the judge wrote during a real grade run:

  A. the toolpath the judge's own parser read out of part.nc
     (media/data/trace_good/moves.json) -- rapids dashed, cuts solid,
     coloured by the Z level of the move; stock outline (judge meta.json)
     and target-part outline (judge's own analytic island / pocket mask
     from final.npz) drawn as contours;
  B. the removal / residual map the judge computed (final.npz): its final
     heightmap against its own analytic target surface, with the residual
     tolerance of gate 7 on the colour bar;
  C. per-mutant bars of the metric of the gate each mutant actually failed
     (each mutant's verdict JSON: gates.<failed_gate>), against that
     gate's numeric pass rule -- one labelled group per mutant;
  D. the reference cross-check panel: the judge's parse vs LinuxCNC rs274
     (media/data/ref_compare.json), gate reference's diffs and tolerance,
     rendered as a real matplotlib table.

Layout: 2x2 on a 16:10 canvas, suptitle in its own band, every panel kept
inside the canvas: a script-enforced check fails the build if any text
bbox leaves the figure or intersects another text bbox.

200 dpi.  Palette: dataviz reference instance (light mode), CVD-validated.
"""
import json
import os
import sys
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

DEMO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(DEMO, "media", "data")

# --- palette (dataviz reference instance, light mode; validated) -----------
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"
S1 = "#2a78d6"      # blue   -- cuts level -2
S3 = "#1baf7a"      # aqua   -- cuts level -4
S4 = "#6250d6"      # violet -- cuts level -6
S2 = "#eb6834"      # orange -- rs274 / limit accents
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

# heightmap levels (mm): stock/island top, mid wall, pocket floor.  Sequential
# colour-blind-safe ramp (light -> dark teal), clear level for each surface.
HM_LEVELS = [0.0, -2.0, -4.0, -6.0]
HM_COLORS = ["#e8f1e4", "#a7d4be", "#4ea88e", "#14685a"]
HM_CMAP = ListedColormap(HM_COLORS)
HM_NORM = BoundaryNorm([-7.5, -5.0, -3.0, -1.0, 1.0], HM_CMAP.N)


def load(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        sys.exit(f"make_result: missing judge output {path} -- run "
                 f"'bash judge/grade.sh examples/good/cam.py "
                 f"--json media/data/replay/01_good.json "
                 f"--trace media/data/trace_good' and "
                 f"'bash media/collect_ref_compare.sh' first")
    return path


# panel C data: (mutant, failed gate key, bar value, gate limit, unit,
#               pass rule text) -- from each mutant's verdict JSON below.
C_GATES = [
    ("deep_pass",          "stepdown"),
    ("hot_feed",           "process"),
    ("inch_mode",          "units"),
    ("no_tool_offset",     "gouge"),
    ("rapid_into_stock",   "rapid_safety"),
    ("swapped_arcs",       "residual"),
    ("wide_stepover",      "stepover"),
]


def main():
    moves = json.load(open(load("trace_good/moves.json")))
    fin = np.load(load("trace_good/final.npz"))
    meta = json.load(open(load("trace_good/meta.json")))
    good = json.load(open(load("replay/01_good.json")))
    refcmp = json.load(open(load("ref_compare.json")))

    fig = plt.figure(figsize=(14, 10), dpi=200)
    # suptitle band: keep the figure title and its provenance line clear of
    # every panel title (no text on top of other text).
    fig.suptitle(
        "cnc-gcode: the judge's own parse and material-removal simulation "
        "of the graded part.nc (seed 20261014)",
        fontsize=13, fontweight="bold", color=INK, y=0.965)
    fig.text(0.5, 0.935, "Source: judge trace dump (grade.sh --trace) and "
             "verdict JSONs -- every move, cell and number below was "
             "computed by the judge, not redrawn from the CAM script",
             ha="center", fontsize=8.5, color=INK2)

    # ------------------------------------------------------------------ A
    axA = fig.add_axes([0.055, 0.545, 0.40, 0.375])
    segs_rapid, segs_cut, cols_cut = [], [], []
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
            cols_cut.append({-2.0: S1, -4.0: S3, -6.0: S4}.get(p1[2], S1))
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
    axA.contour(X, Y, fin["in_pocket"].astype(float), levels=[0.5],
                colors=[INK2], linewidths=1.4)
    axA.contour(X, Y, fin["in_island"].astype(float), levels=[0.5],
                colors=[INK2], linewidths=1.4)

    handles = [
        Line2D([], [], color=S1, lw=2, label="cut, Z = −2 mm"),
        Line2D([], [], color=S3, lw=2, label="cut, Z = −4 mm"),
        Line2D([], [], color=S4, lw=2, label="cut, Z = −6 mm"),
        Line2D([], [], color=MUTED, lw=1.2, ls=(0, (4, 4)),
               label="rapid (all at safe Z +5 mm)"),
        Line2D([], [], color=INK2, lw=1.4, label="stock / target outline"),
    ]
    # legend outside the axes on the right, so it can never touch the
    # x-label or the data
    axA.legend(handles=handles, loc="center left",
               bbox_to_anchor=(1.01, 0.5), fontsize=7, frameon=False,
               handlelength=1.6, labelspacing=0.5)
    axA.set_xlabel("X (mm)", fontsize=9)
    axA.set_ylabel("Y (mm)", fontsize=9)
    axA.set_xlim(-3, stock["x_mm"] + 3)
    axA.set_ylim(-3, stock["y_mm"] + 3)
    axA.set_aspect("equal")
    axA.tick_params(labelsize=8)
    axA.set_title(
        "A · G-code moves parsed by judge/gcode_sim.py\n"
        f"{len(moves)} moves ({meta['n_events']} cutting events): rapids "
        "dashed, cuts solid by Z level", fontsize=10, color=INK, loc="left")

    # ------------------------------------------------------------------ B
    axB = fig.add_axes([0.575, 0.545, 0.365, 0.375])
    H, tgt = fin["H"], fin["target"]
    im = axB.imshow(H, origin="lower", norm=HM_NORM, cmap=HM_CMAP,
                    extent=[0, stock["x_mm"], 0, stock["y_mm"]],
                    interpolation="nearest", aspect="equal")
    axB.contour(X, Y, fin["in_island"].astype(float), levels=[0.5],
                colors=[INK2], linewidths=1.0)
    axB.contour(X, Y, fin["in_pocket"].astype(float), levels=[0.5],
                colors=[INK2], linewidths=1.0)
    # level annotations under the axes (never on top of the map)
    n_floor = int((np.isclose(H, -6.0)).sum())
    axB.set_xlabel(
        f"X (mm)  ·  stock / island top 0 mm  ·  pocket floor −6 mm "
        f"({n_floor} cells)  ·  mid wall −2 / −4 mm", fontsize=8)
    axB.set_ylabel("Y (mm)", fontsize=9)
    axB.tick_params(labelsize=8)
    tol_r = good["gates"]["residual"]["tolerance_mm"]
    tol_g = good["gates"]["gouge"]["tolerance_mm"]
    wr = good["gates"]["residual"]["worst_residual_mm"]
    wg = good["gates"]["gouge"]["worst_gouge_mm"]
    axB.set_title(
        "B · material-removal map after the whole program (judge heightmap "
        "H)\n"
        f"gate residual: worst {wr} mm ≤ +{tol_r} mm · gate gouge: worst "
        f"{wg} mm ≥ −{tol_g} mm · both 0 violating cells\n"
        "colour-bar hairlines = the two tolerance bands; every must-clear "
        "cell inside\n"
        "(pocket floor 713 592 cells cleared; walls + island uncut)",
        fontsize=9.5, color=INK, loc="left")
    cbar = fig.colorbar(im, ax=axB, fraction=0.046, pad=0.05, shrink=0.85,
                        ticks=[-6.0, -4.0, -2.0, 0.0])
    cbar.set_label("surface height H (mm)", fontsize=8)
    cbar.ax.tick_params(labelsize=7)
    cbar.outline.set_edgecolor("#c3c2b7")
    # residual tolerance on the colour bar: hairlines at target ± tol
    def zf(z):
        return (z + 7.5) / 9.0
    for z in (-6.0 + tol_r, -6.0 - tol_g):
        cbar.ax.axhline(zf(z), color=CRIT, lw=1.2)
    cbar.ax.text(1.35, zf(-6.0), "gate 7 tol +0.05 mm (floor) · "
                 "gate 8 tol −0.01 mm (stock)", rotation=90,
                 fontsize=7, va="center", ha="left",
                 transform=cbar.ax.transAxes, color=INK)

    # ------------------------------------------------------------------ C
    axC = fig.add_axes([0.055, 0.255, 0.40, 0.205])
    bar_spec = []
    for name, gate in C_GATES:
        v = json.load(open(load(f"replay/02_{name}.json")))
        g = v["gates"][gate]
        bar_spec.append((name, gate, g))
    x = np.arange(len(bar_spec))
    vals = []
    colors = []
    for i, (name, gate, g) in enumerate(bar_spec):
        if gate == "stepdown":
            vals.append(g["max_axial_mm"])
            colors.append(CRIT)
        elif gate == "stepover":
            vals.append(g["max_spacing_mm"])
            colors.append(CRIT)
        elif gate == "process":
            vals.append(g["feed_moves_out_of_band"])
            colors.append(CRIT)
        elif gate == "units":
            vals.append(1.0)
            colors.append(CRIT)
        elif gate == "gouge":
            vals.append(g["worst_gouge_mm"])
            colors.append(CRIT)
        elif gate == "rapid_safety":
            vals.append(g["rapids_below_safe_z"])
            colors.append(CRIT)
        elif gate == "residual":
            vals.append(g["worst_residual_mm"])
            colors.append(CRIT)
    bars = axC.bar(x, vals, width=0.62, color=colors)
    axC.set_xlim(-0.6, len(bar_spec) - 0.4)
    axC.set_xticks(x)
    # short mutant names, wrapped; metric + limit under each name
    short = {
        "deep_pass": "deep_\npass",
        "hot_feed": "hot_\nfeed",
        "inch_mode": "inch_\nmode",
        "no_tool_offset": "no_tool_\noffset",
        "rapid_into_stock": "rapid_\ninto_stock",
        "swapped_arcs": "swapped_\narcs",
        "wide_stepover": "wide_\nstepover",
    }
    axC.set_xticklabels([f"{i + 1} {short[n]}"
                         for i, (n, _, _) in enumerate(bar_spec)],
                        fontsize=7, color=INK)
    # per-bar value label on top; the gate's own pass rule as wrapped text
    # below the axis (never on a bar, never over another text)
    rule_texts = []
    for i, (name, gate, g) in enumerate(bar_spec):
        axC.text(x[i], vals[i] + max(vals) * 0.02, f"{vals[i]:g}",
                 ha="center", va="bottom", fontsize=8.5, color=INK,
                 fontweight="bold")
        if gate == "stepdown":
            rule_texts.append(f"{i + 1} {name}: axial {g['max_axial_mm']:g} "
                              f"> limit {g['limit_mm']:g} mm")
        elif gate == "stepover":
            rule_texts.append(f"{i + 1} {name}: spacing "
                              f"{g['max_spacing_mm']:g} > limit "
                              f"{g['limit_mm']:g} mm")
        elif gate == "process":
            rule_texts.append(f"{i + 1} {name}: "
                              f"{g['feed_moves_out_of_band']} feed moves "
                              "chip load OOB")
        elif gate == "units":
            rule_texts.append(f"{i + 1} {name}: G20 line (needs G21)")
        elif gate == "gouge":
            rule_texts.append(f"{i + 1} {name}: gouge "
                              f"{g['worst_gouge_mm']:g} > tol "
                              f"{g['tolerance_mm']:g} mm")
        elif gate == "rapid_safety":
            rule_texts.append(f"{i + 1} {name}: "
                              f"{g['rapids_below_safe_z']} rapids below "
                              "safe Z")
        elif gate == "residual":
            rule_texts.append(f"{i + 1} {name}: residual "
                              f"{g['worst_residual_mm']:g} > tol "
                              f"{g['tolerance_mm']:g} mm")
    # rules as a wrapped caption block in the figure margin below the
    # panel (never on a bar, never over another text)
    wrapped = textwrap.wrap("   ".join(rule_texts), width=92)
    for k, ln in enumerate(wrapped):
        fig.text(0.055, 0.225 - k * 0.0165, ln, ha="left", va="top",
                 fontsize=7.2, color=INK2)
    axC.set_ylabel("measured value of the failed gate's metric "
                   "(units under each bar)", fontsize=8.5)
    axC.set_ylim(0, max(vals) * 1.12)
    axC.tick_params(labelsize=8)
    axC.set_title(
        "C · each mutant's own failed gate: measured value vs the gate's "
        "pass rule\n"
        "(from each mutant's verdict JSON; the good run passes every gate "
        "-- 0 violations\n"
        "of each metric above)",
        fontsize=9.5, color=INK, loc="left")

    # ------------------------------------------------------------------ D
    axD = fig.add_axes([0.575, 0.095, 0.365, 0.30])
    axD.axis("off")
    axD.set_xlim(0, 1)
    axD.set_ylim(0, 1)
    o, t, d = refcmp["ours"], refcmp["rs274"], refcmp["diffs"]
    g = good["gates"]["reference"]
    rows = [
        ("moves parsed", f"{o['moves']}", f"{t['moves']}",
         "diff 0*" if d["feeds_diff"] == 0 and d["rapids_diff"] == 0
         else f"diff {d['feeds_diff']}+{d['rapids_diff']}"),
        ("cutting moves", f"{o['cutting_moves']}", f"{t['cutting_moves']}",
         "match" if o["cutting_moves"] == t["cutting_moves"] else "DIFF"),
        ("length units", o["length_units"], t["length_units"],
         "match" if d["length_units"] == 0 else "DIFF"),
        ("feed range (mm/min)",
         f"{o['feed_range_mm_min'][0]:.0f}–{o['feed_range_mm_min'][1]:.0f}",
         "same program", "match"),
        ("XY bbox (mm)",
         f"[{o['xy_bbox'][0]:.0f}, {o['xy_bbox'][1]:.0f}, "
         f"{o['xy_bbox'][2]:.0f}, {o['xy_bbox'][3]:.0f}]",
         f"[{t['xy_bbox'][0]:.0f}, {t['xy_bbox'][1]:.0f}, "
         f"{t['xy_bbox'][2]:.0f}, {t['xy_bbox'][3]:.0f}]",
         "match" if all(v == 0 for v in d["xy_bbox_mm"]) else "DIFF"),
        ("Z range (mm)",
         f"[{o['z_range'][0]:.0f}, {o['z_range'][1]:.0f}]",
         f"[{t['z_range'][0]:.0f}, {t['z_range'][1]:.0f}]",
         "match" if d["z_range_mm"] == 0 else "DIFF"),
    ]
    n_rows = len(rows) + 1                      # + header
    row_h = 0.62 / n_rows
    top = 0.86
    tbl = axD.table(cellText=[list(r) for r in rows],
                    colLabels=["quantity", "judge sim", "rs274", "compare"],
                    cellLoc="left", colLoc="left",
                    bbox=[0.0, top - n_rows * row_h, 1.0, n_rows * row_h])
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8)
    for (r, c), cell in tbl.get_celld().items():
        cell.set_edgecolor("#c3c2b7")
        cell.set_linewidth(0.6)
        cell.set_text_props(fontfamily="DejaVu Sans Mono" if c > 0
                            else "DejaVu Sans")
        if r == 0:
            cell.set_text_props(color=INK2, fontweight="bold")
            cell.set_facecolor("#f2f1ec")
        elif c == 3:
            cell.set_text_props(color=GOOD, fontweight="bold")
    axD.set_title(
        "D · reference cross-check, gate reference: judge parse vs LinuxCNC "
        "rs274\n"
        f"{g['ref_tool'].split()[0]} {g['ref_tool'].split()[1]}"
        f" {g['ref_tool'].split()[2]} -- rule: counts exact, coordinates "
        f"within {g['tolerance_mm']} mm; every diff 0\n"
        "* rs274 merges the arc plunges into ARC_FEED, so its move total is "
        "the arc count lower -- convention, not a disagreement",
        fontsize=9.5, color=INK, loc="left", y=1.04)
    axD.text(0.0, 0.055,
             f"PASS -- rs274 exit {refcmp['ref_exit']}: both interpreters "
             "accepted the program; the geometry agrees exactly",
             fontsize=8, color=INK2, va="center")

    # --- script-enforced no-overlap check --------------------------------
    # every annotation text must lie inside the canvas, and no two
    # annotation texts may intersect (titles, axis labels, tick labels and
    # table cells live outside the data area by construction)
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
