"""result.png - the good controller under the judge's spec envelope.

Top: hero still - one MuJoCo frame of the good controller's scenario-1
replay, frozen at the measured theta settle time, with the numbers and
the pass line overlaid by render3d.py. The render is a kinematic replay
of the judge's own --trace CSV, never re-simulated.
Bottom-left: the gate table with measured values from the verdict JSON.
Bottom-right: the Monte-Carlo panel - 200 real per-sample settle times
(theta from the lean run, x from the displacement run) against the
per-sample gate limits.
"""

import os

import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

import common as c
import render3d as r3

plt = c.rc_params()

V = c.verdict("good")
g = V["gates"]

# ------------------------------------------------------------- top: hero
fig = plt.figure(figsize=(13, 12.6), dpi=200)
gs = fig.add_gridspec(2, 2, height_ratios=[1.62, 1.0], width_ratios=[1, 1],
                      left=0.065, right=0.985, top=0.935, bottom=0.100,
                      wspace=0.20, hspace=0.34)

t_settle = g["s1_theta_settle_s"]["value"]
rep, info = r3.make("good", 1, camera="hero34")
hero = rep.frame(t_settle, info, label="good")
rep.close()

axh = fig.add_subplot(gs[0, :])
axh.imshow(hero)
axh.set_xticks([])
axh.set_yticks([])
for s in axh.spines.values():
    s.set_color(c.AXIS)
    s.set_linewidth(1.0)
axh.set_title(
    "hero frame - MuJoCo render of the judged S1 trace, frozen at the "
    f"measured settle time ({t_settle:.2f} s)",
    fontsize=12.5, color=c.INK, pad=8)

# ---------------------------------------------------------- bottom-left: table
axt = fig.add_subplot(gs[1, 0])
axt.axis("off")
NPASS = sum(gg["pass"] for gg in g.values())
axt.set_title(f"Judge verdict - good controller "
              f"({NPASS}/{len(g)} gates pass)",
              fontsize=12.5, color=c.INK, pad=10)
rows = [
    ("design_stable", "max Re(λ) of $A-BK$", f"{g['design_stable']['value']:.4f}",
     "< -0.05"),
    ("s1_theta_settle_s", "S1 θ settling time", f"{g['s1_theta_settle_s']['value']:.2f} s",
     "≤ 5 s"),
    ("s1_x_settle_s", "S1 x settling time", f"{g['s1_x_settle_s']['value']:.2f} s",
     "≤ 5 s"),
    ("s1_tau_demand_max_Nm", "S1 peak |τ| demand", f"{g['s1_tau_demand_max_Nm']['value']:.3f} N·m",
     "≤ 1 N·m"),
    ("s2_x_settle_s", "S2 x settling time", f"{g['s2_x_settle_s']['value']:.2f} s",
     "≤ 7 s"),
    ("s2_peak_theta_rad", "S2 peak |θ|", f"{g['s2_peak_theta_rad']['value']:.4f} rad",
     "≤ 0.5 rad"),
    ("s2_F_demand_max_N", "S2 peak |F| demand", f"{g['s2_F_demand_max_N']['value']:.3f} N",
     "≤ 10 N"),
    ("gm_force_db", "gain margin, force loop", f"{g['gm_force_db']['value']:.0f} dB",
     "≥ 6 dB"),
    ("gm_torque_db", "gain margin, torque loop", f"{g['gm_torque_db']['value']:.0f} dB",
     "≥ 6 dB"),
    ("pm_force_deg", "phase margin, force loop", f"{g['pm_force_deg']['value']:.1f}°",
     "≥ 45°"),
    ("pm_torque_deg", "phase margin, torque loop", f"{g['pm_torque_deg']['value']:.1f}°",
     "≥ 45°"),
    ("mc_pass_fraction", "Monte-Carlo pass fraction", f"{V['mc_pass']}/{V['mc_n']}",
     "≥ 95 %"),
]
y0, dy = 0.955, 0.049
axt.text(0.01, y0 + 0.052, "gate", fontsize=10, color=c.MUTED, va="center")
axt.text(0.40, y0 + 0.052, "measured", fontsize=10, color=c.MUTED, va="center")
axt.text(0.58, y0 + 0.052, "rule", fontsize=10, color=c.MUTED, va="center")
axt.text(0.76, y0 + 0.052, "result", fontsize=10, color=c.MUTED, va="center")
for i, (_, label, val, rule) in enumerate(rows):
    yy = y0 - (i + 1) * dy
    if i % 2 == 0:
        axt.add_patch(Rectangle((0.0, yy - dy / 2 + 0.011), 1.0, dy - 0.022,
                                transform=axt.transAxes, facecolor="#f4f3f0",
                                edgecolor="none", zorder=1))
    axt.text(0.01, yy, label, fontsize=10.5, color=c.INK, va="center", zorder=2)
    axt.text(0.40, yy, val, fontsize=10.5, color=c.INK2, va="center", zorder=2)
    axt.text(0.58, yy, rule, fontsize=10.5, color=c.INK2, va="center", zorder=2)
    axt.text(0.77, yy, "PASS", fontsize=10, color=c.GOOD, fontweight="bold",
             va="center", zorder=2)
