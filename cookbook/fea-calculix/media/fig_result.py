#!/usr/bin/env python3
"""result.png -- the real CalculiX result for the good artifact.

Panel A: deformed mesh (displacements from work/good-fine/job.frd, scaled
         by the printed factor) coloured by von Mises from the same .frd;
         the allowable stress is marked on the colour bar (spec_limits
         gate).  Panel B: the measured relative change between mesh s and
         s/2 against the 2% gate limit (convergence gate).  Panel C: the
         reference-beam FEA/EB ratios with the +-3% verification band.

Every number is read from media/data/verdicts/good.json or a real job.frd
in media/work/; the script exits non-zero if any source file is missing,
and if any placed text escapes its axes or overlaps another text.
"""
import json
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PolyCollection
from matplotlib import cm, colors

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import beamviz

MEDIA = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(MEDIA, "result.png")

# colour-blind-safe sequential map
CMAP = "viridis"
ALLOW = 250.0 / 1.5


def need(p):
    if not os.path.exists(p):
        raise SystemExit(f"missing {p} -- run the judge collection first")
    return p


def check_layout(fig, items):
    """Fail if any registered text escapes its axes or overlaps another.

    items: (artist, ax_or_None, tag); ax=None means pairwise-only (the
    artist legitimately lives outside any axes, e.g. titles)."""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    boxes = []
    for art, ax, tag in items:
        bb = art.get_window_extent(renderer=r)
        if ax is not None:
            ab = ax.get_window_extent(renderer=r)
            if bb.x0 < ab.x0 - 1 or bb.x1 > ab.x1 + 1 or \
                    bb.y0 < ab.y0 - 1 or bb.y1 > ab.y1 + 1:
                raise SystemExit(
                    f"text '{tag}' escapes its axes: "
                    f"text=({bb.x0:.0f},{bb.y0:.0f})-({bb.x1:.0f},{bb.y1:.0f}) "
                    f"axes=({ab.x0:.0f},{ab.y0:.0f})-({ab.x1:.0f},{ab.y1:.0f})")
        boxes.append((bb, tag))
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if boxes[i][0].overlaps(boxes[j][0]):
                raise SystemExit(
                    f"text overlap: {boxes[i][1]} vs {boxes[j][1]}")
    print(f"layout check: OK ({len(boxes)} texts inside axes, "
          "no pairwise overlaps)")


