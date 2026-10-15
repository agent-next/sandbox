#!/usr/bin/env python3
"""Render media/result.png, media/loop.png and the video frames.

Every plotted value comes from media/data/*.json, all produced by real
judge runs (grade verdict + selftest capture + the artifact's own input
cells). The oracle curve is the closed form over those measured inputs;
the pass band is the judge's ±0.5 % tolerance, the kill bars come from
the self-test, and the video is a captioned step-through of the same
figures (the demo has no time-dependent physics).

Palette: Okabe-Ito colour-blind-safe slots; status colours always carry
a text label.
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

MEDIA = Path(__file__).resolve().parent
DATA = MEDIA / "data"

INK, GREY = "#172B3A", "#677783"
BLUE, ORANGE, GREEN, RED = "#0072B2", "#D55E00", "#009E73", "#D55E00"
LIGHT = "#8DA9C4"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 12, "text.color": INK,
    "axes.labelcolor": INK, "axes.titleweight": "bold",
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.16, "axes.axisbelow": True,
    "legend.framealpha": 0.95, "savefig.facecolor": "white",
})

VERDICT = json.loads((DATA / "grade.json").read_text())
SELFTEST = json.loads((DATA / "selftest.json").read_text())
MODEL = json.loads((DATA / "model.json").read_text())["sheets"]

RATES = [8, 10, 12]
TOL_PCT = 0.5          # judge pass line: NPV vs closed form (SPEC.md)
MOVE_MIN_PCT = 1.0     # negative control: NPV must move (SPEC.md)


def measured_inputs():
    """Initial investment and FCFs from the artifact's own input cells."""
    assum = MODEL["Assumptions"]
    proj = MODEL["Projections"]
    inv = float(assum[1][1])                       # B2 initial investment
    tax = float(assum[3][1])                       # B4 tax rate
    fcfs = []
    for row in proj[1:]:
        year, rev, cost = int(row[0]), float(row[1]), float(row[2])
        fcfs.append((year, (rev - cost) * (1.0 - tax)))
    return inv, fcfs


INV, FCFS = measured_inputs()


def npv(rate):
    """Closed-form oracle over the measured inputs."""
    return INV + sum(fcf / (1.0 + rate) ** t for t, fcf in FCFS)


# The closed form must agree with the judge's own oracle numbers (the judge
# stores them rounded to 4 decimals, so compare at that quantum).
for pct in RATES:
    j_oracle = VERDICT["metrics"][f"npv_{pct}_oracle"]
    assert abs(npv(pct / 100) - j_oracle) <= 1e-4, \
        f"render oracle disagrees with judge oracle at {pct}%"


def style_axes(ax, title, xlabel, ylabel):
    ax.set_title(title, loc="left")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)


def npv_panel(ax, curve_frac=1.0, shown_rates=(8, 10, 12), band=True):
    """NPV vs discount rate: closed form + measured recalc points."""
    style_axes(ax, "Recalculated NPV vs closed-form oracle",
               "Discount rate (%, written into Assumptions!B3)",
               "NPV (USD)")
    rs = np.linspace(0.05, 0.15, 200)
    oracle = np.array([npv(r) for r in rs])
    n = max(2, int(len(rs) * curve_frac))
    ax.plot(rs[:n] * 100, oracle[:n], "-", color=BLUE, lw=2.2,
            label="Closed-form oracle (judge)", zorder=2)
    if band:
        ax.fill_between(rs * 100, oracle * (1 + TOL_PCT / 100),
                        oracle * (1 - TOL_PCT / 100), color=BLUE,
                        alpha=0.12, lw=0,
                        label=f"Judge pass band ±{TOL_PCT:g}%", zorder=1)
    for pct in RATES:
        if pct not in shown_rates:
            continue
        comp = VERDICT["metrics"][f"npv_{pct}_computed"]
        err = VERDICT["metrics"][f"npv_{pct}_err_pct"]
        ax.plot([pct], [comp], "o", color=ORANGE, ms=8, zorder=3,
                label="LibreOffice recalc (measured)" if pct == 8 else None)
        ax.annotate(f"{comp:,.0f}\nerr {err:.4f}%", (pct, comp),
                    textcoords="offset points", xytext=(8, -2),
                    fontsize=9, color=INK)
    ax.legend(loc="upper right", fontsize=10)
    ax.set_xlim(5, 15.6)


