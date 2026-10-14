"""result.png - the good controller under the judge's spec envelope.

Top: the two nonlinear scenarios the judge grades (real --trace CSVs) with
the spec envelope - settling bands, settling limits, actuator limits.
Bottom-left: the gate table with measured values from the verdict JSON.
Bottom-right: the Monte-Carlo panel - 200 real per-sample settle times
against the per-sample gate limits.
"""

import os

import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

import common as c

plt = c.rc_params()

V = c.verdict("good")
g = V["gates"]

# ---------------------------------------------------------------- top: traces
fig = plt.figure(figsize=(13, 8.6), dpi=200)
gs = fig.add_gridspec(2, 2, height_ratios=[1, 1.06], width_ratios=[1, 1],
                      left=0.065, right=0.985, top=0.895, bottom=0.140,
                      wspace=0.20, hspace=0.44)

ax1 = fig.add_subplot(gs[0, 0])
t1, x1, _, th1, _, F1, tau1 = c.trace("good", 1)
ax1.plot(t1, th1, color=c.BLUE, lw=2.0, zorder=3,
         label=r"$\theta$ (pendulum angle)")
ax1.axhline(c.S1_THETA_BAND, color=c.GOOD, lw=1.2, zorder=2)
ax1.axhline(-c.S1_THETA_BAND, color=c.GOOD, lw=1.2, zorder=2)
ax1.fill_between([-0.15, 10.15], -c.S1_THETA_BAND, c.S1_THETA_BAND,
                 color=c.GOOD, alpha=0.08, zorder=1)
ts = g["s1_theta_settle_s"]["value"]
ax1.plot([ts], [c.S1_THETA_BAND], "o", ms=9, color=c.BLUE,
         markeredgecolor=c.SURFACE, markeredgewidth=2, zorder=4)
ax1.annotate(f"settles {ts:.2f} s into the ±0.003 rad band\n"
             f"(gate: settle ≤ {c.S1_SETTLE_MAX:.0f} s)",
             xy=(ts, c.S1_THETA_BAND), xytext=(3.1, 0.064),
             fontsize=10.5, color=c.INK2,
             arrowprops=dict(arrowstyle="-", color=c.AXIS, lw=1))
ax1.set_xlabel("time (s)", fontsize=11.5, color=c.INK2)
ax1.set_ylabel(r"$\theta$ (rad)", fontsize=11.5, color=c.INK2)
ax1.set_title("Scenario 1 - recover from a 0.15 rad lean",
              fontsize=12.5, color=c.INK, pad=8)
ax1.set_xlim(-0.15, 10.15)
ax1.set_ylim(-0.008, 0.166)
c.style_axis(ax1)
leg = ax1.legend(loc="upper right", fontsize=10, frameon=True,
                 facecolor=c.SURFACE, edgecolor=c.GRID)
leg.get_texts()[0].set_color(c.INK2)
ax1.text(0.02, 0.975, "gate: 2 % settle of θ (band ±0.003 rad) ≤ 5 s",
         transform=ax1.transAxes, fontsize=9.5, color=c.GOOD, va="top")

ax2 = fig.add_subplot(gs[0, 1])
t2, x2, _, th2, _, F2, tau2 = c.trace("good", 2)
ax2.plot(t2, x2, color=c.BLUE, lw=2.0, zorder=3, label="$x$ (cart position)")
ax2.axhline(c.S2_X_BAND, color=c.GOOD, lw=1.2, zorder=2)
ax2.axhline(-c.S2_X_BAND, color=c.GOOD, lw=1.2, zorder=2)
ax2.fill_between([-0.3, 10.3], -c.S2_X_BAND, c.S2_X_BAND,
                 color=c.GOOD, alpha=0.08, zorder=1)
xs = g["s2_x_settle_s"]["value"]
ax2.plot([xs], [-c.S2_X_BAND], "o", ms=9, color=c.BLUE,
         markeredgecolor=c.SURFACE, markeredgewidth=2, zorder=4)
ax2.annotate(f"settles {xs:.2f} s into the ±0.02 m band\n"
             f"(gate: settle ≤ {c.S2_SETTLE_MAX:.0f} s)",
             xy=(xs, -c.S2_X_BAND), xytext=(3.3, 0.40),
             fontsize=10.5, color=c.INK2,
             arrowprops=dict(arrowstyle="-", color=c.AXIS, lw=1))
ax2.set_xlabel("time (s)", fontsize=11.5, color=c.INK2)
ax2.set_ylabel("$x$ (m)", fontsize=11.5, color=c.INK2)
ax2.set_title("Scenario 2 - return from a 1 m cart displacement",
              fontsize=12.5, color=c.INK, pad=8)
ax2.set_xlim(-0.3, 10.3)
ax2.set_ylim(-0.12, 1.14)
c.style_axis(ax2)
leg = ax2.legend(loc="upper right", fontsize=10, frameon=True,
                 facecolor=c.SURFACE, edgecolor=c.GRID)
leg.get_texts()[0].set_color(c.INK2)
ax2.text(0.02, 0.975, "gate: 2 % settle of x (band ±0.02 m) ≤ 7 s",
         transform=ax2.transAxes, fontsize=9.5, color=c.GOOD, va="top")

# ---------------------------------------------------------- bottom-left: table
axt = fig.add_subplot(gs[1, 0])
axt.axis("off")
axt.set_title("Judge verdict - good controller (18/18 gates pass)",
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
    ("pm_force_deg", "phase margin, force loop", f"{g['pm_force_deg']['value']:.1f}°",
     "≥ 45°"),
    ("pm_torque_deg", "phase margin, torque loop", f"{g['pm_torque_deg']['value']:.1f}°",
     "≥ 45°"),
    ("mc_pass_fraction", "Monte-Carlo pass fraction", f"{V['mc_pass']}/{V['mc_n']}",
     "≥ 95 %"),
]
y0, dy = 0.955, 0.061
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
axm.text(0.25, 3.30,
         f"{V['mc_pass']}/{V['mc_n']} samples pass both runs\n"
         f"gate: ≥ 95 % of 200 - measured {frac:.3f}\n"
         f"worst θ settle {V['mc_theta_settle_worst_s']:.2f} s, "
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
                 bbox_to_anchor=(0.02, 0.85), fontsize=10,
                 frameon=True, facecolor=c.SURFACE, edgecolor=c.GRID)
leg.get_texts()[0].set_color(c.INK2)
axm.text(0.02, 0.975, "every dot must sit left of / below its red limit",
         transform=axm.transAxes, fontsize=9.5, color=c.CRIT, va="top")

fig.suptitle("LQR cart-pole under the judge's spec envelope - all gates pass",
             fontsize=15, color=c.INK, x=0.065, ha="left", y=0.962)
c.caption(fig, "Every curve and number is measured by judge/grade.sh on "
          "examples/good/controller.json (seed 20260101): traces from the "
          "--trace CSVs, gate values from the verdict JSON. Gain margins "
          "are unlimited (99 dB = judge sentinel for \"no -180° crossing in "
          "the 0.01-1000 rad/s sweep\"). The green band is the settling "
          "band: settling time is the last exit from it (so S2 x = 6.05 s "
          "passes the 7 s gate), and the S1 curve's small dip below zero is "
          "a normal overshoot - the overshoot gate allows 10 %.")
c.check_layout(fig)
fig.savefig(os.path.join(c.MEDIA, "result.png"), dpi=200)
print("result.png written")
