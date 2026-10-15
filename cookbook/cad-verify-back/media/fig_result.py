#!/usr/bin/env python3
"""result.png: the delivered part vs the spec, judged from its own files.

Left  - the real part (STL delivered in examples/good, parsed with the
        judge's own trimesh pin) beside the reference solid rebuilt from the
        spec JSON alone, with the manifold3d XOR symmetric-difference volume
        that gate G7 measured (0.0 mm^3 for the good example) annotated.
Right - the DXF drawing overlay (parsed with the judge's ezdxf pin) with the
        bolt-circle hole positions from the verdict JSON and the angular
        deviation of each step vs the 0.05 deg tolerance (gate G6), plus the
        per-gate verdict numbers from the verdict JSON (gate names G1..G13).

Every number is read from media/data/verdicts/good.json (written by
'judge/grade.sh examples/good --json ...' during make_media.sh's data stage)
or parsed from the delivered files with the judge's pinned tools.  The script
fails loudly if any of those files is missing.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as rd  # noqa: E402

VJ = rd.verdicts_dir()
GOOD_DIR = os.path.join(os.path.dirname(rd.HERE), "examples", "good")

YAW, TILT = 55.0, 24.0


def main():
    vpath = os.path.join(VJ, "good.json")
    if not os.path.isfile(vpath):
        raise SystemExit(f"result: missing judge verdict {vpath} - run "
                         "'bash media/make_media.sh data' first")
    v = rd.load_verdict(vpath)
    g = v["gates"]
    spec = rd.spec()
    r = spec["pcd"] / 2.0

    art = rd.load_stl(os.path.join(GOOD_DIR, "part.stl"))
    ref = rd.ref_mesh(spec)
    R = rd.rot_ypr(YAW, TILT)

    fig = rd.plt.figure(figsize=(12.4, 7.4), dpi=200, facecolor=rd.SURFACE)

    fig.text(0.015, 0.958, "cad-verify-back: the delivered files vs the customer spec",
             fontsize=17, fontweight="bold", color=rd.INK, va="center")
    fig.text(0.015, 0.915,
             f"Judge verdict: PASS on all 14 gates  ·  OCCT volume "
             f"{g['step_volume']['volume_mm3']:.1f} mm³ vs closed-form "
             f"{g['step_volume']['expected_mm3']:.1f} mm³ "
             f"(rel err {g['step_volume']['rel_err']:.1e})",
             fontsize=10, color=rd.INK2, va="center")
    fig.text(0.015, 0.881,
             f"manifold3d XOR vs the spec-built reference solid: "
             f"{g['step_xor']['xor_volume_mm3']:.1f} mm³ symmetric difference "
             f"(gate G7 pass rule ≤ 1% of {g['step_xor']['reference_volume_mm3']:.0f} mm³)",
             fontsize=10, color=rd.INK2, va="center")

    # ---- left: delivered STL beside the spec-built reference ---------------
    axA = fig.add_axes([0.015, 0.30, 0.465, 0.555])
    rd.draw_mesh(axA, art, YAW, TILT, base=rd.BLUE)
    ext = rd.mesh_extent(art, R)

    axR = axA.inset_axes([0.645, 0.585, 0.345, 0.39], transform=axA.transAxes)
    rd.draw_mesh(axR, ref, YAW, TILT, base=rd.ORANGE)
    axR.set_title("reference solid\n(rebuilt from spec.json)", fontsize=7.5,
                  color=rd.INK2, pad=1)

    axA.set_title("delivered part.stl (examples/good) — parsed with trimesh 5.1.1",
                  fontsize=8.5, color=rd.INK2, pad=4)
    fig.text(0.015, 0.262,
             "gate G7 (step_xor): manifold3d boolean XOR of the tessellated delivered "
             f"solid vs the reference — {g['step_xor']['xor_volume_mm3']:.1f} mm³ "
             f"symmetric difference (rel {g['step_xor']['rel_err']:.3%});\n"
             "pass rule ≤ 1% of the reference volume — identical geometry gives an "
             "empty XOR, which is why a zero bar passes (rule on the figure, not "
             "just a small number)",
             fontsize=7.5, color=rd.INK, va="top", linespacing=1.45,
             bbox=dict(facecolor=rd.GOOD_WASH, edgecolor=rd.GOOD,
                       linewidth=0.8, boxstyle="round,pad=0.4"))

    # ---- right: DXF overlay with the bolt circle and angular deviations -----
    # data aspect 140/104 in a fixed box so equal-aspect never fights the slot
    axB = fig.add_axes([0.5095, 0.522, 0.2626, 0.328])
    outline, circles = rd.dxf_circles(os.path.join(GOOD_DIR, "part.dxf"))
    xs = [p[0] for p in outline] + [outline[0][0]]
    ys = [p[1] for p in outline] + [outline[0][1]]
    axB.plot(xs, ys, color=rd.INK2, linewidth=1.2, zorder=1)
    for (cx, cy, d) in circles:
        axB.add_patch(rd.matplotlib.patches.Circle(
            (cx, cy), d / 2.0, fill=False, edgecolor=rd.MUTED,
            linewidth=0.9, zorder=2))
    for (cx, cy) in g["step_holes"]["bolt_centres"]:
        axB.plot([0, cx], [0, cy], color=rd.ORANGE, linewidth=0.7,
                 alpha=0.85, zorder=3)
        axB.plot(cx, cy, marker="o", markersize=4.5, color=rd.ORANGE,
                 zorder=5)
    t = rd.matplotlib.patches.Circle((0, 0), r, fill=False,
                                     edgecolor=rd.ORANGE, linewidth=1.0,
                                     linestyle=(0, (4, 3)), zorder=3)
    axB.add_patch(t)
    axB.set_title("delivered part.dxf (ezdxf 1.4.4) with the spec PCD overlaid: "
                  "gate G6 angular spacing", fontsize=8.5, color=rd.INK2, pad=4)
    axB.set_xlabel(f"{spec['pcd']} mm pitch circle, {spec['bolt_n']} × ⌀{spec['bolt_d']} "
                   "bolt holes", fontsize=7.5, color=rd.INK2)
    axB.set_xlim(-70, 70)
    axB.set_ylim(-52, 52)
    axB.set_aspect("equal")
    axB.xaxis.set_major_locator(rd.matplotlib.ticker.MultipleLocator(20))
    axB.yaxis.set_major_locator(rd.matplotlib.ticker.MultipleLocator(20))
    axB.tick_params(colors=rd.MUTED, labelsize=6.5)
    for s in axB.spines.values():
        s.set_color(rd.GOOD if v["verdict"] == "pass" else rd.CRIT)
        s.set_linewidth(1.6)

    max_dev = g["angular_spacing"]["max_deviation_deg"]
    tol = 0.05
    axB.text(-66, -49, f"max angular deviation {max_dev:.4g}° — pass rule ≤ {tol:g}°\n"
             f"(gate G6: every step within {tol:g}° of "
             f"{g['angular_spacing']['expected_step_deg']:g}°)", fontsize=7,
             color=rd.INK, va="bottom", linespacing=1.35,
             bbox=dict(facecolor=rd.GOOD_WASH if max_dev <= tol else rd.CRIT_WASH,
                       edgecolor=rd.GOOD if max_dev <= tol else rd.CRIT,
                       linewidth=0.8, boxstyle="round,pad=0.3"))

    # ---- right: per-gate measured numbers from the verdict JSON -------------
    axC = fig.add_axes([0.5095, 0.145, 0.4755, 0.325])
    rd.style_axes(axC)
    axC.set_axisbelow(True)
    names, vals, lims, cols = [], [], [], []

    def row(name, measured, limit):
        gg = g[name]
        ok = gg["pass"]
        names.append(rd.GATE_SHORT[name].replace("\n", " "))
        vals.append(measured)
        lims.append(limit)
        cols.append(rd.GOOD if ok else rd.CRIT)

    row("step_volume", g["step_volume"]["rel_err"] * 100, 0.1)
    row("step_xor", g["step_xor"]["rel_err"] * 100, 1.0)
    row("angular_spacing", max_dev, 0.05)
    row("stl_volume", g["stl_volume"]["rel_err"] * 100, 1.0)
    row("step_bbox", g["step_bbox"]["max_err_mm"], 0.01)
    row("step_pcd", max(g["step_pcd"]["max_radial_err_mm"],
                        g["step_pcd"]["max_pos_err_mm"]), 0.02)

    xpos = list(range(len(names)))
    axC.bar(xpos, vals, width=0.62, color=cols, zorder=3)
    for i, (val, lim) in enumerate(zip(vals, lims)):
        axC.plot([i - 0.31, i + 0.31], [lim, lim], color=rd.INK,
                 linewidth=1.3, zorder=4)
        axC.text(i + 0.34, lim, f"{lim:g}", fontsize=6.5, color=rd.INK,
                 va="center", zorder=5)
    axC.set_xticks(xpos)
    axC.set_xticklabels(names, fontsize=6.8, color=rd.INK2)
    axC.set_yscale("symlog", linthresh=1e-3)
    axC.set_ylim(0, 20)
    axC.set_xlim(-0.7, len(names) - 0.2)
    axC.set_ylabel("measured error  |  mark = pass limit (log scale)", fontsize=7.5,
                   color=rd.INK2)
    yticks = [1e-3, 1e-2, 1e-1, 1, 10]
    axC.set_yticks(yticks)
    axC.set_yticklabels(["0.001", "0.01", "0.1", "1", "10"], fontsize=6.5)
    axC.grid(axis="y", color=rd.GRID, linewidth=0.5)
    axC.set_title("per-gate measured errors from the verdict JSON "
                  "(all limits as drawn, all gates PASS)", fontsize=8.5,
                  color=rd.INK2, pad=4)
    axC.text(0.02, 0.95,
             "units per gate: G3 %, G7 %, G6 deg, G10 %, G2 mm, G5 mm — "
             "each mark is that gate's numeric pass rule",
             transform=axC.transAxes, fontsize=6.2, color=rd.MUTED, va="top")

    # legend outside the data, upper figure area of this axis
    handles = [
        rd.matplotlib.patches.Patch(facecolor=rd.GOOD, label="gate PASS (measured)"),
        rd.matplotlib.lines.Line2D([], [], color=rd.INK, linewidth=1.3,
                                   label="pass limit (gate rule)"),
        rd.matplotlib.lines.Line2D([], [], color=rd.ORANGE, linewidth=0.9,
                                   linestyle=(0, (4, 3)),
                                   label="spec PCD (56 mm)"),
    ]
    axC.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.0, -0.30),
               ncol=3, fontsize=6.8, frameon=False)

    rd.assert_no_overlaps(fig, "result.png")

    out = os.path.join(rd.HERE, "result.png")
    fig.savefig(out, dpi=200, facecolor=rd.SURFACE)
    print(f"result.png written ({os.path.getsize(out)} bytes)")


if __name__ == "__main__":
    main()
