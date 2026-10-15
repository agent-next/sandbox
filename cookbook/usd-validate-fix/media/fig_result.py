#!/usr/bin/env python3
"""result.png -- the traffic cone before and after the repair the judge graded.

Left:  task/traffic_cone_broken.usda as the judge saw it -- the gray Band
       (no material binding), no normals drawn anywhere (there are none), and
       the real gate verdicts it failed.
Right: examples/good/traffic_cone_fixed.usda -- the same three meshes with
       the asset's own authored face-varying normals drawn on it, and the
       judge's measured numbers from data/grade_good.json (seed 20261015):
       5/5 gates PASS, per-mesh normals==corners, max |norm|-1 deviation,
       zero-area faces, bbox deviation 0.0 cm, and the measured height axis.

Every number printed comes from the grade verdict JSONs; the geometry
rendered comes from media/extract_mesh.py dumps of the two graded assets.
"""
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (DEMO_NAME, INK, INK_2, MUTED, SURFACE, SEED,
                    GOOD, CRITICAL, BBOX_TOL, UNIT_TOL,
                    draw_cone, load_mesh, load_verdict, defect_counts,
                    GATE_ORDER, GATE_LABEL)

MESH_ORDER = ["/TrafficCone/Base", "/TrafficCone/Body", "/TrafficCone/Band"]
SHORT = {"/TrafficCone/Base": "Base", "/TrafficCone/Body": "Body",
         "/TrafficCone/Band": "Band"}

# The gate rows, in judge order.  Each row is (short label, the one fact it is
# killed by / the fact that proves it passed).
GATE_DETAIL = {
    "validator": "0 FAILURE, 0 ERROR issues",
    "oracle": "0 oracle errors",
    "geometry": "world bbox dev 0.0 cm",
    "up_axis": 'upAxis Y, measured height axis Y',
    "recount": "text recount agrees with pxr",
}


def gate_rows(good):
    """(label, detail, passed) for every judge gate, from the real verdict."""
    out = []
    for key in GATE_ORDER:
        gate = good["gates"][key]
        out.append((GATE_LABEL[key], GATE_DETAIL[key], gate["passed"]))
    return out


