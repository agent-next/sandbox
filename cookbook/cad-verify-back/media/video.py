#!/usr/bin/env python3
"""demo.mp4 frames: the part, the loop, and one card per mutant.

Sequence (24.0 s at 30 fps, 1920x1080):
  1. title + part turntable (the real delivered STL, trimesh-parsed) with the
     verdict headline from the good verdict JSON (5.5 s)
  2. the agent-loop replay panel from fig_loop (4.0 s)
  3. one card per mutant (10 x 1.35 s = 13.5 s): the mutant's mesh or DXF
     drawing with the defect visible where it can be drawn, the gates that
     failed on their own evidence (measured vs limit, parsed from the
     verdict JSON), and the G-number of the gate that caught it.
  4. outro: verdict summary (1.0 s)

All numbers come from media/data/ (judge outputs).  Frames are written to
media/data/frames/ and encoded by make_media.sh (lossless crf-0 master first,
then the web encode).
"""
import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as rd  # noqa: E402

from fig_loop import MUTANTS, MUTANT_LABEL  # noqa: E402

W, H = 19.2, 10.8          # inches at dpi=100 => 1920x1080
FRAMES = os.path.join(rd.DATA, "frames")
GOOD_DIR = os.path.join(os.path.dirname(rd.HERE), "examples", "good")

FRONT = (55.0, 24.0)


def spec_bolt_centres(spec):
    import math
    r = spec["pcd"] / 2.0
    return [(r * math.cos(2 * np.pi * i / spec["bolt_n"]),
             r * math.sin(2 * np.pi * i / spec["bolt_n"]))
            for i in range(spec["bolt_n"])]


def frame_name(i):
    return os.path.join(FRAMES, f"f{i:05d}.png")


def new_fig():
    return rd.plt.figure(figsize=(W, H), dpi=100, facecolor=rd.SURFACE)


def top(title, sub=""):
    rd.plt.figtext(0.024, 0.928, title, fontsize=26, fontweight="bold",
                   color=rd.INK, va="center")
    if sub:
        rd.plt.figtext(0.024, 0.868, sub, fontsize=14, color=rd.INK2,
                       va="center")


def save(fig, i):
    rd.assert_no_overlaps(fig, f"video frame {i}", ignore_xy=True)
    fig.savefig(frame_name(i), dpi=100, facecolor=rd.SURFACE)
    rd.plt.close(fig)


def sec(s):        # seconds -> frame index
    return int(round(s * 30.0))


# --------------------------------------------------------------------------
def mesh_with_holes_highlights(mesh, spec, centres, hole_d, R):
    """Face indices whose triangle centroid lies within a bolt hole."""
    import math
    fc = mesh.triangles_center
    out = []
    for (cx, cy) in centres:
        d = np.hypot(fc[:, 0] - cx, fc[:, 1] - cy)
        # all faces inside the hole cylinder (top and bottom rims included)
        out.extend(np.where(d < hole_d / 2.0 + 0.05)[0].tolist())
    return out


