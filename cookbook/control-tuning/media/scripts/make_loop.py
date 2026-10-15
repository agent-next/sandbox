"""loop.png - the agent loop under the judge, as a replay.

Left column, top to bottom: the mutant x gate matrix from the real verdict
JSONs (4 replay candidates x 18 gates), the trace of the gate that actually
killed too-aggressive (actuator demand), and the trace that killed
too-sluggish (settling). Right column: which gate ended each replay step,
and the selftest kill bars.

Every number is read from a judge output: verdict JSONs and trace CSVs under
media/data/, plus the self-test log (media/data/selftest.log) written by
media/regen_data.sh running judge/selftest.sh verbatim. The kill bars, the
rejection labels and the kill rate come from that log, never from here; a
missing, empty or incomplete log is a hard error.
"""

import os
import re

import numpy as np
from matplotlib.colors import ListedColormap

import common as c

plt = c.rc_params()


def selftest_log():
    """Parse media/data/selftest.log -> (rows, n_good, killed, total, rate).

    rows: [(name, killed_bool, label)] per mutant, in the self-test's own
    order, label = the description + measured detail the self-test
    printed; n_good: how many of the expected-pass gradings passed;
    killed/total/rate: the kill-rate line verbatim. The log must exist,
    be nonempty and carry the closing kill-rate line - anything else
    means the self-test did not run to completion against the current
    judge, and no kill bar may be drawn.
    """
    path = os.path.join(c.DATA, "selftest.log")
    if not os.path.isfile(path):
        c.die(f"missing {path} - run media/regen_data.sh (it runs "
              "judge/selftest.sh verbatim and captures this log)")
    with open(path, encoding="utf-8") as fh:
        log = fh.read()
    if not log.strip():
        c.die(f"{path} is empty - the self-test produced no output")
    m = re.search(r"kill rate:\s*(\d+)/(\d+)\s*=\s*(\d+)%", log)
    if not m:
        c.die(f"{path} has no 'kill rate: k/n = p%' line - the self-test "
              "did not complete")
    killed, total, rate = (int(g) for g in m.groups())
    rows = []
    for verdict, name, label in re.findall(
            r"^(PASS|FAIL) \(expected reject\): (\S+?)(?: \[isolated\])?"
            r"(?: - (.*))?$", log, re.M):
        # drop the trailing measured detail the self-test appends
        # ("... (gate = value)" / "... (invalid artifact: ...)") so the
        # bar labels stay one line; the full line stays in the log
        label = re.sub(r" \((?:invalid artifact:.*|[\w]+ = [^()]*)\)$",
                       "", label or "")
        rows.append((name, verdict == "PASS", label))
    n_good = len(re.findall(r"^PASS \(expected pass\):", log, re.M))
    n_good_total = len(re.findall(r"^\w+ \(expected pass\):", log, re.M))
    if len(rows) != total or sum(k for _, k, _ in rows) != killed:
        c.die(f"self-test log does not add up: {len(rows)} reject lines, "
              f"{sum(k for _, k, _ in rows)} clean kills, but the "
              f"self-test printed {killed}/{total}")
    if n_good != n_good_total:
        c.die(f"self-test log shows {n_good_total - n_good} expected-pass "
              f"grading(s) that did not pass")
    return rows, n_good, killed, total, rate

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
                      height_ratios=[1.30, 1.0, 1.0],
                      left=0.105, right=0.985, top=0.895, bottom=0.118,
                      wspace=0.26, hspace=0.55)

# two-line row labels keep the gate matrix inside the left figure edge
MAT_LBL = {"too-aggressive": "too-aggressive\n(Q × 1000)",
           "too-sluggish": "too-sluggish\n(Q / 100)",
           "mc-marginal": "mc-marginal\n(Q × 0.8)",
           "good": "good\n(committed)"}

# ------------------------------------------------ mutant x gate matrix
axm = fig.add_subplot(gs[0, 0])
mat = np.zeros((len(ORDER), len(GATES)))
for i, name in enumerate(ORDER):
    v = c.verdict(name)
    for j, gk in enumerate(GATES):
        mat[i, j] = 1.0 if v["gates"][gk]["pass"] else 0.0