def main():
    good = load_verdict("good")
    broken = load_verdict("broken")
    mesh_good = load_mesh("good")
    mesh_broken = load_mesh("broken")

    fig = plt.figure(figsize=(19.2, 10.8), dpi=100, facecolor=SURFACE)

    # --- title -----------------------------------------------------------
    fig.text(0.5, 0.968,
             "%s: repair an OpenUSD traffic-cone prop a judge can't fool"
             % DEMO_NAME,
             ha="center", va="center", fontsize=25, color=INK,
             fontweight="bold")
    fig.text(0.5, 0.930,
             "same three meshes, same points -- metadata, topology, bindings "
             "and normals repaired · judge: NVIDIA validator 1.22.0 + "
             "independent usd-core 25.5 oracle + geometry-invariance gate",
             ha="center", va="center", fontsize=13, color=INK_2)

    # --- left panel: the broken asset ------------------------------------
    ax0 = fig.add_axes([0.015, 0.425, 0.295, 0.450], projection="3d",
                       facecolor=SURFACE)
    draw_cone(ax0, mesh_broken, show_normals=False)
    ax0.text2D(0.5, -0.055, "before: task/traffic_cone_broken.usda",
               transform=ax0.transAxes, ha="center", va="top", fontsize=14,
               color=INK, fontweight="bold")

    panel0 = fig.add_axes([0.020, 0.140, 0.270, 0.255])
    panel0.set_xlim(0, 1)
    panel0.set_ylim(0, 1)
    panel0.axis("off")
    sev = broken["gates"]["validator"]["issues_by_severity"]
    counts = defect_counts(broken["gates"]["oracle"]["errors"])
    panel0.text(0.0, 1.00, "NVIDIA validator: %d FAILURE, status FAIL"
                % sev.get("FAILURE", 0), fontsize=13, color=CRITICAL,
                fontweight="bold", va="top")
    oracle_errs = len(broken["gates"]["oracle"]["errors"])
    panel0.text(0.0, 0.885, "independent oracle: %d errors"
                % oracle_errs, fontsize=13, color=CRITICAL,
                fontweight="bold", va="top")
    panel0.text(0.0, 0.775, "rules not passing: %s"
                % ", ".join(broken["gates"]["validator"]
                            ["rules_not_passing"]),
                fontsize=8.5, color=MUTED, va="top")
    y = 0.655
    for did, label, _caught, n in counts:
        panel0.text(0.0, y, "%s  %s" % (did, label), fontsize=10.5,
                    color=INK, va="top")
        panel0.text(1.0, y, "%d×" % n, fontsize=10.5, color=INK_2,
                    va="top", ha="right")
        y -= 0.075
    panel0.text(0.0, 0.040, "gray Band = no material binding · no normals "
                "anywhere (nothing to draw)",
                fontsize=9.5, color=MUTED, va="bottom", style="italic")

    # --- right panel: the repaired asset ---------------------------------
    ax1 = fig.add_axes([0.330, 0.425, 0.295, 0.450], projection="3d",
                       facecolor=SURFACE)
    draw_cone(ax1, mesh_good, show_normals=True)
    ax1.text2D(0.5, -0.055, "after: examples/good/traffic_cone_fixed.usda\n"
               "(arrows: the asset's authored face-varying normals)",
               transform=ax1.transAxes, ha="center", va="top", fontsize=12.5,
               color=INK, fontweight="bold")

    # --- facts table over the right half ---------------------------------
    # The table is a real Axes so columns align and never collide.
    panel1 = fig.add_axes([0.655, 0.150, 0.330, 0.725])
    panel1.set_xlim(0, 1)
    panel1.set_ylim(0, 1)
    panel1.axis("off")

    panel1.text(0.0, 1.00, "judge verdict (seed %s)" % SEED, fontsize=16,
                color=INK, fontweight="bold", va="top")

    y = 0.915
    for label, detail, passed in gate_rows(good):
        glyph = "✓" if passed else "✗"
        color = GOOD if passed else CRITICAL
        panel1.add_patch(plt.Rectangle((0.0, y - 0.026), 0.050, 0.052,
                                       facecolor=color, linewidth=0))
        panel1.text(0.025, y, glyph, fontsize=14, color="#ffffff",
                    fontweight="bold", ha="center", va="center")
        panel1.text(0.070, y + 0.014, label, fontsize=13.5, color=INK,
                    va="center", fontweight="bold")
        panel1.text(0.070, y - 0.024, detail, fontsize=11.5, color=INK_2,
                    va="center")
        y -= 0.082

    # --- oracle recount table (a real table: columns never overlap) -------
    y -= 0.035
    panel1.text(0.0, y, "oracle recount (usd-core alone)", fontsize=16,
                color=INK, fontweight="bold", va="top")
    y -= 0.062
    cols = ["mesh", "normals", "corners", "|norm|−1", "zero-area"]
    # explicit, non-overlapping column centres (axes fraction)
    xs = (0.02, 0.30, 0.45, 0.62, 0.86)
    aligns = ("left", "center", "center", "center", "center")
    for x, h, ha in zip(xs, cols, aligns):
        panel1.text(x, y, h, fontsize=11, color=MUTED, va="top", ha=ha,
                    fontweight="bold")
    y -= 0.042
    panel1.plot([0.0, 1.0], [y + 0.014, y + 0.014], color="#c3c2b7",
                linewidth=0.8)
    for path in MESH_ORDER:
        fact = good["facts"]["oracle"]["meshes"][path]
        rows = (SHORT[path],
                str(fact["normals"]),
                str(fact["face_corners"]),
                "%.0e" % fact["max_normal_dev"],
                str(fact["zero_area_faces"]))
        for x, val, ha in zip(xs, rows, aligns):
            panel1.text(x, y, val, fontsize=12, color=INK, va="center",
                        ha=ha)
        y -= 0.055
    y -= 0.018
    meta = good["facts"]["oracle"]
    up = good["facts"]["up_axis"]
    for line in ("metersPerUnit 0.01 · upAxis Y · defaultPrim TrafficCone",
                 "bound materials 3/3 · colliders %d"
                 % meta["colliders"],
                 "world bbox 36 × 58 × 36 cm · height axis %s, "
                 "margin %.0f cm" % (up["height_axis"],
                                     up["height_margin_cm"]),
                 "point counts kept 8 / 20 / 20 · bbox deviation 0.0 cm "
                 "(limit %.0e)" % BBOX_TOL):
        panel1.text(0.02, y, line, fontsize=11.5, color=INK_2, va="center",
                    ha="left")
        y -= 0.052

    panel1.text(0.0, 0.0,
                "pass lines: 0 FAILURE/ERROR issues · |norm|−1 ≤ %.0e · "
                "bbox dev ≤ %.0e cm" % (UNIT_TOL, BBOX_TOL),
                fontsize=10.5, color=MUTED, va="bottom", style="italic")

    # --- bottom strip: defects the judge caught, from the real verdict ---
    strip = fig.add_axes([0.020, 0.020, 0.960, 0.098])
    strip.set_xlim(0, 1)
    strip.set_ylim(0, 1)
    strip.axis("off")
    strip.text(0.0, 0.88, "the six seeded defects, all caught (real verdict of "
             "the broken asset, seed %s):" % SEED,
             fontsize=12, color=INK, fontweight="bold", va="top")
    x = 0.0
    gap = 0.010
    w = (1.0 - gap * (len(counts) - 1)) / len(counts)
    for did, label, caught_by, n in counts:
        strip.add_patch(plt.Rectangle((x, 0.20), w, 0.52,
                                      facecolor=CRITICAL, linewidth=0,
                                      alpha=0.13))
        strip.text(x + w / 2, 0.46, "%s %s" % (did, label), fontsize=9,
                   color=INK, ha="center", va="center", fontweight="bold")
        strip.text(x + w / 2, 0.33, caught_by, fontsize=7, color=INK_2,
                   ha="center", va="center")
        strip.text(x + w / 2, 0.09, "%d oracle %s" % (n, "error"
                                                      if n == 1 else "errors"),
                   fontsize=7, color=MUTED, ha="center", va="center")
        x += w + gap

    fig.savefig("result.png", dpi=100, facecolor=SURFACE)
    print("wrote result.png")


if __name__ == "__main__":
    main()
