"""loop.png - the agent loop under the judge, as a replay.

Left column, top to bottom: the mutant x gate matrix from the real verdict
JSONs (4 replay candidates x 18 gates), the trace of the gate that actually
killed too-aggressive (actuator demand), and the trace that killed
too-sluggish (settling). Right column: which gate ended each replay step,
and the selftest kill bars.
"""

import os

import numpy as np

import common as c

plt = c.rc_params()

Vg = c.verdict("good")

# The replay order a fixing agent would go through: candidate -> verdict.
ORDER = ["too-aggressive", "too-sluggish", "mc-marginal", "good"]
LABEL = {"too-aggressive": "too-aggressive (Q × 1000)",
         "too-sluggish": "too-sluggish (Q / 100)",
         "mc-marginal": "mc-marginal (Q × 0.8)",
         "good": "good (committed example)"}
GATES = ["design_stable", "s1_F_demand_max_N", "s1_tau_demand_max_Nm",
         "s1_theta_overshoot", "s1_theta_settle_s", "s1_x_settle_s",
         "s1_theta_end_rad", "s1_x_end_m", "s2_peak_theta_rad",
         "s2_F_demand_max_N", "s2_tau_demand_max_Nm", "s2_x_settle_s",
         "s2_theta_end_rad", "gm_force_db", "pm_force_deg", "gm_torque_db",
         "pm_torque_deg", "mc_pass_fraction"]
GATE_LBL = {"design_stable": "stable\nλ(A-BK)", "s1_F_demand_max_N": "S1\n|F|",
            "s1_tau_demand_max_Nm": "S1\n|τ|", "s1_theta_overshoot": "S1\novsh",
            "s1_theta_settle_s": "S1\nθ set", "s1_x_settle_s": "S1\nx set",
            "s1_theta_end_rad": "S1\nθ end", "s1_x_end_m": "S1\nx end",
            "s2_peak_theta_rad": "S2\n|θ| pk", "s2_F_demand_max_N": "S2\n|F|",
            "s2_tau_demand_max_Nm": "S2\n|τ|", "s2_x_settle_s": "S2\nx set",
            "s2_theta_end_rad": "S2\nθ end", "gm_force_db": "GM\nF",
            "pm_force_deg": "PM\nF", "gm_torque_db": "GM\nτ",
            "pm_torque_deg": "PM\nτ", "mc_pass_fraction": "MC\n≥ 95 %"}

fig = plt.figure(figsize=(13, 9.6), dpi=200)
gs = fig.add_gridspec(3, 2, width_ratios=[1.28, 1.0],
                      height_ratios=[1.02, 1.0, 1.0],
                      left=0.055, right=0.99, top=0.895, bottom=0.088,
                      wspace=0.24, hspace=0.52)

# ------------------------------------------------ mutant x gate matrix
axm = fig.add_subplot(gs[0, 0])
mat = np.zeros((len(ORDER), len(GATES)))
for i, name in enumerate(ORDER):
    v = c.verdict(name)
    for j, gk in enumerate(GATES):
        mat[i, j] = 1.0 if v["gates"][gk]["pass"] else 0.0
axm.imshow(mat, aspect="auto", cmap="Greens", vmin=-0.9, vmax=1.25,
           interpolation="nearest")
for i, name in enumerate(ORDER):
    v = c.verdict(name)
    for j, gk in enumerate(GATES):
        if v["gates"][gk]["pass"]:
            axm.text(j, i, "✓", fontsize=11, color=c.GOOD, ha="center",
                     va="center", fontweight="bold")
        else:
            axm.text(j, i, "✕", fontsize=11, color=c.CRIT, ha="center",
                     va="center", fontweight="bold")
axm.set_xticks(range(len(GATES)))
axm.set_xticklabels([GATE_LBL[g] for g in GATES], fontsize=8.4)
axm.set_yticks(range(len(ORDER)))
axm.set_yticklabels([LABEL[n] for n in ORDER], fontsize=10)
axm.tick_params(colors=c.MUTED, length=0)
for s in axm.spines.values():
    s.set_visible(False)
axm.set_title("Gates passed (✓) / failed (✕) per replay step - 18 gates, "
              "seed 20260101", fontsize=12, color=c.INK, pad=8)
axm.set_xticks(np.arange(-0.5, len(GATES), 1), minor=True)
axm.set_yticks(np.arange(-0.5, len(ORDER), 1), minor=True)
axm.grid(which="minor", color=c.SURFACE, linewidth=2.5)
axm.tick_params(which="minor", length=0)