axm.imshow(mat, aspect="auto", vmin=0, vmax=1, interpolation="nearest",
           cmap=ListedColormap(["#f6d3cf", "#1f7a3f"]))
for i, name in enumerate(ORDER):
    v = c.verdict(name)
    for j, gk in enumerate(GATES):
        if v["gates"][gk]["pass"]:
            axm.text(j, i, "✓", fontsize=11, color="white", ha="center",
                     va="center", fontweight="bold")
        else:
            axm.text(j, i, "✕", fontsize=11, color=c.CRIT, ha="center",
                     va="center", fontweight="bold")
axm.set_xticks(range(len(GATES)))
axm.set_xticklabels([GATE_LBL[g] for g in GATES], fontsize=7.0)
axm.set_yticks(range(len(ORDER)))
axm.set_yticklabels([MAT_LBL[n] for n in ORDER], fontsize=10)
axm.tick_params(colors=c.MUTED, length=0)
for s in axm.spines.values():
    s.set_visible(False)
axm.set_title("Gates passed (✓) / failed (✕) per replay step "
              "- seed 20260101", fontsize=12, color=c.INK, pad=8)
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
         label="good (committed)")
axA.axhline(c.TAU_MAX, color=c.CRIT, lw=1.6, zorder=2,
            label="actuator limit ±1 N·m")
axA.axhline(-c.TAU_MAX, color=c.CRIT, lw=1.6, zorder=2)
axA.axhline(0, color=c.AXIS, lw=1.0, zorder=1)
bad = c.verdict("too-aggressive")["gates"]["s2_tau_demand_max_Nm"]["value"]
# label and leader drawn separately: the layout check then measures the
# label text alone, not the whole leader-line box
iA = np.argmax(np.abs(tauA))
axA.text(1.6, 1.45, f"measured peak |τ| = {bad:.2f} N·m - gate fails at 1 N·m\n"
         "(unclamped demand; the simulation clamps the real input)",
         fontsize=10.5, color=c.INK2)
axA.annotate("", xy=(tA[iA], tauA[iA]), xytext=(1.55, 1.6),
             arrowprops=dict(arrowstyle="-", color=c.AXIS, lw=1))
axA.set_xlabel("time (s)", fontsize=11.5, color=c.INK2)
axA.set_ylabel("torque demand (N·m)", fontsize=11.5, color=c.INK2)
axA.set_title("Killed by the actuator gate - scenario 2 torque demand",
              fontsize=12, color=c.INK, pad=8)
axA.set_xlim(-0.2, 10.2)
axA.set_ylim(-4.4, 4.3)
c.style_axis(axA)
axA.legend(loc="lower right", ncol=3, fontsize=8.5, frameon=True, facecolor=c.SURFACE,
           edgecolor=c.GRID)
for txt in axA.get_legend().get_texts():
    txt.set_color(c.INK2)
axA.text(0.02, 0.985,
         "gate: unclamped peak |τ| ≤ 1 N·m in both runs",
         transform=axA.transAxes, fontsize=9.5, color=c.CRIT, va="top")

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
axS.text(10.0, 1.06, f"too-sluggish never settles\n"
         f"(gate ≤ {c.S2_SETTLE_MAX:.0f} s, measured {vs:.0f} s)\n"
         f"good settles {Vg['gates']['s2_x_settle_s']['value']:.2f} s",
         fontsize=10.5, color=c.INK2, ha="right", va="top")
axS.annotate("", xy=(9.4, xS[940]), xytext=(9.75, 0.6),
             arrowprops=dict(arrowstyle="-", color=c.AXIS, lw=1))
axS.set_xlabel("time (s)", fontsize=11.5, color=c.INK2)
axS.set_ylabel("cart position x (m)", fontsize=11.5, color=c.INK2)
axS.set_title("Killed by the settling gate - scenario 2 cart displacement",
              fontsize=12, color=c.INK, pad=8)
axS.set_xlim(-0.3, 10.3)
axS.set_ylim(-0.62, 1.12)
c.style_axis(axS)
axS.legend(loc="lower left", fontsize=9.5,
           frameon=True, facecolor=c.SURFACE,
           edgecolor=c.GRID)
for txt in axS.get_legend().get_texts():
    txt.set_color(c.INK2)
