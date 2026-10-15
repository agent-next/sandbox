#!/usr/bin/env python3
"""result.png -- the three delivered parts vs the spec-built reference.

One row per good part.  Left: the delivered model.stl (what the tool
wrote).  Middle: the reference solid, rebuilt from judge/spec.json by
the judge's own build_reference().  Right: the delivered part again
with the boolean-XOR difference vs the reference highlighted in red
(gate 7's own boolean, manifold3d ^, run on the real meshes) -- for the
good parts the XOR volume is exactly 0, so nothing is red and the panel
says so with the measured number from the verdict JSON.

The readout column prints, per part, the gate numbers from the real
verdict JSON (grade.sh --seed 42 --json) and draws the pass lines:
three tolerance gates as measured/limit bars with the limit (=pass
line) at 1.0, and min wall as a bar with the spec floor line.  All
rules are "<=", so a bar at or below the line passes; that rule is
printed on the panel.
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
    ("bbox", "bbox"),
    ("volume_analytic", "volume"),
    ("xor_volume", "XOR"),
    ("min_wall", "min wall"),
]
LIMITS = {"bbox": 0.05, "volume_analytic": 0.005, "xor_volume": 0.010}
INK = "#1b1b1b"
GREEN = "#007756"       # pass
RED = "#b2182b"         # fail
GRAY = "0.55"


def verdict(part):
    p = os.path.join(VERDICTS, f"good_{part}.json")
    if not os.path.exists(p):
        raise SystemExit(f"missing {p} -- run collect_verdicts.sh first")
    return json.load(open(p))


def gate_line(part, v):
    """(label, text) rows printed per part, straight from the verdict."""
    g = v["gates"]
    b = g["bbox"]["measured"]
    row_b = (f"bbox   {b['step_extents'][0]:g}x{b['step_extents'][1]:g}x"
             f"{b['step_extents'][2]:g} vs spec "
             f"{b['spec'][0]:g}x{b['spec'][1]:g}x{b['spec'][2]:g}"
             f"\n       max dev {b['step_max_dev_mm']:g} mm  "
             f"(rule: each axis <= 0.05 mm)")
    q = g["volume_analytic"]["measured"]
    row_v = (f"volume {q['volume_mm3']:.3f} vs analytic "
             f"{q['analytic_mm3']:.3f} mm3"
             f"\n       rel err {q['rel_err'] * 100:.4f} %  "
             f"(rule: <= 0.5 %)")
    x = g["xor_volume"]["measured"]
    row_x = (f"XOR    {x['xor_volume_mm3']:.3f} mm3 = "
             f"{x['rel'] * 100:.3f} % of reference "
             f"{x['reference_volume_mm3']:.1f}"
             f"\n       (rule: <= 1.0 % of reference)")
    w = g["min_wall"]["measured"]
    if w.get("applicable") is False:
        row_w = ("min wall  not graded for this part\n"
                 "         (spec.json sets min_wall_mm = null)")
    else:
        row_w = (f"min wall {w['min_wall_mm']:.3f} mm over {w['rays']} "
                 f"seeded rays\n"
                 f"         (rule: >= {w['spec_min_wall_mm']:g} - 0.1 mm)")
    f = g["features"]["measured"]
    feats = []
    for cls, d in f["classes"].items():
        n = d["count"]
        r = d["radius_mm"][0] if d["radius_mm"] else float("nan")
        feats.append(f"{cls} x{n} r{r:g}")
    row_f = ("features " + "  ".join(feats) +
             f"\n         (rule: counts/radii exact, centres <= 0.05 mm)")
    return [("gate 5", row_b), ("gate 6", row_v), ("gate 7", row_x),
            ("gate 9", row_w), ("gate 8", row_f)]


def bars_panel(ax, v, part):
    """Pass-line bars: tolerance gates as fraction-of-limit; min wall mm."""
    g = v["gates"]
    labels, fracs, meas = [], [], []
    for gate, lab in GATE_COLS[:3]:
        m = g[gate]["measured"]
        val = {"bbox": lambda: m["step_max_dev_mm"],
               "volume_analytic": lambda: m["rel_err"],
               "xor_volume": lambda: m["rel"]}[gate]()
        labels.append(lab)
        fracs.append(val / LIMITS[gate])
        meas.append(val)
    y = np.arange(3)[::-1]
    cols = [GREEN if fr <= 1.0 else RED for fr in fracs]
    ax.barh(y, fracs, height=0.62, color=cols, alpha=0.9)
    ax.axvline(1.0, color=RED, lw=1.6, ls=(0, (5, 3)))
    ax.set_yticks(y)
    lab_map = {"bbox": "bbox dev\n/ 0.05 mm",
               "volume": "vol rel err\n/ 0.005",
               "XOR": "XOR rel\n/ 0.010"}
    ax.set_yticklabels([lab_map[l] for l in labels], fontsize=7.5)
    for yi, fr, mv, l in zip(y, fracs, meas, labels):
        txt = {"bbox": f"{mv * 1000:.1f} um", "volume": f"{mv * 100:.4f} %",
               "XOR": f"{mv * 100:.3f} %"}[l]
        ax.text(min(fr, 1.0) + 0.03, yi, txt + "  (0.0 % of limit used)"
                if fr == 0 else txt, va="center", fontsize=7.5, color=INK)
    ax.set_xlim(0, 1.45)
    ax.set_xticks([0, 1.0])
    ax.set_xticklabels(["0", "1.0"], fontsize=7)
    ax.set_xlabel("fraction of the limit used -- at or left of the dashed "
                  "line passes (rules are <=)", fontsize=7.5)
    ax.text(1.0, 2.62, " limit = pass line", color=RED, fontsize=7.5,
            ha="left", va="center")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(length=2)


def main():
    fig = plt.figure(figsize=(15.0, 12.6), dpi=200)
    gs = fig.add_gridspec(3, 2, width_ratios=[2.62, 1.0],
                          height_ratios=[1.0] * 3,
                          left=0.015, right=0.985, top=0.930, bottom=0.028,
                          wspace=0.04, hspace=0.14)

    for r, part in enumerate(PARTS):
        v = verdict(part)
        delivered = cadviz.load_stl(
            os.path.join(cadviz.DEMO, "examples", "good", part, "model.stl"))
        ref, ref_vol = cadviz.reference_mesh(part)
        diff, xor_vol = cadviz.xor_solid(delivered, ref)

        # cross-check our recomputation against the judge's own numbers
        xg = v["gates"]["xor_volume"]["measured"]
        assert abs(xor_vol - xg["xor_volume_mm3"]) < 1e-3 * max(
            1.0, xg["reference_volume_mm3"] * 0.01) + 1e-6, \
            f"{part}: XOR recompute {xor_vol} != verdict {xg['xor_volume_mm3']}"
        assert abs(ref_vol - xg["reference_volume_mm3"]) < 1e-6, \
            f"{part}: reference volume drift"

        hi = cadviz.faces_in_solid(delivered, diff)
        elev, azim = (24, -55) if part != "adapter_plate" else (28, -60)

        ax0 = fig.add_subplot(gs[r, 0], projection="3d")
        fc = cadviz.shaded_facecolors(delivered)
        cadviz.draw_mesh(ax0, delivered, fc=fc, elev=elev, azim=azim,
                         title=f"delivered model.stl  ({len(delivered.faces)} "
                               f"facets, from the tool run)")
        ax1 = fig.add_subplot(gs[r, 0], projection="3d")  # placeholder swap
        # (matplotlib gridspec cells are reused via add_subplot below)
        plt.delaxes(ax1)

        # three renders side by side inside the wide cell: use subgridspec
        # (recreate: remove placeholder approach)
        gs_row = gs[r, 0].subgridspec(1, 3, wspace=0.01)
        axA = fig.add_subplot(gs_row[0, 0], projection="3d")
        cadviz.draw_mesh(axA, delivered, fc=fc, elev=elev, azim=azim,
                         title="delivered model.stl\n(tool output, judged)")
        axB = fig.add_subplot(gs_row[0, 1], projection="3d")
        cadviz.draw_mesh(axB, ref, fc=cadviz.shaded_facecolors(
            ref, base=(0.78, 0.82, 0.87)), elev=elev, azim=azim,
            title="reference solid\n(built from spec.json only)")
        axC = fig.add_subplot(gs_row[0, 2], projection="3d")
        fc2 = fc.copy()
        fc2[hi] = cadviz.RED + (1.0,)
        cadviz.draw_mesh(axC, delivered, fc=fc2, elev=elev, azim=azim,
                         title=f"XOR difference highlighted\n"
                               f"{len(np.flatnonzero(hi))} of "
                               f"{len(delivered.faces)} facets in red")
        xrel = xg["rel"]
        axC.text2D(0.5, 0.02,
                   f"XOR {xg['xor_volume_mm3']:.3f} mm3 = "
                   f"{xrel * 100:.3f} % of reference  "
                   f"(rule <= 1.0 % -> {'PASS' if xrel <= 0.01 else 'FAIL'})",
                   transform=axC.transAxes, ha="center", fontsize=8,
                   color=GREEN if xrel <= 0.01 else RED)

        # row label + readout
        axT = fig.add_subplot(gs[r, 1])
        axT.axis("off")
        name = TITLES[part]
        npass = sum(1 for gg in v["gates"].values() if gg["pass"] is True)
        axT.text(0.0, 1.0, f"{name}  --  {npass}/10 gates PASS "
                           f"(exit 0, seed {v['seed']})",
                 fontsize=10.5, fontweight="bold", va="top", color=INK)
        y = 0.925
        for tag, line in gate_line(part, v):
            axT.text(0.0, y, tag, fontsize=7.6, va="top", color=GRAY,
                     family="monospace")
            axT.text(0.075, y, line, fontsize=7.6, va="top", color=INK,
                     family="monospace", linespacing=1.35)
            y -= 0.052 * (line.count("\n") + 1) + 0.012
        gs_in = gs[r, 1].subgridspec(1, 1)
        axB2 = fig.add_subplot(
            fig.add_gridspec(1, 1, left=0.40, right=0.99,
                             top=0.10 + 0.30 * (2 - r),
                             bottom=0.02 + 0.30 * (2 - r))[0, 0])
        bars_panel(axB2, v, part)

    fig.suptitle("text-to-CAD judged: the delivered STEP/STL vs the "
                 "spec-built reference -- all 10 gates pass on all three parts",
                 fontsize=13.5, fontweight="bold", y=0.975)
    fig.text(0.015, 0.005,
             "source: judge/grade.sh examples/good/<part> --seed 42 --json "
             "(media/data/verdicts/good_*.json); reference solids and the XOR "
             "boolean are the judge's own code (check_gates.build_reference, "
             "manifold3d ^).  'gates 1-4, 10' (tool reruns, byte-identical "
             "delivery, STEP/STL validity, judge intact) pass and are not "
             "barred: their rules are printed in loop.png.",
             fontsize=7.2, color="0.35")
    fig.savefig(OUT)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