def main():
    verdict = json.load(open(need(os.path.join(
        MEDIA, "data", "verdicts", "good.json"))))
    conv = json.load(open(need(os.path.join(
        MEDIA, "data", "convergence.json"))))
    f = beamviz.load_fields("good-fine")

    m = verdict["metrics"]
    L, b, h = m["L_mm"], m["b_mm"], m["h_mm"]

    fig = plt.figure(figsize=(15.5, 5.4), dpi=200)
    gs = fig.add_gridspec(1, 3, width_ratios=[2.6, 1.0, 1.0],
                          left=0.035, right=0.985, top=0.80,
                          bottom=0.16, wspace=0.30)
    texts = []   # (artist, ax|None, tag) for the layout check

    def reg(art, ax, tag):
        texts.append((art, ax, tag))
        return art

    # ------------------------------------------------------------------
    # panel A: deformed mesh coloured by von Mises (.frd data)
    axA = fig.add_subplot(gs[0])
    coords, disp, vm, conn = f["coords"], f["disp"], f["vm"], f["conn"]
    scale = 20.0                      # visual amplification, printed on fig
    # saturate the colour map just above the allowable so the wall-corner
    # singularity (excluded from the measured sigma_wall, see SPEC.md)
    # does not wash out the gradient along the beam
    norm = colors.Normalize(vmin=0.0, vmax=1.15 * ALLOW)

    faces = beamviz.boundary_faces(conn)
    defo = coords + scale * disp
    fxyz = defo[faces]                                # (K,4,3)
    verts, order = beamviz.face_draw_order(fxyz, elev_deg=14, azim_deg=75)
    fvm = np.nan_to_num(vm[faces].mean(axis=1), nan=0.0)[order]
    coll = PolyCollection(verts, array=fvm, cmap=CMAP, norm=norm,
                          edgecolors="none", antialiased=False)
    axA.add_collection(coll)
    axA.set_aspect("equal")
    x2, y2 = verts[..., 0], verts[..., 1]
    pad = 0.03 * L
    axA.set_xlim(x2.min() - pad, x2.max() + pad)
    axA.set_ylim(y2.min() - 3.2 * pad, y2.max() + 3.2 * pad)
    axA.axis("off")

    # undeformed beam: silhouette outline of the undeformed box under the
    # same projection -- a straight horizontal outline at its true
    # position, not a wireframe cuboid
    hull = beamviz.undeformed_outline(
        axA, (0, 0, 0), (L, b, h), 14, 75,
        color="0.45", lw=0.9, ls=(0, (4, 3)), zorder=9)
    # label centred on the silhouette's long top edge, in the free space
    # above the deflected mesh
    nxt = np.roll(hull, -1, axis=0)
    lens = np.linalg.norm(nxt - hull, axis=1)
    k = int(np.argmax((hull[:, 1] + nxt[:, 1])
                      * (lens > 0.5 * lens.max())))
    mid = (hull[k] + nxt[k]) / 2
    reg(axA.annotate("undeformed", mid, textcoords="offset points",
                     xytext=(0, 6), ha="center", va="bottom",
                     fontsize=8, color="0.35"),
        axA, "undeformed label")

    cb = fig.colorbar(cm.ScalarMappable(norm=norm, cmap=CMAP), ax=axA,
                      fraction=0.025, pad=0.02, extend="max")
    cb.ax.axhline(ALLOW, color="red", lw=2.0)
    cb.set_label("von Mises stress [MPa] (ccx .frd, nodal) -- "
                 f"red line: allowable {ALLOW:.1f} = 250/1.5",
                 fontsize=8.5)
    cb.ax.tick_params(labelsize=8)

    reg(axA.set_title("spec_limits gate -- deformed mesh, von Mises stress "
                      f"(displacements x{scale:g}, linear static)",
                      fontsize=9.5, loc="left"), None, "title A")
    reg(axA.annotate(
        f"measured sigma_wall = {m['sigma_mpa']:.1f} MPa <= {ALLOW:.1f} "
        f"-> PASS\n"
        f"tip deflection = {m['delta_mm']:.2f} mm <= L/100 = "
        f"{L/100:.2f} mm -> PASS\n"
        f"design {L:.0f} x {b:.0f} x {h:.0f} mm, "
        f"mass {m['mass_g']:.0f} g | P = 1000 N at tip\n"
        f"fine mesh {m['fine_elems']} elements (mesh_size/2 = "
        f"{m['mesh_size_mm']/2:g} mm)",
        xy=(0.01, 0.02), xycoords="axes fraction", fontsize=8.3,
        ha="left", va="bottom",
        bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="0.6",
                  alpha=0.9)), axA, "metrics box")
    reg(axA.annotate("note: colour saturates above "
                     f"{1.15*ALLOW:.0f} MPa; the clamped-face corner is\n"
                     "a point singularity and is excluded from sigma_wall "
                     "by the judge (SPEC.md)",
                     xy=(0.99, 0.98), xycoords="axes fraction", fontsize=7.3,
                     ha="right", va="top", color="0.35",
                     bbox=dict(boxstyle="round,pad=0.25", fc="white",
                               ec="none", alpha=0.75)),
        axA, "saturation note")

    # ------------------------------------------------------------------
    # panel B: convergence -- measured relative change vs the 2% limit
    axB = fig.add_subplot(gs[1])
    meshes = conv["meshes"]                       # coarse then fine
    chg = [conv["delta_change_pct"], conv["sigma_change_pct"]]
    xb = np.arange(2)
    axB.bar(xb, chg, 0.5, color=["tab:blue", "tab:orange"], zorder=3)
    for xi, v_ in zip(xb, chg):
        reg(axB.annotate(f"{v_:.2f}%", (xi, v_),
                         textcoords="offset points", xytext=(0, 5),
                         ha="center", va="bottom", fontsize=9,
                         fontweight="bold"),
            axB, f"conv value {xi}")
    axB.axhline(2.0, color="red", lw=1.4, ls="--", zorder=2)
    reg(axB.annotate("gate limit 2%", (1.55, 2.0),
                     textcoords="offset points", xytext=(0, 4),
                     ha="right", va="bottom", fontsize=8, color="red"),
        axB, "conv limit label")
    axB.set_xlim(-0.6, 1.6)
    axB.set_ylim(0.0, 3.0)
    axB.set_ylabel("relative change s -> s/2 [%]", fontsize=9)
    axB.tick_params(axis="y", labelsize=8)
    axB.set_xticks(xb)
    axB.set_xticklabels(
        [f"tip deflection\n{meshes[0]['delta_mm']:.4f} -> "
         f"{meshes[1]['delta_mm']:.4f} mm",
         f"wall stress\n{meshes[0]['sigma_mpa']:.1f} -> "
         f"{meshes[1]['sigma_mpa']:.1f} MPa"], fontsize=8)
    axB.set_xlabel(f"mesh {meshes[0]['mesh_mm']:g} -> "
                   f"{meshes[1]['mesh_mm']:g} mm ({meshes[0]['elems']} -> "
                   f"{meshes[1]['elems']} elements)", fontsize=8.5)
    reg(axB.set_title("convergence gate -- s vs s/2 <= 2%\n"
                      f"measured d={conv['delta_change_pct']:.2f}% "
                      f"s={conv['sigma_change_pct']:.2f}% -> PASS",
                      fontsize=9.5, loc="left"), None, "title B")

    # ------------------------------------------------------------------
    # panel C: verification -- FEA vs Euler-Bernoulli on the reference beam
    axC = fig.add_subplot(gs[2])
    det = verdict["gates"]["verification"]["detail"]
    p = re.search(r"deflection ([\d.]+) vs ([\d.]+) mm \(([+-][\d.]+)%\), "
                  r"stress ([\d.]+) vs ([\d.]+) MPa \(([+-][\d.]+)%\)", det)
    if not p:
        raise SystemExit("cannot parse verification detail")
    fea_d, eb_d, err_d = float(p.group(1)), float(p.group(2)), float(p.group(3))
    fea_s, eb_s, err_s = float(p.group(4)), float(p.group(5)), float(p.group(6))

    cats = ["tip deflection\n[mm]", "wall stress\n[MPa]"]
    x = np.arange(2)
    w = 0.34
    r_d, r_s = fea_d / eb_d, fea_s / eb_s
    axC.axhspan(0.97, 1.03, color="green", alpha=0.10)
    axC.axhline(1.03, color="red", lw=1.4, ls="--")
    axC.axhline(0.97, color="red", lw=1.4, ls="--")
    axC.axhline(1.0, color="0.5", lw=0.9)
    axC.bar(x - w / 2, [r_d, r_s], w, color="tab:blue")
    axC.bar(x + w / 2, [1.0, 1.0], w, color="0.65")
    for xi, e, fea, ebv, unit in (
            (0, err_d, fea_d, eb_d, "mm"),
            (1, err_s, fea_s, eb_s, "MPa")):
        reg(axC.annotate(f"{fea:g} vs {ebv:g} {unit}\n{e:+.2f}%",
                         (xi, 1.048), ha="center", va="bottom",
                         fontsize=7.5), axC, f"verif label {xi}")
    axC.set_xticks(x)
    axC.set_xticklabels(cats, fontsize=9)
    axC.set_ylabel("FEA / Euler-Bernoulli ratio", fontsize=9)
    axC.set_ylim(0.90, 1.12)
    axC.tick_params(axis="y", labelsize=8)
    axC.set_xlabel("blue: ccx reference beam   grey: Euler-Bernoulli",
                   fontsize=7.5)
    reg(axC.set_title("verification gate -- reference beam vs\n"
                      "Euler-Bernoulli within 3% (red dashed)\n"
                      f"measured {err_d:+.2f}% / {err_s:+.2f}% -> PASS",
                      fontsize=9.5, loc="left"), None, "title C")

    sup = fig.suptitle(
        "fea-calculix: cantilever 1000x12x60 mm, 1000 N tip load "
        "-- good artifact, grade.sh --seed 42 verdict PASS "
        "(real ccx 2.20 / gmsh 4.10.0 run)",
        fontsize=10.5, x=0.035, ha="left")
    reg(sup, None, "suptitle")
    fig.text(0.035, 0.015,
             "Sources: media/data/verdicts/good.json; media/work/good-fine/"
             "job.frd + media/work/good-coarse/job.frd (parsed with the "
             "judge's own .frd reader). No analytically recomputed stress "
             "is plotted.",
             fontsize=7.5, color="0.35")

    check_layout(fig, texts)
    fig.savefig(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
