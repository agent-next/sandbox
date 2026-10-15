#!/usr/bin/env python3
"""demo.mp4 frames, storyboarded to cookbook/DEMO-STANDARD.md (Media).

Slots (37.0 s at 30 fps, 1920x1080; see media/STORYBOARD.md):
  0.0-2.6   hook        - the finished real result fills the frame: the
                          delivered STL (examples/good, trimesh-parsed) on a
                          turntable, verdict caption burned in. No title card.
  2.6-10.0  input->output - the real judge/spec.json text beside the part and
                          its DXF drawing: the spec is the input, the three
                          delivered files are the output.
 10.0-14.0  escalate A  - camera zooms to the bolt circle; the spec PCD and
                          the measured centres from the verdict JSON are
                          overlaid (G5/G6 numbers on screen).
 14.0-18.5  escalate B  - the fixing-agent loop replayed at ~10x speed:
                          each point is a real grade.sh verdict JSON.
 18.5-31.5  escalate C  - the judge stressed: one card per mutant (10 x 1.3 s)
                          with the defect drawn on the mutant's own mesh/DXF
                          and the gate that caught it (measured vs limit).
 31.5-34.5  proof       - verdict PASS 14/14 + self-test kill rate 10/10 +
                          determinism, in phone-readable type.
 34.5-37.0  end card    - `python3 run.py`, static >= 2 s.

All numbers come from media/data/ (judge outputs).  Frames go to
media/data/frames/ and are encoded by make_media.sh (lossless crf-0 master
first, then the crf-18 web encode).
"""
import glob
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render as rd  # noqa: E402

from fig_loop import MUTANTS, MUTANT_LABEL  # noqa: E402

W, H = 19.2, 10.8          # inches at dpi=100 => 1920x1080
FRAMES = os.path.join(rd.DATA, "frames")
GOOD_DIR = os.path.join(os.path.dirname(rd.HERE), "examples", "good")
SPEC_PATH = os.path.join(os.path.dirname(rd.HERE), "judge", "spec.json")

FRONT = (55.0, 24.0)

# burned-in narrative captions: cap height >= 4 % of frame height means
# ~43 px at 1080p -> ~44 pt at dpi 100. Primary captions use CAP, supporting
# text uses SUB (still >= phone-readable chart label sizes elsewhere).
CAP = 44
SUB = 24


def spec_bolt_centres(spec):
    r = spec["pcd"] / 2.0
    return [(r * math.cos(2 * math.pi * i / spec["bolt_n"]),
             r * math.sin(2 * math.pi * i / spec["bolt_n"]))
            for i in range(spec["bolt_n"])]


def frame_name(i):
    return os.path.join(FRAMES, f"f{i:05d}.png")


def new_fig():
    return rd.plt.figure(figsize=(W, H), dpi=100, facecolor=rd.SURFACE)


def caption(fig, text, sub=""):
    """The burned-in narration line(s) for a scene."""
    rd.plt.figtext(0.024, 0.935, text, fontsize=CAP, fontweight="bold",
                   color=rd.INK, va="center")
    if sub:
        rd.plt.figtext(0.026, 0.855, sub, fontsize=SUB, color=rd.INK2,
                       va="center")


def save(fig, i):
    rd.assert_no_overlaps(fig, f"video frame {i}", ignore_xy=True)
    fig.savefig(frame_name(i), dpi=100, facecolor=rd.SURFACE)
    rd.plt.close(fig)


def sec(s):
    return int(round(s * 30.0))