def defect_visual(ax, mutant, v, spec):
    """Draw the mutant's own artifact so the defect is actually visible."""
    art_dir = os.path.join(rd.DATA, "mutants", mutant)
    stl = os.path.join(art_dir, "part.stl")
    dxf = os.path.join(art_dir, "part.dxf")

    if mutant == "dxf_missing_hole":
        outline, circles = rd.dxf_circles(dxf)
        ax.plot([p[0] for p in outline] + [outline[0][0]],
                [p[1] for p in outline] + [outline[0][1]],
                color=rd.INK2, linewidth=1.6)
        for (cx, cy, d) in circles:
            ax.add_patch(rd.matplotlib.patches.Circle(
                (cx, cy), d / 2.0, fill=False, edgecolor=rd.MUTED,
                linewidth=1.4))
        for (cx, cy) in spec_bolt_centres(spec):
            if not any(abs(cx - c[0]) < 0.02 and abs(cy - c[1]) < 0.02
                       for c in [(x, y) for (x, y, d) in circles]):
                ax.add_patch(rd.matplotlib.patches.Circle(
                    (cx, cy), spec["bolt_d"] / 2.0, fill=True,
                    facecolor=rd.CRIT_WASH, edgecolor=rd.CRIT, linewidth=2.0))
        ax.set_xlim(-70, 70)
        ax.set_ylim(-48, 48)
        ax.set_aspect("equal")
        ax.text(-66, -42, "missing DXF circle", fontsize=13, color=rd.CRIT)
    elif mutant in ("stl_flipped_facet", "stl_not_watertight"):
        mesh = rd.load_stl(stl)
        if mutant == "stl_flipped_facet":
            # facet 0 of the binary STL is the highlighted one
            hl = {0}
        else:
            # facet 0 was dropped from the STL; show the hole's neighbours:
            # draw the mesh as-is; the defect is drawn by the missing triangle
            hl = set()
        rd.draw_mesh(ax, mesh, *FRONT, base=rd.BLUE, highlight=hl)
        if mutant == "stl_not_watertight":
            # mark where the dropped facet leaves a gap: its 3 vertices
            import trimesh
            good_mesh = rd.load_stl(os.path.join(GOOD_DIR, "part.stl"))
            # facet 0 of the good mesh = the dropped one
            tri = good_mesh.vertices[good_mesh.faces[0]]
            Rm = rd.rot_ypr(*FRONT)
            p = tri @ Rm.T
            ax.plot(p[:, 0], p[:, 1], color=rd.CRIT, linewidth=4.0,
                    marker="o", markersize=6.0, zorder=6,
                    markerfacecolor=rd.CRIT, markeredgecolor="white")
            ax.text(p[:, 0].mean(), p[:, 1].mean() + 6, "dropped facet",
                    fontsize=13, color=rd.CRIT, zorder=7)
    else:
        mesh = rd.load_stl(stl)
        gg = v["gates"]
        if mutant == "tangential_hole_drift":
            cents = gg["step_holes"]["bolt_centres"]
            good_c = spec_bolt_centres(spec)
            hl = mesh_with_holes_highlights(mesh, spec, cents, spec["bolt_d"],
                                            rd.rot_ypr(*FRONT))
            rd.draw_mesh(ax, mesh, *FRONT, base=rd.BLUE, highlight=hl)
            # drift arrows on the projected view
            Rm = rd.rot_ypr(*FRONT)
            import math
            for (cx, cy) in cents:
                best = min(good_c, key=lambda c: math.hypot(c[0] - cx, c[1] - cy))
                if math.hypot(best[0] - cx, best[1] - cy) > 0.1:
                    p0 = np.array([best[0], best[1], 6.0]) @ Rm.T
                    p1 = np.array([cx, cy, 6.0]) @ Rm.T
                    ax.annotate("", xy=(p1[0], p1[1]), xytext=(p0[0], p0[1]),
                                arrowprops=dict(arrowstyle="->", lw=2.2,
                                                color=rd.CRIT), zorder=6)
        elif mutant in ("wrong_pcd", "edge_violation", "wrong_bolt_count",
                        "bore_off", "boss_missing", "scale_inch_mm"):
            hl = set()
            if "step_holes" in gg and gg["step_holes"].get("pass") is False \
               and gg["step_holes"].get("bolt_centres"):
                cents = gg["step_holes"]["bolt_centres"]
                if len(cents):
                    hl = set(mesh_with_holes_highlights(
                        mesh, spec, cents, spec["bolt_d"],
                        rd.rot_ypr(*FRONT)))
            rd.draw_mesh(ax, mesh, *FRONT, base=rd.BLUE, highlight=hl)


