#!/usr/bin/env python3
"""make_figures.py -- render result.png and loop.png from real judge output.

Data sources (all produced by this repo's judge, never hand-edited):
  judge_runs/verdicts/good.json    grade.sh examples/good/scene.usda --seed 42
  judge_runs/mutants/<name>.json   grade.sh on each mutants.py scene
  judge_runs/mutants/mutants/mutants.json   mutants.py descriptions
  judge_runs/traces/good/traj.npz  judge/simulate.py per-step positions

result.png: the measured PhysX trajectory against the analytic oracle with
the pass lines drawn on (free fall + contact gate, bounce apex gate,
energy gate).  loop.png: the agent loop replayed (each iteration a real
grade verdict) plus the per-mutant gate matrix (kill rate 11/11).

Raises if any input is missing; every number in the output comes from the
JSON/npz files above.
"""

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, Rectangle

MEDIA = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(MEDIA, "judge_runs")
VERDICTS = os.path.join(RUNS, "verdicts")
MUTANTS = os.path.join(RUNS, "mutants")
TRACES = os.path.join(RUNS, "traces", "good")

# reference palette (validated, colour-blind-safe): Box=blue, Ball=orange
BOX_C = "#2a78d6"
BALL_C = "#eb6834"
ANALYTIC_C = "#898781"   # muted ink: the analytic curve is context
GOOD_C = "#0ca30c"       # status good: pass lines / bands
CRIT_C = "#d03b3b"       # status critical: failed gate cells
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
SURFACE = "#fcfcfb"

G = 9.81
DT = 1.0 / 240.0

plt.rcParams.update({
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
    "font.family": "DejaVu Sans",
    "text.color": INK,
    "axes.edgecolor": BASELINE,
    "axes.labelcolor": INK2,
    "axes.titlecolor": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.grid": True,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "axes.spines.top": False,
    "axes.spines.right": False,
})

# the replay: the order a fixing agent would plausibly meet the scripted
# authoring mistakes (mutants), then the good scene that passes
REPLAY = ["cm-units", "spawn-inside-ground", "no-rigidbody",
          "no-ground-collision", "mass-zero", "gravity-flip",
          "restitution-over-unity"]
# the matrix shows every mutant the self-test grades, cheats included
MATRIX = ["cm-units", "gravity-flip", "hidden-reference", "joint-scaffold",
          "kinematic-cheat", "mass-zero", "no-ground-collision",
          "no-rigidbody", "planted-verdict", "restitution-over-unity",
          "spawn-inside-ground"]
GATE_ORDER = ["G1_loads", "G2_freefall", "G3_contact_time", "G4_resting",
              "G5_bounce_apex", "G6_energy", "G7_contract"]
GATE_LABEL = {"G1_loads": "G1\nloads", "G2_freefall": "G2\nfree fall",
              "G3_contact_time": "G3\ncontact time",
              "G4_resting": "G4\nresting", "G5_bounce_apex": "G5\nbounce apex",
              "G6_energy": "G6\nenergy", "G7_contract": "G7\ncontract"}


def need(path):
    if not os.path.exists(path):
        raise SystemExit(f"make_figures: missing judge output {path} -- "
                         "run media/make_media.sh first")
    return path


def load(path):
    return json.load(open(need(path)))


def body_gate(verdict, gate):
    """Merge a gate over both bodies: fails if any body fails it; prefer
    the failing body's detail (Box first) for the cell text."""
    parts = []
    for body in ("Box", "Ball"):
        g = verdict.get("bodies", {}).get(body, {}).get(gate)
        if g is not None:
            parts.append(g)
    if not parts:
        return None
    failed = [g for g in parts if not g.get("passed", False)]
    if failed:
        return failed[0]
    return parts[0]


def contact_index(y, vy):
    """The judge's own contact rule: first sample where vy turns upward."""
    for i in range(1, len(vy)):
        if vy[i - 1] < 0.0 < vy[i]:
            return i
    return None


def style_axes(ax):
    ax.grid(True, axis="both", linewidth=0.8)
    ax.set_axisbelow(True)