# --------------------------------------------------------------------------
def mesh_with_holes_highlights(mesh, centres, hole_d):
    """Face indices whose triangle centroid lies inside a bolt-hole radius."""
    fc = mesh.triangles_center
    out = []
    for (cx, cy) in centres:
        d = np.hypot(fc[:, 0] - cx, fc[:, 1] - cy)
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
                color=rd.INK2, linewidth=1.8)
        for (cx, cy, d) in circles:
            ax.add_patch(rd.matplotlib.patches.Circle(
                (cx, cy), d / 2.0, fill=False, edgecolor=rd.MUTED,
                linewidth=1.6))
        drawn = [(x, y) for (x, y, d) in circles]
        for (cx, cy) in spec_bolt_centres(spec):
            if not any(math.hypot(cx - px, cy - py) < 0.02 for px, py in drawn):
                ax.add_patch(rd.matplotlib.patches.Circle(
                    (cx, cy), spec["bolt_d"] / 2.0, fill=True,
                    facecolor=rd.CRIT_WASH, edgecolor=rd.CRIT, linewidth=2.4))
        ax.set_xlim(-70, 70)
        ax.set_ylim(-46, 46)
        ax.set_aspect("equal")
        ax.text(-66, 40, "missing DXF circle", fontsize=20, color=rd.CRIT)
    elif mutant == "stl_flipped_facet":
        mesh = rd.load_stl(stl)
        rd.draw_mesh(ax, mesh, *FRONT, base=rd.BLUE, highlight={0})
    elif mutant == "stl_not_watertight":
        mesh = rd.load_stl(stl)
        rd.draw_mesh(ax, mesh, *FRONT, base=rd.BLUE)
        # the dropped facet is facet 0 of the good mesh; mark its vertices
        good_mesh = rd.load_stl(os.path.join(GOOD_DIR, "part.stl"))
        tri = good_mesh.vertices[good_mesh.faces[0]]
        Rm = rd.rot_ypr(*FRONT)
        p = tri @ Rm.T
        ax.plot(list(p[:, 0]) + [p[0, 0]], list(p[:, 1]) + [p[0, 1]],
                color=rd.CRIT, linewidth=4.5, marker="o", markersize=7.0,
                zorder=6, markerfacecolor=rd.CRIT, markeredgecolor="white")
        ax.text(p[:, 0].mean(), p[:, 1].mean() + 7, "dropped facet",
                fontsize=20, color=rd.CRIT, zorder=7, ha="center")
    elif mutant == "tangential_hole_drift":
        mesh = rd.load_stl(stl)
        cents = v["gates"]["step_holes"].get("bolt_centres") or []
        if cents:
            hl = mesh_with_holes_highlights(mesh, cents, spec["bolt_d"])
            rd.draw_mesh(ax, mesh, *FRONT, base=rd.BLUE, highlight=set(hl))
        else:
            rd.draw_mesh(ax, mesh, *FRONT, base=rd.BLUE)
        # drift arrows: expected -> measured centre, on the top face
        Rm = rd.rot_ypr(*FRONT)
        good_c = spec_bolt_centres(spec)
        for (cx, cy) in cents:
            best = min(good_c, key=lambda c: math.hypot(c[0] - cx, c[1] - cy))
            if math.hypot(best[0] - cx, best[1] - cy) > 0.1:
                p0 = np.array([best[0], best[1], spec["plate_t"]]) @ Rm.T
                p1 = np.array([cx, cy, spec["plate_t"]]) @ Rm.T
                ax.annotate("", xy=(p1[0], p1[1]), xytext=(p0[0], p0[1]),
                            arrowprops=dict(arrowstyle="->", lw=3.0,
                                            color=rd.CRIT), zorder=6)
    else:
        mesh = rd.load_stl(stl)
        gg = v["gates"]
        hl = set()
        if "step_holes" in gg and gg["step_holes"].get("bolt_centres"):
            cents = gg["step_holes"]["bolt_centres"]
            if len(cents):
                hl = set(mesh_with_holes_highlights(mesh, cents,
                                                    spec["bolt_d"]))
        rd.draw_mesh(ax, mesh, *FRONT, base=rd.BLUE, highlight=hl)