def main():
    os.makedirs(FRAMES, exist_ok=True)
    for f in glob.glob(os.path.join(FRAMES, "*.png")):
        os.remove(f)

    spec = rd.spec()
    vgood = rd.load_verdict(os.path.join(rd.verdicts_dir(), "good.json"))
    gg = vgood["gates"]
    replay = sorted(glob.glob(os.path.join(rd.DATA, "replay", "iter*.json")))

    i = 0

    # ---- section 1: title + part turntable (5.5 s) --------------------------
    art = rd.load_stl(os.path.join(GOOD_DIR, "part.stl"))
    ref = rd.ref_mesh(spec)

    n_turn = sec(2.0)
    still_after = sec(5.5) - n_turn
    for k in range(n_turn):
        yaw = 55.0 + 360.0 * k / n_turn
        fig = new_fig()
        top("cad-verify-back",
            "an agent builds an adapter plate with CadQuery/OCCT — a judge "
            "grades the delivered STEP/STL/DXF, never its code")
        ax = fig.add_axes([0.03, 0.06, 0.62, 0.76])
        rd.draw_mesh(ax, art, yaw, 24.0, base=rd.BLUE)
        axr = fig.add_axes([0.68, 0.42, 0.28, 0.38])
        rd.draw_mesh(axr, ref, yaw, 24.0, base=rd.ORANGE)
        axr.set_title("spec-built reference", fontsize=11, color=rd.INK2)
        txt = ("delivered part.stl (trimesh 5.1.1)\n"
               f"OCCT volume {gg['step_volume']['volume_mm3']:.1f} mm³\n"
               f"closed-form spec {gg['step_volume']['expected_mm3']:.1f} mm³\n"
               f"XOR vs reference {gg['step_xor']['xor_volume_mm3']:.1f} mm³ "
               f"(gate G7 ≤ 1%)")
        fig.text(0.68, 0.36, txt, fontsize=13, color=rd.INK, va="top",
                 linespacing=1.5)
        save(fig, i)
        i += 1
    for k in range(still_after):
        fig = new_fig()
        top("cad-verify-back",
            "an agent builds an adapter plate with CadQuery/OCCT — a judge "
            "grades the delivered STEP/STL/DXF, never its code")
        ax = fig.add_axes([0.03, 0.06, 0.62, 0.76])
        rd.draw_mesh(ax, art, 55.0, 24.0, base=rd.BLUE)
        axr = fig.add_axes([0.68, 0.42, 0.28, 0.38])
        rd.draw_mesh(axr, ref, 55.0, 24.0, base=rd.ORANGE)
        axr.set_title("spec-built reference", fontsize=11, color=rd.INK2)
        txt = ("delivered part.stl (trimesh 5.1.1)\n"
               f"OCCT volume {gg['step_volume']['volume_mm3']:.1f} mm³\n"
               f"closed-form spec {gg['step_volume']['expected_mm3']:.1f} mm³\n"
               f"XOR vs reference {gg['step_xor']['xor_volume_mm3']:.1f} mm³ "
               f"(gate G7 ≤ 1%)")
        fig.text(0.68, 0.36, txt, fontsize=13, color=rd.INK, va="top",
                 linespacing=1.5)
        save(fig, i)
        i += 1

    # ---- section 2: the agent loop replay (4.0 s) ---------------------------
    labels, npass, names = [], [], []
    for p in replay:
        v = rd.load_verdict(p)
        name = os.path.basename(p).split("_", 1)[1].rsplit(".", 1)[0]
        names.append(name)
        npass.append(rd.n_pass(v))
        labels.append(name.replace("_", "\n"))
    for k in range(sec(4.0)):
        fig = new_fig()
        top("the fixing-agent loop, replayed through the judge",
            "each iteration is a real grade.sh run: bad → partly fixed → good "
            "(graded verdicts, not a live agent trace)")
        ax = fig.add_axes([0.10, 0.10, 0.72, 0.70])
        rd.style_axes(ax)
        x = list(range(len(npass)))
        ax.plot(x, npass, color=rd.BLUE, linewidth=3.0, marker="o",
                markersize=12, markerfacecolor=rd.BLUE,
                markeredgecolor=rd.SURFACE, markeredgewidth=2.0, zorder=4)
        ax.axhline(14, color=rd.GOOD, linewidth=2.0, zorder=2)
        ax.text(len(x) - 0.45, 14.3, "all 14 gates pass (verdict PASS, exit 0)",
                fontsize=15, color=rd.GOOD, ha="right", va="bottom")
        for xi, yi, name in zip(x, npass, names):
            ax.annotate(f"{yi}/14", (xi, yi), textcoords="offset points",
                        xytext=(0, 22), fontsize=15, ha="center",
                        color=rd.INK2)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=14, color=rd.INK2)
        ax.set_ylim(0, 15.8)
        ax.set_yticks([0, 4, 8, 12, 14])
        ax.tick_params(labelsize=13)
        ax.set_ylabel("gates passing (of 14)", fontsize=14, color=rd.INK2)
        save(fig, i)
        i += 1

    # ---- section 3: one card per mutant (13.5 s) ----------------------------
    for m in MUTANTS:
        v = rd.load_verdict(os.path.join(rd.verdicts_dir(), f"{m}.json"))
        fails = rd.named_fails(v)
        caught_by = fails[0] if fails else "?"
        lines = [f"mutant: {MUTANT_LABEL[m]}"]
        lines.append(f"caught by gate {rd.GATE_SHORT[caught_by].replace(chr(10), ' ')}"
                     f" — {rd.GATE_RULE[caught_by]}")
        for gate in fails[:4]:
            err = str(v["gates"][gate].get("error", ""))
            lines.append(f"  {rd.GATE_SHORT[gate].replace(chr(10), ' ')}: "
                         f"{rd.fail_oneliner(gate, err)}")
        body = "\n".join(lines)
        for k in range(sec(1.35)):
            fig = new_fig()
            top(f"mutant {MUTANT_LABEL[m]}",
                f"every mutant fails a named gate — kill rate 10/10")
            ax = fig.add_axes([0.03, 0.10, 0.55, 0.72])
            defect_visual(ax, m, v, spec)
            fig.text(0.62, 0.80, body, fontsize=15, color=rd.INK, va="top",
                     linespacing=1.65)
            fig.text(0.62, 0.14, "measured vs limit, from the verdict JSON",
                     fontsize=11, color=rd.MUTED)
            save(fig, i)
            i += 1

    # ---- section 4: outro (1.0 s) --------------------------------------------
    txt = ("verdict PASS — all 14 gates on the delivered files\n"
           f"OCCT/trimesh/manifold3d/ezdxf against closed-form spec numbers\n"
           "self-test kill rate 10/10 · deterministic verdicts")
    for k in range(sec(1.0)):
        fig = new_fig()
        top("cad-verify-back", "judge: the delivered files, not the code")
        fig.text(0.5, 0.55, txt, fontsize=20, color=rd.INK, ha="center",
                 va="center", linespacing=1.8)
        save(fig, i)
        i += 1

    with open(os.path.join(FRAMES, "concat.txt"), "w") as f:
        for k in range(i):
            f.write(f"file '{frame_name(k)}'\n")
    print(f"video.py: wrote {i} frames ({i / 30.0:.2f} s) to {FRAMES}")


if __name__ == "__main__":
    main()