def limits_panel(ax):
    """Judge error margins against their SPEC limits."""
    style_axes(ax, "Error vs SPEC limit (100% = the pass line)",
               "", "Error / limit (%)")
    m = VERDICT["metrics"]
    move = m["negative_control_move_pct"]
    vals = [m[f"npv_{p}_err_pct"] / TOL_PCT * 100 for p in RATES]
    move_ratio = move / MOVE_MIN_PCT * 100        # move vs required minimum
    cap = 130                                     # axis cap for the bar only
    vals.append(min(move_ratio, cap))
    colors = [BLUE] * 3 + [GREEN]
    ax.bar(range(4), vals, color=colors, width=0.55)
    if move_ratio > cap:                          # capped: mark the true value
        ax.plot([3, 3], [cap - 14, cap - 3], color=GREEN, lw=2.5)
    ax.axhline(100, color=INK, ls="--", lw=1.5)
    ax.text(3.4, 104, "SPEC pass limit", ha="right", fontsize=9, color=INK)
    for i, p in enumerate(RATES):
        lab = f"{m[f'npv_{p}_err_pct']:.4f}% / {TOL_PCT:g}%"
        ax.text(i, 6, lab, ha="center", fontsize=8.5)
    ax.text(3, cap - 18, f"{move:.2f}% / ≥{MOVE_MIN_PCT:g}%\n"
            f"({move_ratio:,.0f}% of required)"
            + (" — bar capped" if move_ratio > cap else ""),
            ha="center", fontsize=8.5, color=INK)
    ax.set_xticks(range(4))
    ax.set_xticklabels(["@8%", "@10%", "@12%", "move"], fontsize=10)
    ax.set_ylim(0, 145)


def kill_panel(ax, shown=None):
    """Self-test kill-rate bars: known-good vs each known-bad."""
    style_axes(ax, "Self-test: known-bad workbooks must fail",
               "", "Judge verdict")
    muts = SELFTEST["mutants"]
    names = [m["name"].replace("_", "\n") for m in muts]
    n = len(muts) if shown is None else min(shown, len(muts))
    xs = np.arange(len(muts) + 1)
    ax.bar(xs[:1], [1], color=GREEN, width=0.55)
    ax.text(0, 1.06, "known-good\nPASS", ha="center", fontsize=9, color=GREEN)
    ax.bar(xs[1:n + 1], [1] * n, color=RED, width=0.55)
    for i in range(1, n + 1):
        gates = ",".join(SELFTEST["mutants"][i - 1]["killed_by"])
        ax.text(i, 1.06, gates, ha="center", fontsize=7.5, color=INK,
                rotation=0)
    for i in range(n + 1, len(muts) + 1):
        ax.bar([xs[i]], [1], color=LIGHT, width=0.55, alpha=0.35)
    ax.set_xticks(xs)
    ax.set_xticklabels(["good"] + names, fontsize=8)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["pass", "fail"], fontsize=9)
    ax.set_ylim(0, 1.45)
    rate = SELFTEST["kill_rate_pct"]
    ax.set_title(f"Self-test kill rate {SELFTEST['kill_rate']} = {rate}% "
                 f"(standard: ≥ 90%)", loc="left")


def result_figure():
    fig, (a, b) = plt.subplots(
        2, 1, figsize=(6.4, 6.4), dpi=200,
        gridspec_kw={"height_ratios": [1.5, 1]})
    fig.subplots_adjust(left=0.14, right=0.97, bottom=0.09, top=0.90,
                        hspace=0.55)
    fig.suptitle("spreadsheet-recalc | DCF workbook, judged by recalculation",
                 fontsize=13, weight="bold")
    fig.text(0.5, 0.945, "LibreOffice headless recalc vs closed-form oracle · "
             "seed 0 · all five gates PASS", ha="center", fontsize=9.5,
             color=GREY)
    npv_panel(a)
    limits_panel(b)
    a.xaxis.set_major_locator(plt.MaxNLocator(5))
    b.yaxis.set_major_locator(plt.MaxNLocator(5))
    save(fig, MEDIA / "result.png")


