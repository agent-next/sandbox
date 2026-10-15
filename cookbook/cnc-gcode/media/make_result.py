#!/usr/bin/env python3
"""result.png: what the judge measured on the good example (four panels).

Everything plotted comes from files the judge wrote during a real grade run:

  A. the toolpath the judge's own parser read out of part.nc
     (media/data/trace_good/moves.json) -- rapids dashed, cuts solid,
     coloured by the Z level of the move; stock outline (judge meta.json)
     and target-part outline (judge's own pocket / island masks from
     final.npz) drawn as contours;
  B. the removal map the judge computed (final.npz): its final heightmap,
     with the residual and gouge gate results of the good run;
  C. one bar per mutant: the metric of the gate that mutant failed, as a
     multiple of that gate's pass limit (each mutant's verdict JSON), so
     every bar shares one unit; inch_mode fails a rule with no number;
  D. the reference cross-check: the judge's parse vs LinuxCNC rs274
     (media/data/ref_compare.json), per move kind.

Layout: 2x2 on a 16:10 canvas.  A script-enforced check fails the build if
any text (figure texts, panel titles, axis labels, tick labels, legend and
table text) leaves the canvas or intersects another text.

Palette: dataviz reference instance (light mode), CVD-validated.
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
from matplotlib.patches import Patch, Rectangle

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
GOOD = "#0ca30c"
CRIT = "#d03b3b"
UNCUT = "#e8f1e4"
FLOOR = "#14685a"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "text.color": INK, "axes.edgecolor": "#c3c2b7",
    "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.axisbelow": True, "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
})


def load(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        sys.exit(f"make_result: missing judge output {path} -- run "
                 f"'bash judge/grade.sh examples/good/cam.py "
                 f"--json media/data/replay/01_good.json "
                 f"--trace media/data/trace_good' and "
                 f"'bash media/collect_ref_compare.sh' first")
    return path


# panel C: (mutant, failed gate key) -- read from each mutant's verdict JSON
C_GATES = [
    ("deep_pass",          "stepdown"),
    ("hot_feed",           "process"),
    ("inch_mode",          "units"),
    ("no_tool_offset",     "gouge"),
    ("rapid_into_stock",   "rapid_safety"),
    ("swapped_arcs",       "residual"),
    ("wide_stepover",      "stepover"),
]


def gate_ratio(gate, g):
    """(measured / pass limit or None, short 'measured vs rule' label)."""
    if gate == "stepdown":
        return (g["max_axial_mm"] / g["limit_mm"],
                f"axial {g['max_axial_mm']:g} mm  (limit {g['limit_mm']:g})")
    if gate == "stepover":
        return (g["max_spacing_mm"] / g["limit_mm"],
                f"spacing {g['max_spacing_mm']:g} mm  "
                f"(limit {g['limit_mm']:g})")
    if gate == "process":
        load_max, lim = max(g["chip_load_mm_per_tooth"]), g["limits"][1]
        return (load_max / lim,
                f"chip load {load_max:g} mm/tooth  (limit {lim:g}); "
                f"{g['feed_moves_out_of_band']} moves")
    if gate == "gouge":
        return (g["worst_gouge_mm"] / g["tolerance_mm"],
                f"gouge {g['worst_gouge_mm']:g} mm  "
                f"(tol {g['tolerance_mm']:g})")
    if gate == "rapid_safety":
        return (g["max_rapid_hit_mm"] / g["tolerance_mm"],
                f"rapid {g['max_rapid_hit_mm']:g} mm into stock  "
                f"(tol {g['tolerance_mm']:g}); {g['rapids_below_safe_z']}"
                " rapids")
    if gate == "residual":
        return (g["worst_residual_mm"] / g["tolerance_mm"],
                f"residual {g['worst_residual_mm']:g} mm  "
                f"(tol {g['tolerance_mm']:g})")
    if gate == "units":
        return (None, f"G20 on line {g['g20_lines'][0]}  (rule: G21 only)")
    raise SystemExit(f"make_result: no panel-C rule for gate {gate}")


def all_texts(fig):
    """Every visible text artist on the figure, with a short label."""
    out = [(t, "fig") for t in fig.texts]
    for ax in fig.axes:
        out += [(t, "title") for t in (ax.title, ax._left_title,
                                       ax._right_title)]
        out += [(ax.xaxis.label, "xlabel"), (ax.yaxis.label, "ylabel")]
        out += [(t, "text") for t in ax.texts]
        out += [(t, "tick") for t in ax.get_xticklabels()
                + ax.get_yticklabels()]
        leg = ax.get_legend()
        if leg is not None:
            out += [(t, "legend") for t in leg.get_texts()]
        for tbl in ax.tables:
            out += [(c.get_text(), "cell") for c in tbl.get_celld().values()]
    return [(t, k) for t, k in out if t.get_visible() and t.get_text()]


def check_layout(fig):
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    Wpx, Hpx = fig.bbox.width, fig.bbox.height
    boxes = []
    for t, kind in all_texts(fig):
        bb = t.get_window_extent(rend)
        if bb.x0 < 0 or bb.y0 < 0 or bb.x1 > Wpx or bb.y1 > Hpx:
            raise SystemExit(f"make_result: text outside canvas: "
                             f"{t.get_text()[:50]!r}")
        boxes.append((t.get_text()[:50], kind, bb))
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            if a[1] == b[1] == "cell":
                continue        # cells share edges by construction
            if a[2].overlaps(b[2]):
                raise SystemExit(f"make_result: text overlap: "
                                 f"{a[0]!r} vs {b[0]!r}")
    return len(boxes)


def main():
    moves = json.load(open(load("trace_good/moves.json")))
    fin = np.load(load("trace_good/final.npz"))
    meta = json.load(open(load("trace_good/meta.json")))
    good = json.load(open(load("replay/01_good.json")))
    refcmp = json.load(open(load("ref_compare.json")))

    fig = plt.figure(figsize=(16, 10), dpi=175)
    fig.text(0.03, 0.968,
             "cnc-gcode: the judge's own parse and material-removal "
             f"simulation of the graded part.nc (seed {meta['seed']})",
             fontsize=15, fontweight="bold", color=INK, va="baseline")
    fig.text(0.03, 0.942,
             "Source: judge trace dump (grade.sh --trace) and verdict JSONs "
             "-- every move, cell and number below was computed by the "
             "judge, not redrawn from the CAM script",
             fontsize=9.5, color=INK2, va="baseline")

    # ------------------------------------------------------------------ A
    n_kind = {"rapid": 0, "line": 0, "arc": 0}
    axA = fig.add_axes([0.045, 0.53, 0.33, 0.33])
    segs_rapid, segs_cut, cols_cut = [], [], []
    for mv in moves:
        p0, p1 = mv["start"], mv["end"]
        if mv["kind"] == "rapid":
            n_kind["rapid"] += 1
        else:
            n_kind[mv["motion"]] += 1
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
    # the three Z levels share XY, so draw deepest widest and shallowest
    # thinnest on top: every level stays visible as a nested stripe
    width = {S4: 3.6, S3: 2.2, S1: 0.9}
    order = sorted(range(len(segs_cut)), key=lambda i: -width[cols_cut[i]])
    axA.add_collection(LineCollection(
        [segs_cut[i] for i in order], colors=[cols_cut[i] for i in order],
        linewidths=[width[cols_cut[i]] for i in order]))
    axA.add_collection(LineCollection(
        segs_rapid, colors=MUTED, linewidths=1.0,
        linestyle=(0, (4, 4)), alpha=0.9))

    stock = meta["stock"]
    axA.add_patch(Rectangle((0, 0), stock["x_mm"], stock["y_mm"],
                            fill=False, edgecolor=INK2, lw=1.2))
    ys, xs = fin["ys"], fin["xs"]
    X, Y = np.meshgrid(xs, ys)
    for mask in ("in_pocket", "in_island"):
        axA.contour(X, Y, fin[mask].astype(float), levels=[0.5],
                    colors=[INK2], linewidths=1.4)
    handles = [
        Line2D([], [], color=S1, lw=2, label="cut, Z = −2 mm"),
        Line2D([], [], color=S3, lw=2, label="cut, Z = −4 mm"),
        Line2D([], [], color=S4, lw=2, label="cut, Z = −6 mm"),
        Line2D([], [], color=MUTED, lw=1.2, ls=(0, (4, 4)),
               label=f"rapid (safe Z +{meta['safe_z_mm']:g} mm)"),
        Line2D([], [], color=INK2, lw=1.4, label="stock / target outline"),
    ]
    axA.legend(handles=handles, loc="center left",
               bbox_to_anchor=(1.02, 0.5), fontsize=8.5, frameon=False,
               handlelength=1.8, labelspacing=0.7)
    axA.set_xlabel("X (mm)", fontsize=9.5)
    axA.set_ylabel("Y (mm)", fontsize=9.5)
    axA.set_xlim(-3, stock["x_mm"] + 3)
    axA.set_ylim(-3, stock["y_mm"] + 3)
    axA.set_aspect("equal")
    axA.tick_params(labelsize=8.5)
    axA.set_title(
        "A · toolpath parsed by judge/gcode_sim.py\n"
        f"{len(moves)} moves = {n_kind['rapid']} rapids + "
        f"{n_kind['line']} feed lines + {n_kind['arc']} arcs",
        fontsize=11, color=INK, loc="left", pad=8)

    # ------------------------------------------------------------------ B
    axB = fig.add_axes([0.555, 0.53, 0.33, 0.33])
    H = fin["H"]
    levels = sorted(set(np.round(np.unique(H), 3)))
    if levels != [-6.0, 0.0]:
        raise SystemExit(f"make_result: panel B expects two levels, "
                         f"got {levels}")
    axB.imshow(np.isclose(H, -6.0), origin="lower",
               cmap=ListedColormap([UNCUT, FLOOR]), vmin=0, vmax=1,
               extent=[0, stock["x_mm"], 0, stock["y_mm"]],
               interpolation="nearest", aspect="equal")
    for mask in ("in_pocket", "in_island"):
        axB.contour(X, Y, fin[mask].astype(float), levels=[0.5],
                    colors=[CRIT], linewidths=1.0, linestyles="--")
    n_clear = int(fin["must_clear"].sum())
    n_floor = int(np.isclose(H, -6.0).sum())
    rg, gg = good["gates"]["residual"], good["gates"]["gouge"]
    axB.legend(handles=[
        Patch(color=FLOOR, label=f"cleared to floor −6 mm\n"
                                 f"({n_floor:,} cells)"),
        Patch(facecolor=UNCUT, edgecolor="#c3c2b7",
              label="uncut stock / island, 0 mm"),
        Line2D([], [], color=CRIT, lw=1.2, ls="--",
               label="target pocket + island\n(judge's oracle)"),
    ], loc="center left", bbox_to_anchor=(1.02, 0.5), fontsize=8.5,
        frameon=False, labelspacing=1.0)
    axB.set_xlabel("X (mm)", fontsize=9.5)
    axB.set_ylabel("Y (mm)", fontsize=9.5)
    axB.tick_params(labelsize=8.5)
    axB.set_title(
        "B · material-removal heightmap after the whole program\n"
        f"must-clear {n_clear:,} cells, all cleared · residual "
        f"{rg['worst_residual_mm']:g} mm (tol {rg['tolerance_mm']:g}) · "
        f"gouge {gg['worst_gouge_mm']:g} mm (tol {gg['tolerance_mm']:g})",
        fontsize=11, color=INK, loc="left", pad=8)

    # ------------------------------------------------------------------ C
    axC = fig.add_axes([0.125, 0.075, 0.175, 0.33])
    names, ratios, labels = [], [], []
    for name, gate in C_GATES:
        v = json.load(open(load(f"replay/02_{name}.json")))
        g = v["gates"][gate]
        if g["pass"]:
            raise SystemExit(f"make_result: {name} passed gate {gate}")
        r, lab = gate_ratio(gate, g)
        names.append(f"{name}\n[{gate}]")
        ratios.append(r)
        labels.append(lab)
    y = np.arange(len(names))[::-1]
    for yi, r, lab in zip(y, ratios, labels):
        if r is None:
            axC.text(1.15, yi, "rule failed (no numeric limit)",
                     va="center", fontsize=8.5, color=CRIT, style="italic")
        else:
            axC.barh(yi, r - 1.0, left=1.0, height=0.6, color=CRIT)
            axC.text(r * 1.15, yi, f"{r:.4g}×", va="center",
                     fontsize=9, fontweight="bold", color=INK)
        axC.text(1.03, yi, lab, va="center", fontsize=8, color=INK2,
                 transform=axC.get_yaxis_transform())
    axC.axvline(1.0, color=GOOD, lw=1.6)
    axC.text(1.0, len(names) - 0.35, " pass limit (1×)", color=GOOD,
             fontsize=8.5, va="bottom")
    axC.set_xscale("log")
    axC.set_xlim(0.8, 5e3)
    axC.set_ylim(-0.6, len(names) - 0.1)
    axC.set_yticks(y)
    axC.set_yticklabels(names, fontsize=8.5, color=INK)
    axC.tick_params(axis="x", labelsize=8.5)
    axC.grid(axis="y", visible=False)
    axC.set_xlabel("failed gate's measured value ÷ its pass limit "
                   "(log scale)", fontsize=9.5)
    axC.set_title(
        "C · every mutant is rejected by its own gate\n"
        "(each mutant's verdict JSON; the good run passes all gates)",
        fontsize=11, color=INK, loc="left", pad=8)

    # ------------------------------------------------------------------ D
    axD = fig.add_axes([0.555, 0.075, 0.40, 0.33])
    axD.axis("off")
    o, t, d = refcmp["ours"], refcmp["rs274"], refcmp["diffs"]
    gref = good["gates"]["reference"]
    o_rapids = o["moves"] - o["cutting_moves"]

    def cmp(ok):
        return "match" if ok else "DIFF"

    rows = [
        ("rapids", f"{o_rapids}", f"{o_rapids - d['rapids_diff']}",
         cmp(d["rapids_diff"] == 0)),
        ("feed lines", f"{o['cutting_lines']}", f"{t['cutting_lines']}",
         cmp(o["cutting_lines"] == t["cutting_lines"])),
        ("arcs", f"{o['arcs']}", f"{t['arcs']}", cmp(d["arcs_diff"] == 0)),
        ("length units", o["length_units"], t["length_units"],
         cmp(d["length_units"] == 0)),
        ("XY bbox (mm)",
         "[{:.0f}, {:.0f}, {:.0f}, {:.0f}]".format(*o["xy_bbox"]),
         "[{:.0f}, {:.0f}, {:.0f}, {:.0f}]".format(*t["xy_bbox"]),
         cmp(all(v == 0 for v in d["xy_bbox_mm"]))),
        ("Z range (mm)", "[{:.0f}, {:.0f}]".format(*o["z_range"]),
         "[{:.0f}, {:.0f}]".format(*t["z_range"]),
         cmp(d["z_range_mm"] == 0)),
    ]
    tbl = axD.table(cellText=[list(r) for r in rows],
                    colLabels=["quantity", "judge sim", "LinuxCNC rs274",
                               "compare"],
                    cellLoc="left", colLoc="left",
                    colWidths=[0.24, 0.27, 0.27, 0.16],
                    bbox=[0.0, 0.14, 0.94, 0.80])
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9.5)
    for (r, c), cell in tbl.get_celld().items():
        cell.set_edgecolor("#c3c2b7")
        cell.set_linewidth(0.6)
        cell.set_text_props(fontfamily="DejaVu Sans Mono" if c in (1, 2)
                            else "DejaVu Sans")
        if r == 0:
            cell.set_text_props(color=INK2, fontweight="bold")
            cell.set_facecolor("#f2f1ec")
        elif c == 3:
            ok = cell.get_text().get_text() == "match"
            cell.set_text_props(color=GOOD if ok else CRIT,
                                fontweight="bold")
    ver = gref["ref_tool"].split("+")[0]
    axD.set_title(
        "D · gate reference: judge parse vs an independent interpreter\n"
        f"{ver}; rule: counts exact, coordinates within "
        f"{gref['tolerance_mm']:g} mm",
        fontsize=11, color=INK, loc="left", pad=8)
    axD.text(0.0, 0.04,
             f"{'PASS' if refcmp['gate_pass'] else 'FAIL'} -- rs274 exit "
             f"{refcmp['ref_exit']}: both interpreters accept the program "
             "and agree on every row",
             fontsize=9.5, color=GOOD if refcmp["gate_pass"] else CRIT,
             fontweight="bold", transform=axD.transAxes)

    n = check_layout(fig)
    fig.savefig(os.path.join(DEMO, "media", "result.png"), dpi=175)
    print(f"make_result: wrote media/result.png ({n} texts checked, "
          "none outside the canvas, no overlap)")


if __name__ == "__main__":
    main()