def mutant_card(k_of, m, v, spec):
    """One mutant card. k_of = (index, total) for the 'mutant k/10' header."""
    k, total = k_of
    fails = rd.named_fails(v)
    caught_by = fails[0] if fails else "?"
    cap = f"mutant {k}/{total}: {MUTANT_LABEL[m].replace('_', ' ')}"
    sub = (f"caught by {rd.GATE_SHORT[caught_by].splitlines()[0]} "
           f"{caught_by} — {rd.GATE_RULE[caught_by]}")
    fig = new_fig()
    caption(fig, cap, sub)
    ax = fig.add_axes([0.03, 0.07, 0.55, 0.74])
    defect_visual(ax, m, v, spec)
    ax.set_title("delivered files, mutated (shown: "
                 + ("part.dxf" if m == "dxf_missing_hole" else "part.stl") + ")",
                 fontsize=15, color=rd.MUTED, pad=6)
    lines = []
    for gate in fails[:5]:
        err = str(v["gates"][gate].get("error", ""))
        lines.append(f"{rd.GATE_SHORT[gate].splitlines()[0]} "
                     f"{rd.fail_oneliner(gate, err)}")
    fig.text(0.62, 0.74, "fails on its own evidence:\n\n" + "\n".join(lines),
             fontsize=SUB, color=rd.INK, va="top", linespacing=1.7)
    fig.text(0.62, 0.14, "measured vs limit, parsed from the verdict JSON",
             fontsize=16, color=rd.MUTED)
    return fig