def loop_figure():
    fig, (a, b) = plt.subplots(1, 2, figsize=(9.6, 4.2), dpi=200)
    fig.subplots_adjust(left=0.08, right=0.98, bottom=0.18, top=0.86,
                        wspace=0.25)
    fig.suptitle("spreadsheet-recalc | judge loop: fail the bad, pass the good",
                 fontsize=12.5, weight="bold")
    kill_panel(a)
    limits_panel(b)
    a.tick_params(axis="x", labelsize=7)
    save(fig, MEDIA / "loop.png")


# ---------------------------------------------------------------- video --
# Unique frames are rendered at FRAME_FPS; make_media.sh encodes them to a
# 30 fps output (ffmpeg -framerate FRAME_FPS -r 30), so motion stays smooth
# where it exists without paying matplotlib for 30 saves per second.
FPS = 10
DUR = 30                     # seconds
W, H = 19.2, 10.8            # inches at dpi 100 -> 1920x1080


def slide(title, subtitle=None):
    fig = plt.figure(figsize=(W, H), dpi=100)
    fig.text(0.06, 0.93, title, fontsize=30, weight="bold", color=INK)
    if subtitle:
        fig.text(0.06, 0.875, subtitle, fontsize=16, color=GREY)
    return fig


def axes_at(fig, rect):
    ax = fig.add_axes(rect)
    ax.set_facecolor("white")
    return ax


def model_rows():
    """Artifact rows for the structure slide: label, value/formula."""
    rows = [("Assumptions", "Initial investment", str(INV))]
    a = MODEL["Assumptions"]
    rows += [("Assumptions", "Discount rate (B3)", str(a[2][1])),
             ("Assumptions", "Tax rate (B4)", str(a[3][1]))]
    for row in MODEL["Projections"][1:]:
        rows.append(("Projections",
                     f"Year {int(row[0])}: FCF formula", str(row[6])))
        rows.append(("Projections",
                     f"Year {int(row[0])}: PV formula", str(row[8])))
    rows.append(("Valuation", "NPV (B2)", str(MODEL["Valuation"][1][1])))
    return rows


def f_title(progress):
    fig = slide("spreadsheet-recalc",
                "A DCF workbook with live formulas, graded by headless recalculation")
    ax = axes_at(fig, [0.06, 0.30, 0.88, 0.42])
    ax.axis("off")
    facts = [
        f"artifact: examples/good/dcf_model.xlsx — 3 sheets, 12 live formulas",
        f"judge: LibreOffice recalc at 8 / 10 / 12 % vs closed-form DCF oracle (±{TOL_PCT:g}%)",
        f"self-test: {SELFTEST['kill_rate']} known-bad workbooks killed = "
        f"{SELFTEST['kill_rate_pct']}% kill rate",
        "verdict: " + ("PASS" if VERDICT["pass"] else "FAIL") +
        " on every gate",
    ]
    y = 0.86
    for i, fact in enumerate(facts):
        vis = max(0.0, min(1.0, progress * 4 - i))
        if vis <= 0:
            continue
        ax.text(0.02, y - i * 0.24, "· " + fact, fontsize=26,
                alpha=vis, color=INK, transform=ax.transAxes)
    return fig


def f_model(progress):
    fig = slide("The artifact: every computed cell is a formula",
                "openpyxl-authored workbook — no hardcoded results")
    ax = axes_at(fig, [0.06, 0.10, 0.88, 0.70])
    ax.axis("off")
    rows = model_rows()
    n = int(progress * (len(rows) + 1))
    ax.text(0.0, 1.03, "sheet      cell                        content",
            fontsize=20, family="DejaVu Sans Mono", color=GREY,
            transform=ax.transAxes)
    for i, (sheet, label, value) in enumerate(rows):
        if i >= n:
            break
        ax.text(0.0, 0.96 - i * (0.9 / len(rows)),
                f"{sheet:<11}{label:<28}{value}",
                fontsize=17, family="DejaVu Sans Mono", color=INK,
                transform=ax.transAxes)
    return fig


def f_npv(progress):
    fig = slide("The judge recalculates — and compares to the oracle",
                "Discount rate rewritten into Assumptions!B3, LibreOffice headless recalc")
    ax = axes_at(fig, [0.10, 0.14, 0.84, 0.62])
    if progress < 0.4:
        npv_panel(ax, curve_frac=progress / 0.4, shown_rates=())
    else:
        k = int((progress - 0.4) / 0.6 * 4)     # 0..3 points revealed
        npv_panel(ax, shown_rates=RATES[:k])
        ax.tick_params(labelsize=20)
        for t in ax.texts:
            t.set_fontsize(15)
        ax.legend(fontsize=19)
        ax.title.set_fontsize(24)
        ax.xaxis.label.set_fontsize(20)
        ax.yaxis.label.set_fontsize(20)
    return fig