axt.set_xlim(0, 1)
axt.set_ylim(0, 1.06)

# -------------------------------------------------- bottom-right: MC panel
# one dot per perturbed plant: x settle (x-axis) vs theta settle (y-axis).
# A sample passes only if it sits left of the 7 s x-limit AND below the
# 8 s theta-limit, so the limits are drawn as axis-aligned pass lines.
axm = fig.add_subplot(gs[1, 1])
mc = c.mc_samples("good")
th_s = np.array([r[4] for r in mc])
x_s = np.array([r[5] for r in mc])
axm.scatter(x_s, th_s, s=15, color=c.BLUE, alpha=0.45, linewidths=0,
            zorder=3)
axm.axvline(c.MC_X_SETTLE_MAX, color=c.CRIT, lw=1.6, zorder=2)
axm.axhline(c.MC_THETA_SETTLE_MAX, color=c.CRIT, lw=1.6, zorder=2)
axm.text(c.MC_X_SETTLE_MAX - 0.12, 0.30,
         "x settle limit 7 s\n(displacement run)",
         fontsize=10, color=c.CRIT, va="bottom", ha="right")
axm.text(c.MC_X_SETTLE_MAX - 0.15, c.MC_THETA_SETTLE_MAX - 0.25,
         "θ settle limit 8 s (lean run)",
         fontsize=10, color=c.CRIT, va="top", ha="right")
frac = g["mc_pass_fraction"]["value"]
axm.text(0.25, 2.20,
         f"{V['mc_pass']}/{V['mc_n']} samples pass both runs\n"
         f"gate: ≥ 95 % of 200 - measured {frac:.3f}\n"
         f"worst θ settle {V['mc_theta_settle_worst_s']:.2f} s (lean run), "
         f"worst x settle {V['mc_x_settle_worst_s']:.2f} s",
         fontsize=10, color=c.INK2, va="top", ha="left")
axm.set_title("Monte-Carlo gate - ±20 % plant perturbation, 200 runs",
              fontsize=12.5, color=c.INK, pad=8)
axm.set_xlabel("x settling time (s)", fontsize=11.5, color=c.INK2)
axm.set_ylabel("θ settling time (s)", fontsize=11.5, color=c.INK2)
axm.set_xlim(0, 7.7)
axm.set_ylim(0, 8.55)
c.style_axis(axm)
handles = [
    Line2D([], [], marker="o", ls="", ms=6, mfc=c.BLUE, mec=c.SURFACE,
           mew=1, label="one perturbed plant (both spec runs)"),
]
leg = axm.legend(handles=handles, loc="upper left",
                 bbox_to_anchor=(0.02, 0.81), fontsize=10,
                 frameon=True, facecolor=c.SURFACE, edgecolor=c.GRID)
leg.get_texts()[0].set_color(c.INK2)
axm.text(0.02, 0.87, "dots must sit left of / below the red limits",
         transform=axm.transAxes, fontsize=9.5, color=c.CRIT, va="top")

fig.suptitle("LQR cart-pole under the judge's spec envelope - all gates pass",
             fontsize=15, color=c.INK, x=0.065, ha="left", y=0.978)
c.caption(fig, "The hero frame is the simulator's own 3-D render (MuJoCo "
          "mujoco.Renderer, kinematic replay of media/data/good/"
          "s1_trace.csv written by judge/grade.sh, seed 20260101) frozen "
          "at the measured θ settle time; the overlay numbers come from "
          "the same CSV row, and the settle band strip on the rail marks "
          "±0.01 m around x = 0. Gate values are read from the verdict "
          "JSON; gain margins are unlimited (99 dB = judge sentinel for "
          "\"no crossing of any odd multiple of 180° in the 0.01-1000 "
          "rad/s sweep\").")
c.check_layout(fig)
fig.savefig(os.path.join(c.MEDIA, "result.png"), dpi=200)
print("result.png written")
