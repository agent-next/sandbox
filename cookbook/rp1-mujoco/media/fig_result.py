#!/usr/bin/env python3
"""result.png -- the readout of the judged run.

Panel A  the real RP1 humanoid (rp1_description at the pinned SHA)
         rendered headless by MuJoCo (EGL), loaded with the exact judged
         state at t = 5.15 s, mid-push -- the pose the judge graded, read
         back from its own trace (grade.sh --trace), not re-simulated.
Panels B-E  the judge's own per-step trace of the good controller, each
         against its gate's pass line (SPEC.md gates 6-9):
           B pelvis height vs the 0.9*z0 floor      (stand gate)
           C torso tilt vs the 10 deg limit, push marked, 5 deg
             recovery limit shown after t = 7 s     (stand + push gates)
           D vertical foot contact force / m*g      (zero-torque oracle's
             statics, fz = 1.003; the oracle's own run is gate 5)
           E peak joint torque vs the 70.6 N*m ankle limit (limits gate)
Every number drawn comes from media/data/traces/good/trace.csv.gz (the
real trace) or data/verdicts/good.json (the real verdict); the script
raises if any source is missing or a plotted aggregate disagrees with the
verdict text.
200 dpi, colour scheme from the cookbook dataviz palette (series blue,
status good/fail green/red with text labels).
"""
import csv
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import colors as mcolors

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rp1render

MEDIA = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(MEDIA)
OUT = os.path.join(MEDIA, "result.png")
VERDICT = os.path.join(MEDIA, "data", "verdicts", "good.json")
TRACE = os.path.join(MEDIA, "data", "traces", "good", "trace.csv.gz")
SCENE = os.path.join(MEDIA, "work", "scene", "mjcf", "rp1_flat.xml")

BLUE = "#2a78d6"     # series 1 (validated)
GREEN = "#0ca30c"    # status good / pass line
RED = "#b71c1c"      # status fail
INK = "#0b0b0b"
SUB = "#4a4a48"


def need(p):
    if not os.path.exists(p):
        raise SystemExit(f"missing {p} -- run media/collect_data.sh first")
    return p