def f_kill(progress):
    fig = slide("The self-test: the judge must fail bad workbooks",
                f"{SELFTEST['kill_rate']} known-bad mutants, single scripted edits of the good artifact")
    ax = axes_at(fig, [0.10, 0.16, 0.84, 0.62])
    n = int(round(progress * len(SELFTEST["mutants"])))
    kill_panel(ax, shown=n)
    ax.title.set_fontsize(24)
    ax.tick_params(labelsize=19)
    for t in ax.texts:
        t.set_fontsize(14)
    return fig


def f_verdict(progress):
    fig = slide("Verdict", "from the grade JSON, seed 0")
    ax = axes_at(fig, [0.06, 0.12, 0.5, 0.66])
    ax.axis("off")
    y = 0.95
    for gate, ok in sorted(VERDICT["gates"].items()):
        mark = "PASS" if ok else "FAIL"
        color = GREEN if ok else RED
        ax.text(0.02, y, f"{gate:<18}{mark}", fontsize=24,
                family="DejaVu Sans Mono", color=color, transform=ax.transAxes)
        y -= 0.14
    m = VERDICT["metrics"]
    y -= 0.04
    for pct in RATES:
        ax.text(0.02, y, f"NPV @ {pct}%: {m[f'npv_{pct}_computed']:,.2f} "
                f"(err {m[f'npv_{pct}_err_pct']:.4f}%)", fontsize=20,
                color=INK, transform=ax.transAxes)
        y -= 0.12
    ax2 = axes_at(fig, [0.60, 0.30, 0.36, 0.42])
    npv_panel(ax2)
    ax2.title.set_fontsize(19)
    ax2.tick_params(labelsize=15)
    for t in ax2.texts:
        t.set_fontsize(12)
    ax2.legend(fontsize=15)
    if progress > 0.5:
        fig.text(0.30, 0.045, "ALL GATES PASS", fontsize=44, weight="bold",
                 color=GREEN, alpha=(progress - 0.5) * 2)
    return fig


def f_outro(_progress):
    fig = slide("Run it yourself",
                "one command, one disposable sandbox, one verdict")
    ax = axes_at(fig, [0.06, 0.34, 0.88, 0.40])
    ax.axis("off")
    ax.text(0.5, 0.62, "python3 cookbook/spreadsheet-recalc/run.py --ref main",
            fontsize=28, family="DejaVu Sans Mono", color=BLUE,
            ha="center", transform=ax.transAxes)
    ax.text(0.5, 0.28, "cookbook/spreadsheet-recalc · judge a workbook you "
            "built with:\nbash judge/grade.sh your_model.xlsx --json /tmp/v.json",
            fontsize=19, color=GREY, ha="center", transform=ax.transAxes)
    return fig


SEGMENTS = [                       # (duration_s, frame_fn)
    (3.5, f_title),
    (6.0, f_model),
    (7.0, f_npv),
    (6.5, f_kill),
    (5.0, f_verdict),
    (2.0, f_outro),
]


def video_frames(frames_dir):
    frames_dir = Path(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)
    total = sum(d for d, _ in SEGMENTS)
    assert 20 <= total <= 60, f"video length {total}s outside 20-60s"
    idx = 0
    for dur, fn in SEGMENTS:
        n = int(round(dur * FPS))
        for k in range(n):
            fig = fn(k / max(1, n - 1))
            fig.savefig(frames_dir / f"f{idx:04d}.png", dpi=100,
                        metadata={"Software": None})
            plt.close(fig)
            idx += 1
        print(f"segment {fn.__name__}: {n} frames")
    print(f"video: {idx} frames at {FPS} fps = {idx / FPS:.1f} s")
    return idx


def save(fig, path):
    fig.savefig(path, dpi=200, metadata={"Software": None})
    plt.close(fig)
    print(f"wrote {path.name}")


def main():
    result_figure()
    loop_figure()
    if len(sys.argv) > 1:                       # frames dir given
        video_frames(sys.argv[1])


if __name__ == "__main__":
    main()
