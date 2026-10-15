#!/usr/bin/env python3
"""result.png -- the three delivered parts vs the spec-built reference.

Layout, top to bottom, one band per known-good part:

  * three renders of the REAL meshes: the delivered model.stl (what the
    tool wrote), the reference solid rebuilt from judge/spec.json by the
    judge's own build_reference(), and the delivered part again with the
    boolean-XOR difference vs the reference painted red (gate 7's own
    boolean, manifold3d ^, on the real meshes -- for the good parts the
    XOR volume is exactly 0, so nothing is red and the panel says so with
    the measured number from the verdict JSON);
  * the gate numbers, printed from the verdict JSON of
    `grade.sh examples/good/<part> --seed 42 --json`;
  * a pass-line bar chart of the three tolerance gates, measured as a
    fraction of the gate limit, with the limit (= pass line) at 1.0:
    all rules are <=, so a bar at or left of the line passes.

Pass/fail colours are Okabe-Ito bluish green / vermillion, which pass the
CVD checks for a two-status palette (validated).  A static overlap check
refuses to write the figure while any two text artists overlap; it is
re-run by make_media.sh over the saved PNG.

Every number printed here comes from a judge verdict JSON (or is recomputed
by the judge's own code path and asserted equal to the verdict).
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import cadviz

MEDIA = cadviz.MEDIA
VERDICTS = os.path.join(MEDIA, "data", "verdicts")
OUT = os.path.join(MEDIA, "result.png")

PARTS = ["bushing", "adapter_plate", "bracket"]
TITLES = {"bushing": "bushing", "adapter_plate": "adapter plate",
          "bracket": "L-bracket"}

GATE_COLS = [
    ("bbox", "bbox dev <= 0.05 mm"),
    ("volume_analytic", "vol rel err <= 0.5 %"),
    ("xor_volume", "XOR rel <= 1.0 %"),
]
LIMITS = {"bbox": 0.05, "volume_analytic": 0.005, "xor_volume": 0.010}
INK = "#1b1b1b"
GRAY = "#6b6b6b"


def verdict(part):
    p = os.path.join(VERDICTS, f"good_{part}.json")
    if not os.path.exists(p):
        raise SystemExit(f"missing {p} -- run collect_verdicts.sh first")
    return json.load(open(p))


def gate_rows(part, v):
    """(tag, text) rows: the key gate numbers, straight from the verdict."""
    g = v["gates"]
    rows = []

    b = g["bbox"]["measured"]
    rows.append(("gate 5  bbox",
                 f"{b['step_extents'][0]:g} x {b['step_extents'][1]:g} x "
                 f"{b['step_extents'][2]:g} mm vs spec "
                 f"{b['spec'][0]:g} x {b['spec'][1]:g} x {b['spec'][2]:g}\n"
                 f"          max dev {b['step_max_dev_mm']:g} mm\n"
                 f"          rule: every axis <= 0.05 mm of spec"))

    q = g["volume_analytic"]["measured"]
    rows.append(("gate 6  volume",
                 f"{q['volume_mm3']:.3f} mm3 vs analytic "
                 f"{q['analytic_mm3']:.3f}\n"
                 f"          rel err {q['rel_err'] * 100:.4f} %\n"
                 f"          rule: rel err <= 0.5 %"))

    f = g["features"]["measured"]
    feats = "\n".join(
        f"          {cls} x{d['count']} (want {d['count_expected']})"
        + (f" r{d['radius_mm'][0]:g}" if d["radius_mm"] else "")
        for cls, d in sorted(f["classes"].items()))
    rows.append(("gate 8  features", feats.lstrip() + "\n"
                 "          rule: counts/radii exact, centres <= 0.05 mm"))

    w = g["min_wall"]["measured"]
    if w.get("applicable") is False:
        rows.append(("gate 9  min wall", "not graded for this part\n"
                                         "          (spec.json: "
                                         "min_wall_mm = null)"))
    else:
        rows.append(("gate 9  min wall",
                     f"{w['min_wall_mm']:.3f} mm over {w['rays']} seeded "
                     f"rays\n"
                     f"          rule: >= {w['spec_min_wall_mm']:g} - 0.1 "
                     f"mm (hole edge to next face)"))
    return rows


def bars_panel(ax, v):
    """The three tolerance gates as fractions of their limits."""
    g = v["gates"]
    y, fracs, texts = [], [], []
    for gate, _lab in GATE_COLS:
        m = g[gate]["measured"]
        val = {"bbox": lambda: m["step_max_dev_mm"],
               "volume_analytic": lambda: m["rel_err"],
               "xor_volume": lambda: m["rel"]}[gate]()
        y.append(len(y))
        fracs.append(val / LIMITS[gate])
        texts.append({"bbox": f"{val * 1000:.1f} um",
                      "volume_analytic": f"{val * 100:.4f} %",
                      "xor_volume": f"{val * 100:.3f} %"}[gate])
    y = np.array(y)[::-1]                     # first gate at the top
    ax.barh(y, fracs, height=0.62, color=cadviz.PASS, alpha=0.9)
    ax.axvline(1.0, color=cadviz.FAIL, lw=1.6, ls=(0, (5, 3)), zorder=3)
    # gate name + measured value are drawn INSIDE the axes (left of the
    # bar), so no tick label can extend left into the render column
    for yi, fr, tx, (_g, lab) in zip(y, fracs, texts, GATE_COLS[::-1]):
        ax.text(-0.04, yi, lab, ha="right", va="center", fontsize=7.4,
                color=GRAY)
        ax.text(fr + 0.03, yi, tx, va="center", fontsize=7.4, color=INK)
    ax.set_yticks([])
    ax.set_ylim(-0.85, 2.6)          # headroom for the 90 deg-style labels
    ax.set_xlim(-0.78, 1.58)
    ax.set_xticks([0, 1.0])
    ax.set_xticklabels(["0", "1.0 = pass line"], fontsize=7.4)
    ax.set_xlabel("fraction of the gate limit used; the rule is '<=', so a "
                  "bar ending left of the dashed line passes",
                  fontsize=7.0, color=GRAY)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(length=2)


FIG_W, FIG_H, DPI = 16.4, 16.5, 200


def line_frac(fontsize, linespacing, ax_h_in):
    """Axes-fraction height of one text line at `fontsize` pt."""
    return (fontsize * linespacing) / (ax_h_in * 72.0)


def main():
    fig = plt.figure(figsize=(FIG_W, FIG_H), dpi=DPI)
    gs = fig.add_gridspec(3, 2, width_ratios=[2.62, 1.0],
                          height_ratios=[1.0] * 3,
                          left=0.006, right=0.994, top=0.938, bottom=0.030,
                          wspace=0.015, hspace=0.20)

    for r, part in enumerate(PARTS):
        v = verdict(part)
        delivered = cadviz.load_stl(
            os.path.join(cadviz.DEMO, "examples", "good", part, "model.stl"))
        ref, ref_vol = cadviz.reference_mesh(part)
        diff, xor_vol = cadviz.xor_solid(delivered, ref)

        # cross-check the recomputation against the judge's own numbers
        xg = v["gates"]["xor_volume"]["measured"]
        assert abs(xor_vol - xg["xor_volume_mm3"]) <= max(1e-6, 1e-6 * ref_vol), \
            f"{part}: XOR recompute {xor_vol} != verdict {xg['xor_volume_mm3']}"
        assert abs(ref_vol - xg["reference_volume_mm3"]) <= 1e-6 * ref_vol

        hi = cadviz.faces_in_solid(delivered, diff)
        elev, azim = (24, -55) if part != "adapter_plate" else (30, -62)

        gs_row = gs[r, 0].subgridspec(1, 3, wspace=0.005)
        fc = cadviz.shaded_facecolors(delivered)
        axA = fig.add_subplot(gs_row[0, 0], projection="3d")
        cadviz.draw_mesh(axA, delivered, fc=fc, elev=elev, azim=azim,
                         title=f"delivered model.stl\n(the tool's output, "
                               f"-- what was judged)")
        axB = fig.add_subplot(gs_row[0, 1], projection="3d")
        cadviz.draw_mesh(
            axB, ref, fc=cadviz.shaded_facecolors(ref, base=(0.80, 0.84, 0.88)),
            elev=elev, azim=azim,
            title="reference solid\n(built from spec.json alone)")
        axC = fig.add_subplot(gs_row[0, 2], projection="3d")
        fc2 = fc.copy()
        fc2[hi] = cadviz.FAIL_RGB + (1.0,)
        nred = len(np.flatnonzero(hi))
        cadviz.draw_mesh(axC, delivered, fc=fc2, elev=elev, azim=azim,
                         title=f"XOR difference vs reference\n"
                               f"{nred} of {len(delivered.faces)} facets "
                               f"flagged red")
        xrel = xg["rel"]
        axC.text2D(0.5, 0.015,
                   f"XOR {xg['xor_volume_mm3']:.3f} mm3 = "
                   f"{xrel * 100:.3f} % of the reference (gate 7)\n"
                   f"rule: XOR <= 1.0 % of reference -> "
                   f"{'PASS' if xrel <= 0.01 else 'FAIL'}",
                   transform=axC.transAxes, ha="center", fontsize=8,
                   color=cadviz.PASS if xrel <= 0.01 else cadviz.FAIL)

        # right column: the numbers of this part, then its pass-line bars
        axT = fig.add_subplot(gs[r, 1])
        axT.axis("off")
        cell = gs[r, 1].get_position(fig)
        row_h_in = cell.height * FIG_H
        fs = 7.6
        lh = line_frac(fs, 1.46, row_h_in)

        npass = sum(1 for gg in v["gates"].values() if gg["pass"] is True)
        axT.text(0.0, 1.0,
                 f"{TITLES[part]} -- {npass}/10 gates PASS\n"
                 f"grade.sh exit {0 if v['pass'] else 1}, seed {v['seed']}, "
                 f"judge/grade.sh --json",
                 fontsize=9.8, fontweight="bold", va="top", color=INK,
                 linespacing=1.3)
        y = 1.0 - 3.0 * line_frac(9.8, 1.3, row_h_in) - 0.5 * lh
        for tag, text in gate_rows(part, v):
            axT.text(0.0, y, tag, fontsize=fs, va="top", color=GRAY,
                     family="monospace")
            body = "\n".join(cadviz.wrap(ln, 60) for ln in text.split("\n"))
            axT.text(0.0, y - lh, body, fontsize=fs, va="top", color=INK,
                     family="monospace", linespacing=1.42)
            y -= (body.count("\n") + 2) * lh + 0.7 * lh

        # bars occupy the bottom slab of the same row, below the text
        bars_top = max(0.02, min(0.42, y - 0.6 * lh))
        axBars = fig.add_axes([cell.x0 + 0.006, cell.y0 + 0.010,
                               cell.width - 0.012,
                               cell.height * bars_top - 0.010])
        bars_panel(axBars, v)

    fig.suptitle("text-to-CAD judged: the delivered STEP/STL vs the "
                 "spec-built reference -- all 10 gates pass on all three parts",
                 fontsize=14, fontweight="bold", y=0.982)
    fig.text(0.006, 0.010,
             "source: judge/grade.sh examples/good/<part> --seed 42 --json "
             "(media/data/verdicts/good_*.json); the reference solids and the "
             "XOR boolean are the judge's own code path "
             "(check_gates.build_reference + tessellate, manifold3d ^), "
             "recomputed here and asserted equal to the verdict.",
             fontsize=7.5, color="0.4")
    cadviz.check_no_overlap(fig, "result.png")
    fig.savefig(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