axS.text(0.98, 0.03, "gate: 2 % settle of x (band ±0.02 m) ≤ 7 s",
         transform=axS.transAxes, fontsize=9.5, color=c.GOOD, va="bottom",
         ha="right")

# ------------------------------------------------ right top: first-failing gate
axf = fig.add_subplot(gs[0, 1])
axf.axis("off")
axf.set_title("The gate that ended each replay step", fontsize=12,
             color=c.INK, pad=8)
Vm = c.verdict("mc-marginal")
Va = c.verdict("too-aggressive")
Vs = c.verdict("too-sluggish")
NGATES = len(Vg["gates"])
FIRST = [("too-aggressive", "actuator demand",
          f"peak |τ| = {Va['gates']['s2_tau_demand_max_Nm']['value']:.2f} N·m > 1 N·m"),
         ("too-sluggish", "settling time",
          f"x settles {Vs['gates']['s2_x_settle_s']['value']:.0f} s > 7 s"),
         ("mc-marginal", "Monte-Carlo robustness",
          f"{Vm['mc_pass']}/{Vm['mc_n']} = "
          f"{Vm['gates']['mc_pass_fraction']['value']:.3f} < 0.95"),
         ("good", f"all {NGATES} gates", "verdict: PASS")]
yy = 0.94
for name, gname, detail in FIRST:
    if name == "good":
        mark, mcol = "✓", c.GOOD
    else:
        mark, mcol = "✕", c.CRIT
    axf.text(0.02, yy, mark, fontsize=13, color=mcol, va="center",
             fontweight="bold")
    axf.text(0.09, yy, LABEL[name], fontsize=11, color=c.INK, va="center")
    axf.text(0.09, yy - 0.10, f"→ {gname}:  {detail}", fontsize=10,
             color=c.INK2, va="center")
    yy -= 0.21
axf.text(0.02, 0.02,
         "mc-marginal fails the Monte-Carlo gate alone",
         fontsize=9.5, color=c.INK2, va="bottom")
axf.set_xlim(0, 1)
axf.set_ylim(0, 1)

# ------------------------------------------- right bottom: selftest kill bars
# Every bar, label and the kill rate come from the captured self-test log
# (media/data/selftest.log, written by media/regen_data.sh); nothing here
# invents a kill. NGATES and the good row's pass count come from the good
# verdict JSON.
ST_ROWS, N_GOOD, KILLED, TOTAL, RATE = selftest_log()
axs = fig.add_subplot(gs[1:, 1])
rows = [("good", True,
         f"{sum(g['pass'] for g in Vg['gates'].values())}/{NGATES} "
         "gates pass")] + ST_ROWS
BAR_H = 0.62 if len(rows) <= 11 else 0.58
FS = 10.5 if len(rows) <= 11 else 9.0
for i, (name, killed, label) in enumerate(rows):
    y = -i
    col = c.GOOD if killed else c.CRIT
    axs.barh([y], [1], height=BAR_H, color=col, zorder=3)
    axs.text(0.035, y, name, fontsize=FS, color="white", va="center",
             fontweight="bold")
    tag = "pass" if killed and name == "good" else (
        "rejected" if killed else "NOT KILLED")
    txt = f"{tag} - {label}" if label else tag
    axs.text(1.05, y, txt, fontsize=FS, color=col, va="center")
axs.set_xlim(0, 2.42)
axs.set_ylim(-len(rows) - 1.7, 0.62)
axs.set_yticks([])
axs.set_xticks([])
for s in ("top", "right", "left", "bottom"):
    axs.spines[s].set_visible(False)
axs.set_title(f"Selftest - known-bad mutants the judge must reject\n"
              f"(kill rate {KILLED}/{TOTAL} = {RATE} %, threshold ≥ 90 %)",
              fontsize=12, color=c.INK, pad=8)
axs.text(0.0, -(len(rows) + 0.55),
         f"bars and kill rate parsed from the captured selftest output "
         f"(media/data/selftest.log);\n"
         f"{N_GOOD} expected-pass grading(s) incl. the full Monte-Carlo "
         "grade of the good example", fontsize=9.0, color=c.MUTED,
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
c.check_layout(fig)
fig.savefig(os.path.join(c.MEDIA, "loop.png"), dpi=200)
print("loop.png written")
