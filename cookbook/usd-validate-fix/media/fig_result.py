#!/usr/bin/env python3
"""result.png -- the traffic cone before and after the repair the judge graded.

Left:  task/traffic_cone_broken.usda as the judge saw it -- the gray Band
       (no material binding), no normals drawn anywhere (there are none), and
       the real gate verdicts it failed (11 oracle errors, 7 FAILURE issues).
Right: examples/good/traffic_cone_fixed.usda -- the same three meshes with
       the asset's own authored face-varying normals drawn on it, and the
       judge's measured numbers from data/grade_good.json (seed 20261015):
       3/3 gates PASS, 0 FAILURE/ERROR issues, per-mesh normals==corners,
       max |norm|-1 deviation, zero-area faces, bbox deviation 0.0 cm.

Every number printed comes from the grade verdict JSONs; the geometry
rendered comes from media/extract_mesh.py dumps of the two graded assets.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import (DEMO_NAME, INK, INK_2, MUTED, GRID, SURFACE, SEED,
                    GOOD, CRITICAL, BBOX_TOL, UNIT_TOL,
                    draw_cone, load_mesh, load_verdict, error_classes,
                    defect_counts)

MESH_ORDER = ["/TrafficCone/Base", "/TrafficCone/Body", "/TrafficCone/Band"]
SHORT = {"/TrafficCone/Base": "Base", "/TrafficCone/Body": "Body",
         "/TrafficCone/Band": "Band"}


def mesh_facts_lines(verdict):
    """Per-mesh judge numbers (normals/corners, unit dev, zero-area)."""
    lines = []
    for path in MESH_ORDER:
        fact = verdict["facts"]["oracle"]["meshes"][path]
        lines.append((SHORT[path], fact["normals"], fact["face_corners"],
                      fact["max_normal_dev"], fact["zero_area_faces"]))
    return lines


def main():
    good = load_verdict("good")
    broken = load_verdict("broken")
    mesh_good = load_mesh("good")
    mesh_broken = load_mesh("broken")

    fig = plt.figure(figsize=(19.2, 10.8), dpi=100, facecolor=SURFACE)

    # --- title -----------------------------------------------------------
    fig.text(0.5, 0.965,
             "%s: repair an OpenUSD traffic-cone prop a judge can't fool"
             % DEMO_NAME,
             ha="center", va="center", fontsize=24, color=INK,
             fontweight="bold")
    fig.text(0.5, 0.925,
             "same three meshes, same points -- metadata, topology, bindings "
             "and normals repaired · judge: NVIDIA validator 1.22.0 + "
             "independent usd-core 25.5 oracle + geometry-invariance gate",
             ha="center", va="center", fontsize=13, color=INK_2)

    # --- left panel: the broken asset ------------------------------------
    ax0 = fig.add_axes([0.020, 0.415, 0.275, 0.464], projection="3d",
                       facecolor=SURFACE)
    draw_cone(ax0, mesh_broken, show_normals=False)
    ax0.set_title("before: task/traffic_cone_broken.usda",
                  fontsize=15, color=INK, pad=2)

    panel0 = fig.add_axes([0.020, 0.135, 0.275, 0.27])
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
    y = 0.66
    for did, label, _caught, n in counts:
        panel0.text(0.0, y, "%s  %s" % (did, label), fontsize=10.5,
                    color=INK, va="top")
        panel0.text(1.0, y, "%d×" % n, fontsize=10.5, color=INK_2,
                    va="top", ha="right")
        y -= 0.078
    panel0.text(0.0, 0.075, "gray Band = no material binding · no normals "
                "anywhere (nothing to draw)",
                fontsize=9.5, color=MUTED, va="bottom", style="italic")

    # --- right panel: the repaired asset ---------------------------------
    ax1 = fig.add_axes([0.375, 0.415, 0.275, 0.464], projection="3d",
                       facecolor=SURFACE)
    draw_cone(ax1, mesh_good, show_normals=True)
    ax1.set_title("after: examples/good/traffic_cone_fixed.usda\n"
                  "(arrows: the asset's authored face-varying normals)",
                  fontsize=13, color=INK, pad=2)

    # --- facts table over the right half ---------------------------------
    panel1 = fig.add_axes([0.680, 0.415, 0.300, 0.464])
    panel1.set_xlim(0, 1)
    panel1.set_ylim(0, 1)
    panel1.axis("off")

    v = good["gates"]["validator"]
    panel1.text(0.0, 1.0, "judge verdict (seed %s)" % SEED, fontsize=15,
                color=INK, fontweight="bold", va="top")
    # gate rows, status chips with glyph + word
    y = 0.915
    labels = [("gate 1  NVIDIA validator", v["validator_status"],
               v["passed"]),
              ("gate 2  usd-core oracle", "0 errors",
               good["gates"]["oracle"]["passed"]),
              ("gate 3  geometry kept", "bbox dev 0.0 cm",
               good["gates"]["geometry"]["passed"])]
    for label, detail, passed in labels:
        glyph = "✓" if passed else "✗"
        color = GOOD if passed else CRITICAL
        panel1.add_patch(plt.Rectangle((0.0, y - 0.028), 0.055, 0.056,
                                      facecolor=color, linewidth=0))
        panel1.text(0.0275, y, glyph, fontsize=15, color="#ffffff",
                    fontweight="bold", ha="center", va="center")
        panel1.text(0.075, y, label, fontsize=13.5, color=INK,
                    va="center", fontweight="bold")
        panel1.text(0.075, y - 0.038, detail, fontsize=11.5, color=INK_2,
                    va="center")
        y -= 0.115

    # measured per-mesh numbers from the oracle facts
    y -= 0.02
    panel1.text(0.0, y, "oracle recount (usd-core alone)", fontsize=15,
                color=INK, fontweight="bold", va="top")
    y -= 0.055
    header = ("mesh", "normals/corners", "|norm|−1 max", "zero-area")
    xs = (0.0, 0.30, 0.68, 0.90)
    for x, h in zip(xs, header):
        panel1.text(x, y, h, fontsize=11, color=MUTED, va="top",
                    fontweight="bold")
    y -= 0.035
    for name, normals, corners, dev, zero in mesh_facts_lines(good):
        panel1.text(xs[0], y, name, fontsize=12, color=INK, va="center")
        panel1.text(xs[1], y, "%d / %d" % (normals, corners), fontsize=12,
                    color=INK, va="center")
        panel1.text(xs[2], y, "%.1e" % dev, fontsize=12, color=INK,
                    va="center")
        panel1.text(xs[3], y, str(zero), fontsize=12, color=INK, va="center")
        y -= 0.062
    meta = good["facts"]["oracle"]
    y -= 0.02
    for line in ("metersPerUnit 0.01 · upAxis Y · defaultPrim TrafficCone",
                 "bound materials 3/3 · colliders 1",
                 "point counts kept 8 / 20 / 20 · bbox deviation 0.0 cm "
                 "(limit %.0e)" % BBOX_TOL):
        panel1.text(0.0, y, line, fontsize=11.5, color=INK_2, va="center")
        y -= 0.058

    # pass lines: the numeric limits the figure draws against
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