# --------------------------------------------- the killer trace: saturation
axA = fig.add_subplot(gs[1, 0])
tA, _, _, _, _, FA, tauA = c.trace("too-aggressive", 2)
tG, _, _, _, _, FG, tauG = c.trace("good", 2)
axA.plot(tA, tauA, color=c.ORANGE, lw=2.0, zorder=3,
         label="too-aggressive (Q × 1000)")
axA.plot(tG, tauG, color=c.BLUE, lw=2.0, zorder=3,
         label="good (committed example)")
axA.axhline(c.TAU_MAX, color=c.CRIT, lw=1.6, zorder=2,
            label="actuator limit ±1 N·m")
axA.axhline(-c.TAU_MAX, color=c.CRIT, lw=1.6, zorder=2)
axA.axhline(0, color=c.AXIS, lw=1.0, zorder=1)
bad = c.verdict("too-aggressive")["gates"]["s2_tau_demand_max_Nm"]["value"]
axA.annotate(f"measured peak |τ| = {bad:.2f} N·m - gate fails at 1 N·m\n"
             "(unclamped demand; the simulation clamps the real input)",
             xy=(tA[np.argmax(np.abs(tauA))], bad),
             xytext=(1.6, 1.66), fontsize=10.5, color=c.INK2,
             arrowprops=dict(arrowstyle="-", color=c.AXIS, lw=1))
axA.set_xlabel("time (s)", fontsize=11.5, color=c.INK2)
axA.set_ylabel("torque demand (N·m)", fontsize=11.5, color=c.INK2)
axA.set_title("Killed by the actuator gate - scenario 2 torque demand",
              fontsize=12, color=c.INK, pad=8)
axA.set_xlim(-0.2, 10.2)
axA.set_ylim(-2.75, 3.35)
c.style_axis(axA)
axA.legend(loc="upper right", fontsize=9.5, frameon=True, facecolor=c.SURFACE,
           edgecolor=c.GRID)
for txt in axA.get_legend().get_texts():
    txt.set_color(c.INK2)
axA.text(0.02, 0.03,
         "gate: peak unclamped |τ| demand ≤ 1 N·m in both scenarios",
         transform=axA.transAxes, fontsize=9.5, color=c.CRIT, va="bottom")

# ------------------------------------------- the killer trace: settling
axS = fig.add_subplot(gs[2, 0])
tS, xS, _, _, _, _, _ = c.trace("too-sluggish", 2)
tG2, xG2, _, _, _, _, _ = c.trace("good", 2)
axS.plot(tS, xS, color=c.ORANGE, lw=2.0, zorder=3,
         label="too-sluggish (Q / 100)")
axS.plot(tG2, xG2, color=c.BLUE, lw=2.0, zorder=3,
         label="good (committed example)")
axS.axhline(c.S2_X_BAND, color=c.GOOD, lw=1.2, zorder=2)
axS.axhline(-c.S2_X_BAND, color=c.GOOD, lw=1.2, zorder=2)
axS.fill_between([-0.3, 10.3], -c.S2_X_BAND, c.S2_X_BAND, color=c.GOOD,
                 alpha=0.08, zorder=1)
vs = c.verdict("too-sluggish")["gates"]["s2_x_settle_s"]["value"]
axS.annotate(f"too-sluggish never settles (gate: ≤ 7 s, measured {vs:.0f} s)\n"
             f"good settles {Vg['gates']['s2_x_settle_s']['value']:.2f} s",
             xy=(9.4, xS[940]), xytext=(2.2, 0.60), fontsize=10.5,
             color=c.INK2, arrowprops=dict(arrowstyle="-", color=c.AXIS, lw=1))
axS.set_xlabel("time (s)", fontsize=11.5, color=c.INK2)
axS.set_ylabel("cart position x (m)", fontsize=11.5, color=c.INK2)
axS.set_title("Killed by the settling gate - scenario 2 cart displacement",
              fontsize=12, color=c.INK, pad=8)
axS.set_xlim(-0.3, 10.3)
axS.set_ylim(-0.35, 1.12)
c.style_axis(axS)
axS.legend(loc="upper right", fontsize=9.5, frameon=True, facecolor=c.SURFACE,
           edgecolor=c.GRID)
for txt in axS.get_legend().get_texts():
    txt.set_color(c.INK2)
axS.text(0.02, 0.03, "gate: 2 % settle of x (band ±0.02 m) ≤ 7 s",
         transform=axS.transAxes, fontsize=9.5, color=c.GOOD, va="bottom")

# ------------------------------------------------ right top: first-failing gate
axf = fig.add_subplot(gs[0, 1])
axf.axis("off")
axf.set_title("The gate that ended each replay step", fontsize=12,
             color=c.INK, pad=8)