def main():
    os.makedirs(FRAMES, exist_ok=True)
    for f in glob.glob(os.path.join(FRAMES, "*.png")):
        os.remove(f)

    spec = rd.spec()
    with open(SPEC_PATH) as f:
        spec_text = f.read().strip()
    vgood = rd.load_verdict(os.path.join(rd.verdicts_dir(), "good.json"))
    gg = vgood["gates"]
    replay = sorted(glob.glob(os.path.join(rd.DATA, "replay", "iter*.json")))

    art = rd.load_stl(os.path.join(GOOD_DIR, "part.stl"))
    i = 0

    # ---- 0.0-2.6 s: hook — the finished real result fills the frame --------
    n_hook = sec(2.6)
    for k in range(n_hook):
        yaw = 55.0 + 90.0 * k / n_hook
        fig = new_fig()
        ax = fig.add_axes([0.0, 0.0, 1.0, 1.0])
        rd.draw_mesh(ax, art, yaw, 24.0, base=rd.BLUE, zoom=0.82)
        fig.text(0.03, 0.06, "verdict PASS — 14/14 gates on the "
                 "delivered files", fontsize=40, fontweight="bold",
                 color=rd.INK, va="bottom",
                 bbox=dict(facecolor=rd.SURFACE, edgecolor=rd.GOOD,
                           linewidth=2.0, boxstyle="round,pad=0.45"))
        fig.text(0.03, 0.955, "cad-verify-back", fontsize=SUB, color=rd.INK2,
                 va="top")
        save(fig, i)
        i += 1

    # ---- 2.6-10.0 s: input -> output ---------------------------------------
    for k in range(sec(7.4)):
        fig = new_fig()
        caption(fig, "in: spec.json — out: part.step · part.stl · part.dxf",
                "the judge grades the delivered files, never the agent's code")
        axL = fig.add_axes([0.035, 0.10, 0.26, 0.68])
        axL.set_axis_off()
        axL.text(0.0, 1.0, spec_text, fontsize=17, family="monospace",
                 color=rd.INK, va="top", linespacing=1.75,
                 bbox=dict(facecolor="white", edgecolor=rd.BASELINE,
                           linewidth=1.2, boxstyle="round,pad=0.5"))
        axL.set_title("judge/spec.json — the only input", fontsize=17,
                      color=rd.INK2, pad=8)
        fig.text(0.315, 0.45, "→", fontsize=60, color=rd.ORANGE,
                 ha="center", va="center", fontweight="bold")
        axM = fig.add_axes([0.36, 0.09, 0.34, 0.70])
        rd.draw_mesh(axM, art, 55.0, 24.0, base=rd.BLUE)
        axM.set_title("part.stl (the delivered file)", fontsize=17,
                      color=rd.INK2, pad=8)
        axD = fig.add_axes([0.72, 0.12, 0.25, 0.64])
        outline, circles = rd.dxf_circles(os.path.join(GOOD_DIR, "part.dxf"))
        xs = [p[0] for p in outline] + [outline[0][0]]
        ys = [p[1] for p in outline] + [outline[0][1]]
        axD.plot(xs, ys, color=rd.INK2, linewidth=1.4)
        for (cx, cy, d) in circles:
            axD.add_patch(rd.matplotlib.patches.Circle(
                (cx, cy), d / 2.0, fill=False, edgecolor=rd.MUTED,
                linewidth=1.1))
        axD.set_xlim(-68, 68)
        axD.set_ylim(-52, 52)
        axD.set_aspect("equal")
        axD.set_xticks([])
        axD.set_yticks([])
        for s in axD.spines.values():
            s.set_color(rd.BASELINE)
        axD.set_title("part.dxf (the delivered drawing)", fontsize=17,
                      color=rd.INK2, pad=8)
        save(fig, i)
        i += 1

    # ---- 10.0-14.0 s: escalate A — bolt-circle close-up --------------------
    cents = gg["step_holes"]["bolt_centres"]
    pcd_max = max(gg["step_pcd"]["max_radial_err_mm"],
                  gg["step_pcd"]["max_pos_err_mm"])
    n_z = sec(4.0)
    for k in range(n_z):
        zoom = 1.05 + 0.75 * k / n_z          # 1.05 -> 1.8, slow push-in
        yaw = 55.0 + 18.0 * k / n_z
        fig = new_fig()
        caption(fig, "the judge measures the delivered geometry",
                f"G5 PCD err {pcd_max:g} mm ≤ 0.02 mm · G6 angular dev "
                f"{gg['angular_spacing']['max_deviation_deg']:g}° ≤ 0.05°")
        ax = fig.add_axes([0.16, 0.02, 0.68, 0.78])
        Rm = rd.draw_mesh(ax, art, yaw, 24.0, base=rd.BLUE, zoom=zoom)
        # spec PCD + measured centres projected into the same view
        t = np.linspace(0, 2 * math.pi, 121)
        ring = np.stack([spec["pcd"] / 2.0 * np.cos(t),
                         spec["pcd"] / 2.0 * np.sin(t),
                         np.full_like(t, spec["plate_t"])], axis=1)
        pr = ring @ Rm.T
        ax.plot(pr[:, 0], pr[:, 1], color=rd.ORANGE, linewidth=2.4,
                linestyle=(0, (5, 3)), zorder=5)
        pts = np.array([[c[0], c[1], spec["plate_t"]] for c in cents]) @ Rm.T
        ax.plot(pts[:, 0], pts[:, 1], "o", markersize=10, color=rd.ORANGE,
                markeredgecolor="white", markeredgewidth=1.4, zorder=6)
        save(fig, i)
        i += 1

    # ---- 14.0-18.5 s: escalate B — the agent loop at ~10x speed ------------
    labels, npass = [], []
    for p in replay:
        v = rd.load_verdict(p)
        npass.append(rd.n_pass(v))
        labels.append(os.path.basename(p).split("_", 1)[1]
                      .rsplit(".", 1)[0].replace("_", "\n"))
    n_rep = sec(4.5)
    per = max(1, n_rep // len(npass))
    for k in range(n_rep):
        shown = min(len(npass), 1 + k // per)
        fig = new_fig()
        caption(fig, "the fixing loop, replayed — ~10× speed",
                "each point is a real grade.sh verdict (replayed, not a live "
                "trace)")
        ax = fig.add_axes([0.09, 0.08, 0.72, 0.70])
        rd.style_axes(ax)
        x = list(range(len(npass)))
        ax.plot(x, [14] * len(x), color=rd.GRID, linewidth=2.0, zorder=1)
        ax.axhline(14, color=rd.GOOD, linewidth=2.2, zorder=2)
        ax.plot(x[:shown], npass[:shown], color=rd.BLUE, linewidth=3.4,
                marker="o", markersize=15, markerfacecolor=rd.BLUE,
                markeredgecolor=rd.SURFACE, markeredgewidth=2.2, zorder=4)
        for xi, yi in zip(x[:shown], npass[:shown]):
            ax.annotate(f"{yi}/14", (xi, yi), textcoords="offset points",
                        xytext=(0, 26 if yi < 14 else -36), fontsize=20,
                        ha="center", color=rd.INK2)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=17, color=rd.INK2)
        ax.set_ylim(0, 15.9)
        ax.set_yticks([0, 4, 8, 12, 14])
        ax.tick_params(labelsize=16)
        ax.set_ylabel("gates passing (of 14)", fontsize=18, color=rd.INK2)
        save(fig, i)
        i += 1

    # ---- 18.5-31.5 s: escalate C — one card per mutant ----------------------
    for k, m in enumerate(MUTANTS):
        v = rd.load_verdict(os.path.join(rd.verdicts_dir(), f"{m}.json"))
        for _ in range(sec(1.3)):
            fig = mutant_card((k + 1, len(MUTANTS)), m, v, spec)
            save(fig, i)
            i += 1

    # ---- 31.5-34.5 s: proof — verdict + kill matrix --------------------------
    for k in range(sec(3.0)):
        fig = new_fig()
        caption(fig, "verdict: PASS — all 14 gates, deterministic",
                "self-test: every scripted mutant is caught — kill rate 10/10")
        # mini kill matrix: real per-gate verdicts, big enough to read
        axm = fig.add_axes([0.06, 0.09, 0.88, 0.62])
        rows = ["good"] + MUTANTS
        n_r, n_c = len(rows), len(rd.GATE_ORDER)
        axm.set_xlim(0, n_c + 2.6)
        axm.set_ylim(0, n_r)
        axm.invert_yaxis()
        for j, gate in enumerate(rd.GATE_ORDER):
            axm.text(j + 0.5, -0.55, rd.GATE_SHORT[gate].splitlines()[0],
                     fontsize=15, color=rd.INK2, ha="center", va="bottom")
        for ridx, row in enumerate(rows):
            vv = vgood if row == "good" else rd.load_verdict(
                os.path.join(rd.verdicts_dir(), f"{row}.json"))
            axm.text(n_c + 0.15, ridx + 0.5, row.replace("_", " "),
                     fontsize=13.5, color=rd.INK, ha="left", va="center")
            for j, gate in enumerate(rd.GATE_ORDER):
                gcell = vv["gates"][gate]
                err = str(gcell.get("error", ""))
                if gcell["pass"]:
                    fc = rd.GOOD_WASH
                elif err.startswith("skipped"):
                    fc = rd.SKIP_WASH
                else:
                    fc = rd.CRIT
                axm.add_patch(rd.matplotlib.patches.Rectangle(
                    (j + 0.06, ridx + 0.14), 0.88, 0.72, facecolor=fc,
                    edgecolor=rd.SURFACE, linewidth=1.0))
        axm.set_xticks([])
        axm.set_yticks([])
        for s in axm.spines.values():
            s.set_visible(False)
        save(fig, i)
        i += 1

    # ---- 34.5-37.0 s: end card — static >= 2 s -------------------------------
    for k in range(sec(2.5)):
        fig = new_fig()
        fig.text(0.5, 0.62, "python3 run.py", fontsize=64, fontweight="bold",
                 color=rd.INK, ha="center", va="center", family="monospace")
        fig.text(0.5, 0.44,
                 "or ask your agent: “design the plate in judge/spec.json — "
                 "the judge grades what you deliver”",
                 fontsize=SUB, color=rd.INK2, ha="center", va="center")
        fig.text(0.5, 0.30, "cookbook/cad-verify-back", fontsize=20,
                 color=rd.MUTED, ha="center", va="center")
        save(fig, i)
        i += 1

    # concat demuxer needs an explicit per-frame duration, else it treats
    # each still as 0 s and the encoder drops all but the first few frames
    with open(os.path.join(FRAMES, "concat.txt"), "w") as f:
        for k in range(i):
            f.write(f"file '{frame_name(k)}'\nduration {1.0 / 30.0:.6f}\n")
    print(f"video.py: wrote {i} frames ({i / 30.0:.2f} s) to {FRAMES}")


if __name__ == "__main__":
    main()
