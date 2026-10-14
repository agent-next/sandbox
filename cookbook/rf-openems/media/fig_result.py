#!/usr/bin/env python3
"""result.png -- the good antenna's real measured S11 against the spec.

Panel A: S11(dB) vs frequency from the grader's own sweep output
         (media/data/traces/good__s11_artifact.csv, written by
         judge/grade.py --trace from the artifact's antenna_results.json),
         the judge's independent re-derivation from the raw openEMS port
         time series (good__s11_judge.csv, G6), and the G8 fine-mesh
         re-run (good__s11_fine.csv). Red dashed line: the -10 dB
         pass threshold of gate G4; shaded band: the G5 +-2 % resonance
         window around 2.45 GHz.
Panel B: eeff of the ~50 ohm oracle microstrip line: openEMS probe
         measurement vs Hammerstad-Jensen closed form from the good
         verdict JSON (gate G7, +-4 % rule), plus the phase slope the
         eeff is extracted from.

Every number is read from media/data (verdict JSONs / grade.py trace
CSVs); the script exits non-zero if any source file is missing, and if
any placed text escapes its axes or overlaps another text.
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

MEDIA = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(MEDIA, "data")
OUT = os.path.join(MEDIA, "result.png")

F_TARGET = 2.45          # GHz (SPEC.md)
S11_TARGET = -10.0       # dB  (G4)
F_RES_TOL = 0.02         # +-2 % (G5)
S11_FLOOR = -30.0        # dB, plot floor

C_GOOD = "#0072B2"       # Okabe-Ito blue  (validated CVD-safe)
C_FINE = "#D55E00"       # Okabe-Ito vermillion
C_JUDGE = "#009E73"      # Okabe-Ito green
C_SPEC = "#c94343"       # status red, reserved for the limit


def need(p):
    if not os.path.exists(p):
        raise SystemExit(f"missing {p} -- run media/make_data.sh first")
    return p


def read_trace(name):
    p = need(os.path.join(DATA, "traces", name + ".csv"))
    d = np.genfromtxt(p, delimiter=",", names=True)
    return d["freq_ghz"], d["s11_db"]


def check_layout(fig, items):
    """Fail if any registered text escapes its axes or overlaps another.

    items: (artist, ax_or_None, tag); ax=None means pairwise-only (the
    artist legitimately lives outside any axes, e.g. titles)."""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    boxes = []
    for art, ax, tag in items:
        bb = art.get_window_extent(renderer=r)
        if ax is not None:
            ab = ax.get_window_extent(renderer=r)
            if bb.x0 < ab.x0 - 1 or bb.x1 > ab.x1 + 1 or \
                    bb.y0 < ab.y0 - 1 or bb.y1 > ab.y1 + 1:
                raise SystemExit(
                    f"text '{tag}' escapes its axes: "
                    f"text=({bb.x0:.0f},{bb.y0:.0f})-({bb.x1:.0f},{bb.y1:.0f}) "
                    f"axes=({ab.x0:.0f},{ab.y0:.0f})-({ab.x1:.0f},{ab.y1:.0f})")
        boxes.append((bb, tag))
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if boxes[i][0].overlaps(boxes[j][0]):
                raise SystemExit(
                    f"text overlap: {boxes[i][1]} vs {boxes[j][1]}")
    print(f"layout check: OK ({len(boxes)} texts, no overlaps)")


def main():
    v = json.load(open(need(os.path.join(DATA, "verdicts", "good.json"))))
    fg, sg = read_trace("good__s11_artifact")
    fj, sj = read_trace("good__s11_judge")
    ff, sf = read_trace("good__s11_fine")

    # measured numbers, straight from the verdict JSON
    g4 = next(g for g in v["gates"] if g["gate"] == "G4_S11_at_target")
    g5 = next(g for g in v["gates"] if g["gate"] == "G5_resonance")
    g6 = next(g for g in v["gates"] if g["gate"] == "G6_raw_crosscheck")
    g8 = next(g for g in v["gates"] if g["gate"] == "G8_convergence")
    s11_at = float(np.interp(F_TARGET, fg, sg))          # dB at 2.45
    i_res = int(np.argmin(sg))
    s11_min, f_res = float(sg[i_res]), float(fg[i_res])
    conv = v["convergence"]
    oracle = v["oracle"]

    fig = plt.figure(figsize=(15.5, 6.0), dpi=200)
    gs = fig.add_gridspec(
        1, 2, width_ratios=[2.35, 1.0], left=0.045, right=0.985,
        top=0.86, bottom=0.13, wspace=0.24)
    texts = []   # (artist, ax|None, tag) for the layout check

    def reg(art, ax, tag):
        texts.append((art, ax, tag))
        return art

    # ------------------------------------------------------------- panel A
    axA = fig.add_subplot(gs[0])
    band = (F_TARGET * (1 - F_RES_TOL), F_TARGET * (1 + F_RES_TOL))
    axA.axvspan(*band, color="#97b7d3", alpha=0.25, zorder=0)
    axA.axhline(S11_TARGET, color=C_SPEC, lw=1.8, ls="--", zorder=1)
    # the G4 rule is 'S11 at 2.45 GHz <= -10 dB': the curve must dip
    # BELOW the red line inside the band -- deeper (more negative) is
    # better; that is printed next to the line, not assumed obvious.
    axA.plot(fg, sg, color=C_GOOD, lw=2.2, zorder=3,
             label="measured S11 (grader trace, 51 pts)")
    axA.plot(fj, sj, color=C_JUDGE, lw=1.4, ls=(0, (4, 3)), zorder=4,
             label="judge re-derived from raw port time series (G6)")
    axA.plot(ff, sf, color=C_FINE, lw=1.6, ls=(0, (1, 1.6)), zorder=4,
             label=f"fine-mesh re-run {conv['mesh_res_fine_mm']} mm (G8)")
    axA.axvline(F_TARGET, color="0.35", lw=1.0, zorder=2)

    # marker + labels at the measured minimum
    axA.plot([f_res], [s11_min], "o", ms=7, mfc="white", mec=C_GOOD,
             mew=1.8, zorder=5)
    reg(axA.annotate(f"min S11 = {s11_min:.1f} dB @ {f_res:.2f} GHz",
                     xy=(f_res, s11_min), xytext=(f_res + 0.035, s11_min - 1),
                     fontsize=11, fontweight="bold",
                     arrowprops=dict(arrowstyle="-", color=C_GOOD, lw=1.0)),
         axA, "min-annotation")

    reg(axA.text(F_TARGET + 0.004, -28.6,
                 f"trace at 2.45 GHz = {s11_at:.1f} dB\n(G4 rule: below the "
                 f"red -{abs(S11_TARGET):.0f} dB line)",
                 fontsize=10.5, va="bottom"), axA, "s11-at-target")
    reg(axA.text(F_TARGET + 0.004, -0.5,
                 f"G5 resonance window\n2.45 GHz ±{F_RES_TOL*100:.0f} %",
                 fontsize=9, va="top", ha="left", color="0.30"),
        axA, "band-label")
    reg(axA.text(0.015, 0.03,
                 f"gate verdicts (verdict JSON):\n"
                 f"G4 {g4['detail']}\n"
                 f"G5 {g5['detail']}\n"
                 f"G6 max|judge-artifact| = "
                 f"{v['raw_crosscheck_maxdiff_db']:.1f} dB ≤ 1.5\n"
                 f"G8 fine mesh S11 = {conv['S11_at_target_fine_dB']:.1f} dB, "
                 f"f_res shift {conv['f_res_shift_pct']:.1f} % ≤ 1.5\n"
                 f"G8 rule: dip depth is mesh-sensitive, so the gate\n"
                 f"re-checks the spec on the finer mesh, not ΔS11;\n"
                 f"dotted curve: {np.interp(F_TARGET, ff, sf):.1f} dB at 2.45: pass\n"
                 f"verdict dB values use a 1 dB grid (run-to-run\n"
                 f"noise); gate decisions use the raw values",
                 transform=axA.transAxes, fontsize=9, va="bottom",
                 family="monospace", color="0.25", bbox=dict(
                     facecolor="white", edgecolor="0.7", pad=4)),
        axA, "verdict-box")

    axA.set_xlim(2.2, 2.7)
    axA.set_ylim(S11_FLOOR, 0)
    axA.set_xlabel("frequency [GHz]")
    axA.set_ylabel("|S11| [dB]")
    axA.set_title("S11 of the judged-good patch antenna — openEMS sweep "
                  "vs the -10 dB spec", fontsize=13)
    axA.set_xticks(np.arange(2.2, 2.71, 0.05))
    axA.grid(True, alpha=0.25)
    axA.legend(loc="upper right", bbox_to_anchor=(1.0, 0.62), fontsize=9.5, framealpha=0.95)

    # ------------------------------------------------------------- panel B
    axB = fig.add_subplot(gs[1])
    probes = np.asarray(oracle["probes_mm"], float)
    phases = np.asarray(oracle["phases_deg"], float)
    # unwrap: the verdict stores each phase on the 1 deg reporting grid;
    # successive probes differ by ~-79 deg -> cumulative sum recovers the
    # true travel. Sign: phase decreases along +x.
    travel = -np.concatenate([[0.0], np.cumsum(np.abs(np.diff(phases)))])
    coef = np.polyfit(probes, travel, 1)
    axB.plot(probes, travel, "o-", color=C_JUDGE, lw=2.0, ms=7,
             label="openEMS probe phase travel (G7 sim)")
    xs = np.linspace(probes[0], probes[-1], 100)
    axB.plot(xs, np.polyval(coef, xs), color="0.55", lw=1.2, ls=":",
             label=f"linear fit → |β| = "
                   f"{abs(coef[0])*np.pi/180:.3f} rad/mm")
    beta_sim = coef[0] * np.pi / 180.0
    lam0 = 299.792458 / oracle["freq_GHz"]   # mm
    eeff_sim_check = (beta_sim * lam0 / (2 * np.pi)) ** 2
    assert abs(eeff_sim_check - oracle["eeff_sim"]) < 0.05, \
        f"eeff mismatch: {eeff_sim_check} vs {oracle['eeff_sim']}"
    reg(axB.text(0.04, 0.05,
                 f"εeff: sim {oracle['eeff_sim']:.2f} vs "
                 f"H-J {oracle['eeff_HJ']:.2f}\n"
                 f"Δ = {oracle['delta_pct']:.1f} % "
                 f"(G7 rule ≤ 4 %)",
                 transform=axB.transAxes, fontsize=10, va="bottom",
                 bbox=dict(facecolor="white", edgecolor="0.7", pad=4)),
        axB, "eeff-box")

    axB.set_xlabel("probe position x [mm]")
    axB.set_ylabel("unwrapped phase travel [deg]")
    axB.set_title("Oracle: eeff of the ~50 Ω line\nvs Hammerstad-Jensen "
                  "(G7)", fontsize=12)
    axB.grid(True, alpha=0.25)
    axB.legend(loc="upper right", fontsize=9, framealpha=0.95)

    fig.suptitle(
        "rf-openems — judge verdict on the good antenna: all 9 gates "
        "pass (replay of the real grade run)",
        fontsize=15, y=0.97)
    reg(fig.text(0.045, 0.015,
                 "source: media/data/verdicts/good.json + traces "
                 "good__s11_*.csv (judge/grade.sh examples/good/antenna.py "
                 "--trace, seed 42) — no synthesised data",
                 fontsize=8, color="0.4"), None, "source-note")

    check_layout(fig, texts)
    fig.savefig(OUT, dpi=200)
    plt.close(fig)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