Vm = c.verdict("mc-marginal")
Va = c.verdict("too-aggressive")
Vs = c.verdict("too-sluggish")
FIRST = [("too-aggressive", "actuator demand",
          f"peak |τ| = {Va['gates']['s2_tau_demand_max_Nm']['value']:.2f} N·m > 1 N·m"),
         ("too-sluggish", "settling time",
          f"x settles {Vs['gates']['s2_x_settle_s']['value']:.0f} s > 7 s"),
         ("mc-marginal", "Monte-Carlo robustness",
          f"{Vm['mc_pass']}/{Vm['mc_n']} = "
          f"{Vm['gates']['mc_pass_fraction']['value']:.3f} < 0.95"),
         ("good", "all 18 gates", "verdict: PASS")]
yy = 0.86
for name, gname, detail in FIRST:
    if name == "good":
        mark, mcol = "✓", c.GOOD
    else:
        mark, mcol = "✕", c.CRIT
    axf.text(0.02, yy, mark, fontsize=13, color=mcol, va="center",
             fontweight="bold")
    axf.text(0.09, yy, LABEL[name], fontsize=11, color=c.INK, va="center")
    axf.text(0.09, yy - 0.055, f"→ {gname}:  {detail}", fontsize=10,
             color=c.INK2, va="center")
    yy -= 0.20
axf.text(0.02, 0.015,
         "mc-marginal passes all 17 deterministic gates (green row in the "
         "matrix) and dies on the Monte-Carlo gate alone - 39/200 perturbed "
         "plants miss the 7 s displacement settling limit.",
         fontsize=10, color=c.INK2, va="bottom")
axf.set_xlim(0, 1)
axf.set_ylim(0, 1)

# ------------------------------------------------ right bottom: selftest bars
axs = fig.add_subplot(gs[1:, 1])
MUT = ["nan-weight", "wrong-type", "wrong-shape", "sign-flip",
       "degenerate-r-force", "degenerate-r-torque", "too-aggressive",
       "too-sluggish", "mc-marginal"]
HOW = {"nan-weight": "gate 1: NaN weight", "wrong-type": "gate 1: type ≠ \"lqr\"",
       "wrong-shape": "gate 1: Q length 3", "sign-flip": "gate 2: no stabilising K",
       "degenerate-r-force": "gate 3: |F| demand", "degenerate-r-torque": "gate 3: |τ| demand",
       "too-aggressive": "gate 3: |τ| demand", "too-sluggish": "gate 3/4: settling",
       "mc-marginal": "gate 6: Monte-Carlo"}
axs.barh([0], [1], height=0.62, color=c.GOOD, zorder=3)
axs.text(1.012, 0, "good - 18/18 gates pass", fontsize=10.5, color=c.GOOD,
         va="center", fontweight="bold")
for i, m in enumerate(MUT):
    axs.barh([-(i + 1)], [1], height=0.62, color=c.CRIT, zorder=3)
    axs.text(1.012, -(i + 1), f"{m} - rejected ({HOW[m]})", fontsize=10.5,
             color=c.CRIT, va="center")
axs.set_xlim(0, 1)
axs.set_ylim(-len(MUT) - 0.6, 0.6)
axs.set_yticks([])
axs.set_xticks([])
for s in ("top", "right", "left", "bottom"):
    axs.spines[s].set_visible(False)
axs.set_title("Selftest - known-bad mutants the judge must reject\n"
              "(kill rate 9/9 = 100 %, threshold ≥ 90 %)",
              fontsize=12, color=c.INK, pad=8)
axs.text(0.0, -(len(MUT) + 0.45),
         "gate 1 rejects invalid JSON before any simulation runs; "
         "gate 6 alone kills mc-marginal", fontsize=9.5, color=c.MUTED,
         va="top")

fig.suptitle("The agent loop under the judge - replayed with the committed "
             "examples (seed 20260101)", fontsize=15, color=c.INK, x=0.055,
             ha="left", y=0.962)
c.caption(fig, "Replay of a fixing agent's loop (candidates graded in the "
          "order a tuner would meet the failures), not a live agent trace: "
          "each candidate's gates come from its own judge/grade.sh verdict "
          "JSON, each curve from its --trace CSV. In the matrix, \"MC\" is "
          "the Monte-Carlo gate (≥ 95 % of 200 ±20 %-perturbed plants pass "
          "both spec runs); mc-marginal is green in every other column and "
          "fails only there.")
fig.savefig(os.path.join(c.MEDIA, "loop.png"), dpi=200)
print("loop.png written")
