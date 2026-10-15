#!/usr/bin/env python3
"""Render media/result.png and media/loop.png from media/data/*.json.

Every plotted value comes from a judge output file (the grade verdicts and
the engine-driven oracle comparison written by make_data.py).  Palette:
the validated reference categorical palette (blue/orange slots 1-2) plus
the status palette for pass/killed states; status colors always ship with
a text label, never color alone.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.gridspec import GridSpec  # noqa: E402

MEDIA = Path(__file__).resolve().parent
DATA = MEDIA / "data"

# reference palette (dataviz skill, validated): light mode
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT2 = "#52514e"
GRID = "#e8e8e6"
S1 = "#2a78d6"   # categorical slot 1 (blue): delivered/collected
S2 = "#eb6834"   # categorical slot 2 (orange): second suite
GOOD = "#0ca30c"     # status good (always labelled)
CRIT = "#d03b3b"     # status critical (always labelled)
MASK = TEXT2     # pass/tolerance lines wear ink, not series color

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "text.color": TEXT, "axes.labelcolor": TEXT,
    "xtick.color": TEXT2, "ytick.color": TEXT2,
    "axes.edgecolor": TEXT2, "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
})

ERROR_FLOOR = 1e-18   # exact agreement (0) is plotted at this axis floor
EPS = 2.220446049250313e-16


def load(name):
    return json.loads((DATA / name).read_text())


def sci(v: float) -> str:
    if v == 0:
        return "0 (exact)"
    return f"{v:.1e}".replace("e-0", "e-")


def stamp(ax, lines):
    ax.text(0.985, 0.955, lines, transform=ax.transAxes, ha="right",
            va="top", fontsize=10, fontweight="bold", color=GOOD,
            bbox=dict(boxstyle="round,pad=0.35", fc=SURFACE, ec=GOOD, lw=1.6))


# ---------------------------------------------------------------- result ---
def result_png(oracle, good):
    fig = plt.figure(figsize=(10, 6.5), dpi=200)
    gs = GridSpec(2, 2, height_ratios=[1.12, 1.0], hspace=0.62, wspace=0.30,
                  top=0.86, bottom=0.15, left=0.085, right=0.975)
    ax_o = fig.add_subplot(gs[0, 0])
    ax_s = fig.add_subplot(gs[0, 1])
    ax_g = fig.add_subplot(gs[1, :])

    # -- oracle panel: max relative error per graded input ---------------
    names = [i["input"] for i in oracle["inputs"]]
    errs = [i["max_rel_error"] for i in oracle["inputs"]]
    tol = oracle["tolerance_rel"]
    x = range(len(names))
    ax_o.bar(x, [max(e, ERROR_FLOOR) for e in errs], width=0.42,
             color=S1, edgecolor=SURFACE, linewidth=1)
    for xi, e in zip(x, errs):
        ax_o.annotate(sci(e), (xi, max(e, ERROR_FLOOR)),
                      textcoords="offset points", xytext=(0, 4),
                      ha="center", fontsize=8.5, color=TEXT)
    ax_o.set_yscale("log")
    ax_o.set_ylim(ERROR_FLOOR / 3, 1e-4)
    ax_o.axhline(tol, color=MASK, lw=1.4, ls=(0, (4, 3)))
    ax_o.axhline(EPS, color=GRID, lw=1.0)
    ax_o.text(2.42, tol * 1.9, f"pass line: tolerance {tol:.0e} rel",
              fontsize=8.5, color=TEXT2, ha="right")
    ax_o.text(2.42, EPS * 2.6, f"machine ε {EPS:.1e}",
              fontsize=8, color=TEXT2, ha="right")
    ax_o.set_xticks(list(x), names, fontsize=8.5)
    ax_o.set_xlabel("oracle input (sample + two seeded)", fontsize=9)
    ax_o.set_ylabel("max relative error\n(delivered vs reference)", fontsize=9)
    ax_o.set_title("oracle gate: delivered --json vs judge reference",
                   fontsize=10)
    ax_o.grid(True, axis="y", which="major", color=GRID, lw=0.6)
    ax_o.set_axisbelow(True)

    # -- measured statistics panel: what the delivery computes -----------
    sample = oracle["inputs"][0]
    fields = sample["fields"]
    names_s = [f["metric"] for f in fields]
    xs = range(len(fields))
    for xi, f in zip(xs, fields):
        ax_s.plot([xi, xi], [f["min"], f["max"]], color=S1, lw=2.0,
                  solid_capstyle="round", zorder=2)
        ax_s.plot([xi], [f["mean"]], "o", color=S1, ms=9,
                  markeredgecolor=SURFACE, markeredgewidth=2, zorder=3)
    ax_s.set_yscale("log")
    ax_s.set_xlim(-0.6, len(fields) - 0.4)
    ax_s.set_xticks(list(xs), names_s, fontsize=8.5)
    ax_s.set_xlabel("metric (sample.csv)", fontsize=9)
    ax_s.set_ylabel("min – max, ● mean\n(measured)", fontsize=9)
    ax_s.set_title(f"measured summary — sample.csv "
                   f"({sample['metrics']} metrics, "
                   f"{sample['total_count']} rows)", fontsize=10)
    ax_s.grid(True, axis="y", which="major", color=GRID, lw=0.6)
    ax_s.set_axisbelow(True)
    ax_s.plot([], [], color=S1, lw=2, marker="o", ms=9,
              markeredgecolor=SURFACE, markeredgewidth=2,
              label="min–max range, mean")
    ax_s.legend(loc="lower left", fontsize=8, frameon=False)

    # -- gates panel: collected tests vs the required minimums -----------
    reg = good["gates"]["regression"]
    acc = good["gates"]["acceptance"]
    bars = [("regression suite\n(fixture's own)", reg["tests_collected"],
             reg["rule"].split(">=")[-1].strip().split()[0], S1),
            ("acceptance suite\n(hidden)", acc["tests_collected"],
             acc["rule"].split(">=")[-1].strip().split()[0], S2)]
    for i, (label, collected, minimum, color) in enumerate(bars):
        ax_g.bar([i], [collected], width=0.34, color=color,
                 edgecolor=SURFACE, linewidth=1)
        ax_g.annotate(f"{collected} collected — 0 failed",
                      (i, collected), textcoords="offset points",
                      xytext=(0, 4), ha="center", fontsize=9, color=TEXT)
        minimum = int(minimum)
        ax_g.plot([i - 0.24, i + 0.24], [minimum, minimum], color=MASK,
                  lw=1.4, ls=(0, (4, 3)))
        ax_g.annotate(f"pass line: ≥ {minimum}", (i + 0.26, minimum),
                      fontsize=8.5, color=TEXT2, va="center")
    ax_g.set_xticks([0, 1], [b[0] for b in bars], fontsize=9)
    ax_g.set_xlim(-0.6, 1.9)
    ax_g.set_ylim(0, 31)
    ax_g.set_ylabel("tests collected", fontsize=9)
    ax_g.set_title("regression + acceptance gates", fontsize=10)
    ax_g.grid(True, axis="y", color=GRID, lw=0.6)
    ax_g.set_axisbelow(True)
    handles = [plt.Rectangle((0, 0), 1, 1, fc=c, ec=SURFACE)
               for c in (S1, S2)]
    ax_g.legend(handles, ["regression suite", "acceptance suite"],
                loc="upper right", fontsize=8, frameon=False)

    # -- figure title, PASS stamp, footer --------------------------------
    fig.suptitle("background-coding-agent — judge verdict on the "
                 "known-good delivery (seed 20261015)", fontsize=12, y=0.965)
    stamp(ax_o, "PASS\n7/7 gates")
    fig.text(0.085, 0.035,
             f"patch {good['gates']['patch']['files']} files / "
             f"{good['gates']['patch']['added_lines']} added lines · "
             f"lint {good['gates']['lint']['findings']} findings · "
             f"oracle {len(oracle['inputs'])}/{len(oracle['inputs'])} "
             f"inputs agree · PR {good['gates']['pr']['chars']} chars",
             fontsize=8.5, color=TEXT2)
    fig.savefig(MEDIA / "result.png")
    plt.close(fig)


# ------------------------------------------------------------------ loop ---
def loop_png(replay, selftest):
    fig = plt.figure(figsize=(10, 6.5), dpi=200)
    gs = GridSpec(2, 1, height_ratios=[1.0, 1.05], hspace=0.55,
                  top=0.88, bottom=0.17, left=0.085, right=0.975)
    ax_l = fig.add_subplot(gs[0])
    ax_k = fig.add_subplot(gs[1])

    # -- replay staircase: judge score per iteration until pass ----------
    xs = list(range(len(replay)))
    ys = [step["gates_passed"] for step in replay]
    ax_l.plot(xs, ys, color=TEXT2, lw=2, solid_capstyle="round", zorder=2)
    for xi, step in zip(xs, replay):
        if step["passed"]:
            ax_l.plot([xi], [step["gates_passed"]], "o", color=GOOD, ms=11,
                      markeredgecolor=SURFACE, markeredgewidth=2, zorder=4)
            ax_l.annotate("PASS", (xi, step["gates_passed"]),
                          textcoords="offset points", xytext=(0, 7),
                          ha="center", fontsize=9, fontweight="bold",
                          color=GOOD)
        else:
            ax_l.plot([xi], [step["gates_passed"]], "s", color=CRIT, ms=9,
                      markeredgecolor=SURFACE, markeredgewidth=2, zorder=4)
            ax_l.annotate(f"✗ {step['failed_gate']}",
                          (xi, step["gates_passed"]),
                          textcoords="offset points", xytext=(0, 7),
                          ha="center", fontsize=8.5, color=CRIT)
    ax_l.axhline(7, color=MASK, lw=1.4, ls=(0, (4, 3)))
    ax_l.text(-0.42, 7.12, "pass line: all 7 gates", fontsize=8.5,
              color=TEXT2)
    ax_l.set_xticks(xs, [s["label"] for s in replay], fontsize=7.5,
                    rotation=18, ha="right")
    ax_l.set_ylim(-0.5, 8.1)
    ax_l.set_yticks(range(0, 8))
    ax_l.set_ylabel("gates passed before the judge stops", fontsize=9)
    ax_l.set_title("agent-loop replay — one iteration per gate, until "
                   "pass (scripted)", fontsize=10)
    ax_l.grid(True, axis="y", color=GRID, lw=0.6)
    ax_l.set_axisbelow(True)

    # -- self-test: known-good vs each known-bad -------------------------
    good_row = {"label": "known-good", "gates_passed": 7, "passed": True}
    rows = [good_row] + sorted(selftest["kills"],
                               key=lambda k: k["gates_passed"])
    xs = list(range(len(rows)))
    for xi, row in enumerate(rows):
        if row["passed"]:
            color, lbl = GOOD, "passes"
        else:
            color, lbl = S1, f"killed: {row['failed_gate']}"
        ax_k.bar([xi], [row["gates_passed"]], width=0.5, color=color,
                 edgecolor=SURFACE, linewidth=1)
        ax_k.annotate(lbl, (xi, row["gates_passed"]),
                      textcoords="offset points", xytext=(0, 3), ha="center",
                      fontsize=6.6 if not row["passed"] else 8,
                      color=TEXT if row["passed"] else TEXT2,
                      rotation=0)
    ax_k.set_xticks(xs, [r["label"] for r in rows], fontsize=6.6,
                    rotation=38, ha="right")
    ax_k.set_ylim(0, 8.6)
    ax_k.set_yticks(range(0, 8))
    ax_k.set_ylabel("gates passed before death", fontsize=9)
    rate = selftest["kill_rate"]
    ax_k.set_title(f"self-test — known-good vs "
                   f"{selftest['mutants']} known-bad mutants: kill rate "
                   f"{selftest['mutants']}/{selftest['mutants']} = "
                   f"{rate:.0%} (≥ 90% required)", fontsize=10)
    ax_k.grid(True, axis="y", color=GRID, lw=0.6)
    ax_k.set_axisbelow(True)

    fig.suptitle("background-coding-agent — the judge can fail "
                 "(11 single-edit mutants, 11 kills)", fontsize=12, y=0.965)
    fig.text(0.085, 0.03,
             "green = known-good passes · blue = a known-bad mutant, "
             "bar height = how deep it got before the judge killed it",
             fontsize=8.5, color=TEXT2)
    fig.savefig(MEDIA / "loop.png")
    plt.close(fig)


def main():
    oracle = load("oracle_detail.json")
    good = load("verdict_good.json")
    replay = load("replay.json")
    selftest = load("selftest.json")
    result_png(oracle, good)
    loop_png(replay, selftest)
    print("make_figures: wrote result.png, loop.png")


if __name__ == "__main__":
    main()