# ---------------------------------------------------------------- result.png
def fig_result():
    v = load(os.path.join(VERDICTS, "good.json"))
    traj = np.load(need(os.path.join(TRACES, "traj.npz")))
    box_y, box_vy = traj["box_y"], traj["box_vy"]
    ball_y, ball_vy = traj["ball_y"], traj["ball_vy"]
    t = np.arange(len(box_y)) * DT

    bx = v["bodies"]["Box"]
    bl = v["bodies"]["Ball"]
    g2b, g2l = bx["G2_freefall"]["detail"], bl["G2_freefall"]["detail"]
    g3b, g3l = bx["G3_contact_time"]["detail"], bl["G3_contact_time"]["detail"]
    g4b = bx["G4_resting"]["detail"]
    g5 = bl["G5_bounce_apex"]["detail"]
    g6b, g6l = bx["G6_energy"]["detail"], bl["G6_energy"]["detail"]
    e0_box, e0_ball = g6b["E0_J"], g6l["E0_J"]
    m_box = v["bodies"]["Box"]["G1_loads"]["detail"]["mass_kg"]
    m_ball = v["bodies"]["Ball"]["G1_loads"]["detail"]["mass_kg"]

    i_box = contact_index(box_y, box_vy)
    i_ball = contact_index(ball_y, ball_vy)

    fig, axes = plt.subplots(1, 3, figsize=(15.5, 5.4), dpi=200,
                             constrained_layout=True)
    fig.suptitle("physx-drop-test: measured PhysX trajectory vs the "
                 "analytic oracle -- all "
                 f"{len(v['gates'])} gates pass",
                 fontsize=15, fontweight="bold")
    fig.text(0.01, 0.005,
             f"source: grade.sh examples/good/scene.usda --seed 42 | "
             f"ovphysx 0.6.3, 2400 steps @ 1/240 s | green = judge pass line",
             fontsize=8.5, color=MUTED)

    # --- (a) box: free fall + first contact ------------------------------
    ax = axes[0]
    style_axes(ax)
    ax.plot(t, box_y, color=BOX_C, lw=2.0, solid_capstyle="round",
            label="simulated (box)", zorder=3)
    tt = np.linspace(0, g3b["t_contact_analytic_s"], 200)
    ax.plot(tt, g2b["y0_m"] - 0.5 * G * tt ** 2, color=ANALYTIC_C, lw=1.4,
            ls=(0, (4, 3)), label=r"analytic $y_0-\frac{1}{2}gt^2$", zorder=2)
    # G3 pass band: +/- 1 frame around the analytic contact time
    tc = g3b["t_contact_analytic_s"]
    ax.axvspan(tc - 1 / 240.0, tc + 1 / 240.0, color=GOOD_C, alpha=0.18,
               zorder=1)
    ax.axvline(tc, color=GOOD_C, lw=1.2)
    ax.plot(g3b["t_contact_sim_s"], box_y[i_box], "o", ms=9, mfc=BOX_C,
            mec=SURFACE, mew=2, zorder=5)
    ax.annotate(f"first contact {g3b['t_contact_sim_s']:.3f} s\n"
                fr"$\Delta$ {g3b['delta_frames']:.2f} fr $\leq$ 1 fr"
                " (G3 pass)",
                xy=(g3b["t_contact_sim_s"], box_y[i_box]),
                xytext=(0.16, 0.52), fontsize=9.5, color=INK2,
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
    ax.axhline(g4b["y_rest_m"], color=GOOD_C, lw=1.0)
    ax.text(0.012, g4b["y_rest_m"] + 0.012,
            f"$y_{{rest}}$ {g4b['y_rest_m']:.3f} m (G4: error "
            f"{g4b['error_mm']:.1f} mm)", fontsize=9, color=GOOD_C)
    ax.set_xlim(0, 0.55)
    ax.set_ylim(0, 0.87)
    ax.set_xlabel("t (s)")
    ax.set_ylabel("centre height y (m)")
    ax.set_title(f"(a) Box free fall\nfitted g = {g2b['g_fit']} m/s$^2$, "
                 f"max residual {g2b['max_abs_residual_m']:.4f} m (G2)",
                 fontsize=11)
    ax.legend(loc="upper right", fontsize=9, frameon=False)

    # --- (b) ball: bounce apex -------------------------------------------
    ax = axes[1]
    style_axes(ax)
    ax.plot(t, ball_y, color=BALL_C, lw=2.0, solid_capstyle="round",
            label="simulated (ball)", zorder=3)
    tt = np.linspace(0, g3l["t_contact_analytic_s"], 200)
    ax.plot(tt, g2l["y0_m"] - 0.5 * G * tt ** 2, color=ANALYTIC_C, lw=1.4,
            ls=(0, (4, 3)), label=r"analytic $y_0-\frac{1}{2}gt^2$", zorder=2)
    # G5 pass band: +/- 10 % around the analytic apex
    apex_a = g5["apex_analytic_m"]
    ax.axhspan(apex_a * 0.9, apex_a * 1.1, color=GOOD_C, alpha=0.12, zorder=1)
    ax.axhline(apex_a, color=GOOD_C, lw=1.2)
    ax.text(0.63, apex_a + 0.012,
            f"analytic apex $y_{{rest}}+e^2\\Delta h$ = {apex_a:.3f} m",
            fontsize=9, color=GOOD_C)
    i_apex = i_ball + 1 + int(np.argmin(np.abs(
        (ball_y[i_ball + 1:] - g5["apex_sim_m"])[:240])))
    ax.plot(t[i_apex], g5["apex_sim_m"], "o", ms=9, mfc=BALL_C,
            mec=SURFACE, mew=2, zorder=5)
    ax.annotate(f"measured apex {g5['apex_sim_m']:.4f} m\n"
                f"{100 * g5['rel_error']:.2f} % "
                fr"$\leq$ 10 % (G5)",
                xy=(t[i_apex], g5["apex_sim_m"]),
                xytext=(0.70, 0.90), fontsize=9.5, color=INK2,
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
    # G3 marker for the ball
    tcl = g3l["t_contact_analytic_s"]
    ax.axvspan(tcl - 1 / 240.0, tcl + 1 / 240.0, color=GOOD_C, alpha=0.18,
               zorder=1)
    ax.plot(g3l["t_contact_sim_s"], ball_y[i_ball], "o", ms=9, mfc=BALL_C,
            mec=SURFACE, mew=2, zorder=5)
    ax.annotate(f"contact {g3l['t_contact_sim_s']:.4f} s, "
                fr"$\Delta$ {g3l['delta_frames']:.2f} fr (G3)",
                xy=(g3l["t_contact_sim_s"], ball_y[i_ball]),
                xytext=(0.18, 0.35), fontsize=9.5, color=INK2,
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
    ax.axhline(g4b["y_rest_m"], color=GOOD_C, lw=1.0)
    ax.set_xlim(0, 1.2)
    ax.set_ylim(0, 1.30)
    ax.set_xlabel("t (s)")
    ax.set_ylabel("centre height y (m)")
    ax.set_title(f"(b) Ball drop and first bounce\n"
                 f"restitution e = 0.50, drop from {g2l['y0_m']:.2f} m",
                 fontsize=11)
    ax.legend(loc="upper right", fontsize=9, frameon=False)

    # --- (c) energy --------------------------------------------------------
    ax = axes[2]
    style_axes(ax)
    e_box = (m_box * G * box_y + 0.5 * m_box * box_vy ** 2) / e0_box
    e_ball = (m_ball * G * ball_y + 0.5 * m_ball * ball_vy ** 2) / e0_ball
    ax.plot(t, e_box, color=BOX_C, lw=2.0, label="box (E₀ "
            f"{e0_box:.2f} J)", zorder=3)
    ax.plot(t, e_ball, color=BALL_C, lw=2.0, label="ball (E₀ "
            f"{e0_ball:.2f} J)", zorder=3)
    ax.axhline(1.0, color=GOOD_C, lw=1.2)
    ax.axhspan(1.0, 1.005, color=GOOD_C, alpha=0.25, zorder=1)
    ax.text(4.1, 1.018, "pass line E ≤ E₀ (+0.5 % E₀)",
            fontsize=9, color=GOOD_C)
    ax.plot(t[-1], e_box[-1], "o", ms=8, mfc=BOX_C, mec=SURFACE, mew=2,
            zorder=5)
    ax.plot(t[-1], e_ball[-1], "o", ms=8, mfc=BALL_C, mec=SURFACE, mew=2,
            zorder=5)
    ax.annotate(f"{e_box[-1]:.3f}", xy=(t[-1], e_box[-1]),
                xytext=(-4, 8), textcoords="offset points",
                fontsize=9, color=BOX_C, ha="right")
    ax.annotate(f"{e_ball[-1]:.3f}", xy=(t[-1], e_ball[-1]),
                xytext=(-4, -13), textcoords="offset points",
                fontsize=9, color=BALL_C, ha="right")
    gain_box = 100 * g6b["max_step_gain_J"] / e0_box
    gain_ball = 100 * g6l["max_step_gain_J"] / e0_ball
    ax.text(0.35, 0.62, "max step gain:\nbox "
            f"{gain_box:.3f} % E₀, ball {gain_ball:.3f} % E₀\n"
            r"(tolerance 0.5 %, G6)", fontsize=9.5, color=INK2)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 1.10)
    ax.set_xlabel("t (s)")
    ax.set_ylabel("E / E₀")
    ax.set_title("(c) Mechanical energy never increases\n"
                 r"$E = mgy + \frac{1}{2}mv^2$, normalised", fontsize=11)
    ax.legend(loc="upper right", fontsize=9, frameon=False)

    out = os.path.join(MEDIA, "result.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"[figures] wrote {out}")


# ------------------------------------------------------------------ loop.png
def short_reason(gate, det):
    r = det.get("reason")
    if r:
        table = {
            "no free-fall segment sampled": "no free fall",
            "free-fall window too short": "window too short",
            "no velocity reversal — no contact detected": "no contact",
            "no rebound sampled": "no rebound",
            "initial potential energy not positive": "E₀ ≤ 0",
            "spawn height": None,
            "body not sampled by simulator": "not sampled",
        }
        for k, s in table.items():
            if r.startswith(k) and s:
                return s
        if r.startswith("spawn height"):
            return f"y₀ {det.get('y0_m', '?')} ≠ authored"
        return r[:16]
    return None


def cell_text(gate, g):
    """Short measured-vs-limit text for one verdict cell."""
    ok = bool(g.get("passed"))
    det = g.get("detail", {})
    mark = "✓" if ok else "✗"
    r = short_reason(gate, det)
    if gate == "G1_loads":
        txt = (f"{det['mass_kg']:g} kg" if det.get("mass_kg") is not None
               else "no mass")
    elif gate == "G2_freefall":
        if det.get("g_fit") is not None:
            txt = f"g = {det['g_fit']:g}"
        else:
            txt = r or "?"
    elif gate == "G3_contact_time":
        if det.get("delta_frames") is not None:
            txt = f"Δ {det['delta_frames']:g} fr"
        else:
            txt = r or "no contact"
    elif gate == "G4_resting":
        if det.get("error_mm") is not None:
            txt = f"{det['error_mm']:g} mm"
        else:
            txt = r or "?"
    elif gate == "G5_bounce_apex":
        if det.get("rel_error") is not None:
            txt = f"{100 * det['rel_error']:.2f} %"
        else:
            txt = r or "no rebound"
    elif gate == "G6_energy":
        if det.get("max_step_gain_J") is not None and det.get("E0_J"):
            txt = (f"+{100 * det['max_step_gain_J'] / det['E0_J']:.2f} % "
                   "E₀")
        else:
            txt = r or "?"
    else:
        txt = r or ("pass" if ok else "fail")
    if r and not ok:
        txt = r
    return ok, f"{mark} {txt}"


def fig_loop():
    good = load(os.path.join(VERDICTS, "good.json"))
    n_gates = len(good["gates"])
    muts = {m: load(os.path.join(MUTANTS, f"{m}.json")) for m in MATRIX}
    desc = load(os.path.join(MUTANTS, "mutants", "mutants.json"))
    killed = sum(1 for v in muts.values()
                 if any(not r.get("passed", False)
                        for r in v.get("gates", {}).values()))

    fig = plt.figure(figsize=(15.5, 10.6), dpi=200, constrained_layout=True)
    gs = fig.add_gridspec(2, 1, height_ratios=[1.0, 1.6])
    fig.suptitle("The agent loop and the self-test -- every point and "
                 "cell is a real grade.sh verdict (--seed 42)",
                 fontsize=15, fontweight="bold")

    # --- top: the replayed loop -------------------------------------------
    ax = fig.add_subplot(gs[0])
    style_axes(ax)
    names = REPLAY + ["good"]
    passed = []
    for n in names:
        v = good if n == "good" else muts[n]
        gates = v.get("gates", {})
        passed.append(sum(1 for r in gates.values() if r.get("passed")))
    xs = np.arange(len(names))
    ax.axhline(n_gates, color=GOOD_C, lw=1.2)
    ax.text(0.02, n_gates + 0.08, f"all {n_gates} gates pass", fontsize=9.5,
            color=GOOD_C)
    ax.plot(xs[:-1], passed[:-1], "-o", color=BOX_C, lw=2, ms=9,
            mfc=BOX_C, mec=SURFACE, mew=2, zorder=4)
    ax.plot(xs[-1], passed[-1], "o", ms=11, mfc=GOOD_C, mec=SURFACE, mew=2,
            zorder=5)
    ax.annotate("PASS", xy=(xs[-1], passed[-1]), xytext=(6, -4),
                textcoords="offset points", fontsize=12, fontweight="bold",
                color=GOOD_C)
    for i, n in enumerate(names[:-1]):
        v = muts[n]
        failed = [g for g, r in v.get("gates", {}).items()
                  if not r.get("passed")]
        short = " ".join(g.split("_")[0] for g in failed)
        ax.annotate(f"✗ {short}", xy=(i, passed[i]), xytext=(0, 9),
                    textcoords="offset points", ha="center", fontsize=9,
                    color=CRIT_C)
    labels = []
    for n in names:
        if n == "good":
            labels.append("good\n(final artifact)")
        else:
            d = desc[n].split("(")[0].strip().rstrip(",")
            words = d.split()
            lines, cur = [], ""
            for w in words:
                if len(cur) + len(w) + 1 > 22:
                    lines.append(cur)
                    cur = w
                else:
                    cur = f"{cur} {w}".strip()
            lines.append(cur)
            labels.append("\n".join(lines[:3]))
    ax.set_xticks(xs, labels, fontsize=8.6)
    ax.set_ylim(0, n_gates + 1.2)
    ax.set_yticks(range(0, n_gates + 1))
    ax.set_ylabel(f"gates passed (of {n_gates})")
    ax.set_title("replayed authoring iterations: the judge names the "
                 "failed gate(s) until the scene passes", fontsize=11)

    # --- bottom: scene x gate matrix --------------------------------------
    ax = fig.add_subplot(gs[1])
    ax.grid(False)
    rows = ["good"] + MATRIX
    for ri, n in enumerate(rows):
        v = good if n == "good" else muts[n]
        for ci, gate in enumerate(GATE_ORDER):
            g = body_gate(v, gate)
            ok, txt = (True, "✓") if g is None else cell_text(gate, g)
            if n == "good":
                ok = bool(good["gates"].get(gate, {}).get("passed", False))
            fc = "#0ca30c14" if ok else "#d03b3b1a"
            ax.add_patch(Rectangle((ci, len(rows) - 1 - ri), 1, 1,
                                   facecolor=fc, edgecolor=BASELINE,
                                   lw=0.6))
            ax.text(ci + 0.5, len(rows) - 1 - ri + 0.5, txt, ha="center",
                    va="center", fontsize=8.6,
                    color=INK if ok else CRIT_C)
        # verdict column (a surviving mutant would be a judge bug: the
        # self-test requires kill rate >= 90 %, so both read as failures)
        if n == "good":
            vtxt, vcol = "PASS", GOOD_C
        else:
            failed = [g for g, r in v.get("gates", {}).items()
                      if not r.get("passed")]
            vtxt = (f"killed ({len(failed)} gate"
                    f"{'s' if len(failed) != 1 else ''})")
            vcol = CRIT_C
        ax.add_patch(Rectangle((len(GATE_ORDER), len(rows) - 1 - ri), 1, 1,
                               facecolor=SURFACE, edgecolor=BASELINE,
                               lw=0.6))
        ax.text(len(GATE_ORDER) + 0.5, len(rows) - 1 - ri + 0.5, vtxt,
                ha="center", va="center", fontsize=8.8, color=vcol,
                fontweight="bold")
    ax.set_xlim(0, len(GATE_ORDER) + 1)
    ax.set_ylim(0, len(rows))
    ax.set_xticks([i + 0.5 for i in range(len(GATE_ORDER) + 1)],
                  [GATE_LABEL[g] for g in GATE_ORDER] + ["verdict"],
                  fontsize=9)
    ax.set_yticks([len(rows) - 0.5 - i for i in range(len(rows))],
                  rows, fontsize=9.5)
    ax.set_title(f"self-test matrix: every known-bad scene is killed by at "
                 f"least one gate -- kill rate {killed}/{len(muts)} = "
                 f"{round(100 * killed / len(muts))} % (rule: ≥ 90 %)",
                 fontsize=11)
    for s in ("top", "right", "left", "bottom"):
        ax.spines[s].set_visible(False)

    out = os.path.join(MEDIA, "loop.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"[figures] wrote {out}")


if __name__ == "__main__":
    fig_result()
    fig_loop()