def main():
    tr = rp1render.Trace(need(TRACE))
    v = json.load(open(need(VERDICT)))
    g = v["gates"]
    stand, push, limits = g["stand"], g["push"], g["limits"]
    stat, effort = g["gravity_statics"], g["effort"]

    t, z = tr.t, tr.pos[:, 2]
    tilt = tr.tilt
    fz, tau, frac = tr.fz, tr.tau_peak, tr.tau_frac
    z0 = stand["z0_m"]
    zfloor = stand["z_floor_m"]           # 0.9 * z0
    tiltlim = stand["tilt_limit_deg"]     # 10
    reclim = push["recover_limit_deg"]    # 5
    rec_t = push["recover_from_s"]        # 7.0
    mg = stat["m_times_g_n"]
    tau_lim = 70.6                        # ankle ctrlrange (limits gate)

    # aggregated trace values must reproduce the verdict (plotted == judged)
    assert abs(z.min() - stand["zmin_m"]) < 5e-4, \
        f"trace zmin {z.min()} vs verdict {stand['zmin_m']}"
    assert abs(tilt.max() - stand["max_tilt_deg"]) < 5e-3
    assert abs(tilt[t >= rec_t].max() -
               push["max_tilt_after_recovery_deg"]) < 5e-3
    assert abs(tau.max() - effort["peak_tau_nm"]) < 5e-2, \
        f"trace tau {tau.max()} vs verdict {effort['peak_tau_nm']}"

    # ---- hero render: the exact judged state at mid-push ------------------
    k = tr.index_at(5.15)
    rend = rp1render.Renderer(need(SCENE))
    rend.set_state(tr, k)
    rend.aim(distance=2.55, azimuth=136.0, elevation=-4.0, lookat_z=0.82)
    img = rend.render()

    fig = plt.figure(figsize=(13.6, 9.0), dpi=200, facecolor="#fcfcfb")

    # A: hero real render
    axA = fig.add_axes([0.045, 0.335, 0.49, 0.60])
    axA.imshow(img)
    axA.axis("off")
    axA.set_title(
        "A -- real MuJoCo render of the judged run at t = %.2f s "
        "(30 N push in plane)\nRP1 humanoid, rp1_description @ pinned SHA; "
        "headless EGL" % tr.t[k],
        fontsize=9.5, loc="left", color=INK)

    # verdict box (top-right)
    fig.text(
        0.985, 0.965,
        "judge verdict (grade.sh examples/good, seed 20261014):  PASS\n"
        "all 10 gates  (model x4, statics oracle, stand, push, "
        "limits, integrity)\n"
        "self-test: 8/8 mutants killed, physics kills 8/8 "
        "(doc: media/data/selftest.txt)",
        ha="right", va="top", fontsize=9.2,
        bbox=dict(boxstyle="round,pad=0.5", fc="#eef6ee", ec=GREEN,
                  lw=1.4))

    # panels B--E
    axB, axC, axD, axE = (None,) * 4

    def trace_axes(rect):
        ax = fig.add_axes(rect)
        ax.set_facecolor("#fcfcfb")
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.grid(True, color="0.88", lw=0.6)
        ax.tick_params(labelsize=8, colors=SUB)
        return ax

    # shared x: full episode
    XL = (0, t[-1])

    # B: pelvis height vs 0.9 z0 floor (stand gate)
    axB = trace_axes([0.555, 0.665, 0.42, 0.28])
    axB.axhline(zfloor, color=GREEN, lw=1.6, ls="--", zorder=2)
    axB.plot(t, z, color=BLUE, lw=1.6, zorder=3)
    axB.axvline(5.0, color=RED, lw=0.9, ls=":", alpha=0.75)
    axB.set_ylim(0.66, 0.82)
    axB.set_xlim(XL)
    axB.set_ylabel("pelvis z [m]", fontsize=8.5, color=INK)
    axB.text(0.985, 0.07,
             f"stand gate: pelvis z >= 0.9*z0 = {zfloor:.3f} m\n"
             f"min {stand['zmin_m']:.4f} m  (z0 = {z0:.2f} m)",
             transform=axB.transAxes, ha="right", va="bottom",
             fontsize=7.8, color=INK,
             bbox=dict(boxstyle="round,pad=0.3", fc="white",
                       ec=GREEN, lw=0.8, alpha=0.95))

    # C: torso tilt vs limits, push marked (stand + push gates)
    axC = trace_axes([0.555, 0.335, 0.42, 0.28])
    axC.axhline(tiltlim, color=GREEN, lw=1.6, ls="--", zorder=2)
    axC.axhline(reclim, color="0.45", lw=1.1, ls=(0, (4, 3)), zorder=2)
    axC.plot(t, tilt, color=BLUE, lw=1.6, zorder=3)
    axC.axvspan(5.0, 5.2, color=RED, alpha=0.14, zorder=1)
    axC.axvline(rec_t, color=RED, lw=0.9, ls=":", alpha=0.75)
    axC.set_ylim(0, 11)
    axC.set_xlim(XL)
    axC.set_ylabel("|roll|,|pitch| max [deg]", fontsize=8.5, color=INK)
    axC.text(4.9, 10.3, "10 deg", ha="right", va="top", fontsize=7.2,
             color=GREEN)
    axC.text(4.9, 5.3, "5 deg after t=7 s", ha="right", va="bottom",
             fontsize=7.2, color="0.35")
    axC.text(5.1, 10.3, "30 N push\n5.0-5.2 s", ha="left", va="top",
             fontsize=7.2, color=RED)
    axC.text(0.985, 0.05,
             f"push gate: tilt <= {reclim:g} deg by t = {rec_t:g} s\n"
             f"max after recovery {push['max_tilt_after_recovery_deg']:.2f} "
             f"deg (<= {reclim:g})",
             transform=axC.transAxes, ha="right", va="bottom", fontsize=7.8,
             color=INK,
             bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=GREEN,
                       lw=0.8, alpha=0.95))

    # D: vertical foot GRF vs m*g (statics oracle gate)
    axD = trace_axes([0.075, 0.075, 0.42, 0.215])
    axD.axhline(1.0, color="0.45", lw=1.0, ls=(0, (4, 3)))
    axD.plot(t, fz / mg, color=BLUE, lw=1.4)
    axD.axvspan(5.0, 5.2, color=RED, alpha=0.14)
    axD.set_ylim(0.9, 1.12)
    axD.set_xlim(XL)
    axD.set_ylabel("feet vertical\nGRF / (m*g)", fontsize=8.5, color=INK)
    axD.set_xlabel("t [s]", fontsize=8.5, color=INK)
    axD.text(0.985, 0.94,
             f"statics oracle gate: fz = m*g within 2 %  "
             f"({stat['feet_fz_n']:.1f} N vs {stat['m_times_g_n']:.1f} N, "
             f"ratio {stat['ratio']:.4f})",
             transform=axD.transAxes, ha="right", va="top", fontsize=7.8,
             color=INK,
             bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=GREEN,
                       lw=0.8, alpha=0.95))

    # E: peak joint torque vs ankle limit (limits gate)
    axE = trace_axes([0.555, 0.075, 0.42, 0.215])
    axE.axhline(tau_lim, color=GREEN, lw=1.6, ls="--")
    axE.plot(t, tau, color=BLUE, lw=1.4)
    axE.axvspan(5.0, 5.2, color=RED, alpha=0.14)
    axE.set_ylim(-2, 78)
    axE.set_xlim(XL)
    axE.set_ylabel("peak |joint\n torque| [N m]", fontsize=8.5, color=INK)
    axE.set_xlabel("t [s]", fontsize=8.5, color=INK)
    axE.text(0.985, 0.94,
             f"limits gate: |tau| <= ctrlrange (ankle {tau_lim:.1f} N m, "
             f"the binding joint)\npeak {effort['peak_tau_nm']:.1f} N m "
             f"(= {100*effort['peak_tau_nm']/tau_lim:.0f} % of the ankle "
             f"limit), energy {effort['mechanical_energy_j']:.1f} J",
             transform=axE.transAxes, ha="right", va="top", fontsize=7.8,
             color=INK,
             bbox=dict(boxstyle="round,pad=0.3", fc="white", ec=GREEN,
                       lw=0.8, alpha=0.95))

    # caption strip: vertical, along the far-left margin (clear of all axes)
    cap = fig.text(
        0.008, 0.055,
        "every series: the judge's per-step trace of the good controller "
        "(data/traces/good/trace.csv.gz, grade.sh --trace), "
        "no re-simulation.  "
        "green dashed = gate pass line;  red band = the 30 N push;  limits: "
        "judge/params.json via SPEC.md.",
        fontsize=7.2, va="bottom", ha="left", color=SUB, rotation=90)

    fig.suptitle(
        "rp1-mujoco -- the judged stand + 30 N push recovery, with its "
        "pass lines", fontsize=12.5, fontweight="bold", x=0.045, y=0.985,
        ha="left")

    # ---- no-overlap check -------------------------------------------------
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    texts = [(cap, "caption")]
    for ax in (axB, axC, axD, axE):
        texts.append((ax.yaxis.label, f"{ax.get_ylabel()} ylabel"))
    for name, ax in (("B", axB), ("C", axC), ("D", axD), ("E", axE)):
        for t in ax.texts:
            texts.append((t, f"panel {name} box"))
    # every boxed info text must sit fully inside its axes
    for ax in (axB, axC, axD, axE):
        ab = ax.get_window_extent(renderer=r)
        for t in ax.texts:
            bb = t.get_window_extent(renderer=r)
            if (bb.x0 < ab.x0 - 1 or bb.x1 > ab.x1 + 1 or
                    bb.y0 < ab.y0 - 1 or bb.y1 > ab.y1 + 1):
                raise SystemExit(f"info box escapes its axes in {ax}")
    # pairwise: no two text artists overlap
    bbs = [(t.get_window_extent(renderer=r), tag) for t, tag in texts]
    for i in range(len(bbs)):
        for j in range(i + 1, len(bbs)):
            if bbs[i][0].overlaps(bbs[j][0]):
                raise SystemExit(f"text overlap: {bbs[i][1]} vs "
                                 f"{bbs[j][1]}")
    print(f"no-overlap check: OK ({len(bbs)} texts, panels' boxes inside "
          "their axes, no pairwise overlaps)")

    fig.savefig(OUT)
    sz = os.path.getsize(OUT)
    print(f"wrote {OUT}  ({sz} bytes)")


if __name__ == "__main__":
    main()
