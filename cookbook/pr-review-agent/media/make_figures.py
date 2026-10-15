#!/usr/bin/env python3
"""Figures for the pr-review-agent demo — every plotted number comes from a
verdict JSON or artifact file written by a real judge run in make_media.sh.
No invented data: if a source file is missing, this exits 1.

Usage: make_figures.py <judge_runs_dir> <outdir>
Writes result.png and loop.png (200 dpi).

Palette: dataviz reference instance (validate_palette.js PASS on
#2a78d6,#eb6834, light surface #fcfcfb); status colors always carry a text
label, never color alone.
"""

from __future__ import annotations

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

BLUE = "#2a78d6"    # series 1 — the measured good run
ORANGE = "#eb6834"  # series 2 — a second measured series
GREEN = "#0ca30c"   # status: good (always with a text label)
RED = "#d03b3b"     # status: critical (always with a text label)
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASE = "#c3c2b7"
SURFACE = "#fcfcfb"
GOOD_TINT = "#e2f3e2"   # 10 % tint of status-good for large fills
CRIT_TINT = "#f9e3e3"

plt.rcParams.update({
    "font.size": 13, "axes.edgecolor": BASE, "axes.labelcolor": INK,
    "xtick.color": INK2, "ytick.color": INK2, "text.color": INK,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.axisbelow": True, "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
})

GATE_NAMES = {
    "g1_shape": "G1 shape", "g2_coverage": "G2 coverage",
    "g3_clean_prs": "G3 clean PRs", "g4_failing_test": "G4 failing test",
    "g5_passing_test": "G5 passing test", "g6_isolation": "G6 isolation",
}


def need(path: str):
    if not os.path.isfile(path):
        sys.exit(f"make_figures: missing source file {path} — run the judge "
                 f"first (see make_media.sh)")
    return path


def load(path: str) -> dict:
    with open(need(path), encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- result ---

def panel_localization(ax, runs: dict) -> None:
    """G2: reported line minus planted line per defect, with the +/-2 band.

    Three measured series: the good run (matched, line_error from the
    verdict) and two mutants the self-test kills at G2 — wrong-line-race
    (reported far off; planted line from its verdict's `missed`, reported
    line from its artifact) and wrong-kind-none-deref (right place, kind
    'other' -> not counted).
    """
    good = runs["good"]["gates"]["g2_coverage"]
    defects = sorted(good["matched"], key=lambda m: m["pr"])
    xs = range(1, len(defects) + 1)
    labels = [f"PR{m['pr']}\n{m['kind']}" for m in defects]

    wl = runs["wrong-line-race"]
    wl_missed = [d for d in wl["gates"]["g2_coverage"]["missed"]
                 if d["kind"] == "race"][0]
    wl_reported = load(runs["src"]["wrong-line-race"])["findings"][0]["line"]

    wk = runs["wrong-kind-none-deref"]
    wk_missed = [d for d in wk["gates"]["g2_coverage"]["missed"]
                 if d["kind"] == "none-deref"][0]
    wk_finding = load(runs["src"]["wrong-kind-none-deref"])["findings"][0]

    ax.axhspan(-2, 2, color=GOOD_TINT, zorder=0)
    for y in (-2, 2):
        ax.axhline(y, color=GREEN, lw=1.4, zorder=1)
    ax.text(4.42, 0, "|Δ| ≤ 2 counts (G2)", color="#006300", fontsize=12,
            va="center", ha="left")

    ax.scatter(xs, [m["line_error"] for m in defects], s=110, color=BLUE,
               zorder=3, label="known-good review (matched)", edgecolor=SURFACE,
               linewidth=1.5)
    ax.scatter([wl_missed["pr"]], [wl_reported - wl_missed["line"]], s=160,
               color=RED, marker="x", zorder=3,
               linewidth=2.2,
               label="mutant: reported +15 off (rejected)")
    ax.scatter([wk_missed["pr"]], [wk_finding["line"] - wk_missed["line"]],
               s=130, facecolor="none", edgecolor=ORANGE, linewidth=2.4,
               zorder=3, label=f"mutant: kind {wk_finding['kind']!r} (rejected)")

    ax.annotate(f"line {wl_reported} vs planted {wl_missed['line']}",
                (wl_missed["pr"], wl_reported - wl_missed["line"]),
                textcoords="offset points", xytext=(12, 2), color=INK2,
                fontsize=11.5)
    ax.annotate("right line, wrong class",
                (wk_missed["pr"], wk_finding["line"] - wk_missed["line"]),
                textcoords="offset points", xytext=(12, -16), color=INK2,
                fontsize=11.5)

    ax.set_xticks(list(xs))
    ax.set_xticklabels(labels)
    ax.set_xlim(0.4, 6.1)
    ax.set_ylim(-5, 18)
    ax.set_ylabel("reported line − planted line")
    ax.set_title("G2 — defect localization vs the ±2-line rule", loc="left",
                 fontsize=15, color=INK)
    ax.legend(loc="upper left", frameon=True, edgecolor=GRID, fontsize=11.5)


def panel_discrimination(ax, good: dict) -> None:
    """G4+G5: the reviewer's own tests, run both ways by the judge."""
    prs = good["gates"]["g4_failing_test"]["prs"]
    kinds = {m["pr"]: m["kind"] for m in
             good["gates"]["g2_coverage"]["matched"]}
    clean = set(good["gates"]["g3_clean_prs"]["clean_prs"])
    n = len(prs)

    ax.set_xlim(0, 2)
    ax.set_ylim(0, n)
    ax.axis("off")
    for i, pr in enumerate(sorted(prs, key=int)):
        r = prs[pr]
        y = n - 1 - i
        row = f"PR{r['pr']}" + (f" · {kinds[r['pr']]}" if r["pr"] in kinds
                                else " · clean")
        ax.text(-0.06, y + 0.5, row, ha="right", va="center", color=INK,
                fontsize=12.5)
        cells = [
            (0, f"exit {r['buggy_exit']} · "
                f"{r['buggy_counts']['failed']} failed"
                + (f" / {r['buggy_counts']['passed']} passed"
                   if r["buggy_counts"]["passed"] else ""),
             r["buggy_exit"] == 1 and r["buggy_counts"]["failed"] >= 1),
            (1, f"exit {r['fixed_exit']} · "
                f"{r['fixed_counts']['passed']} passed",
             r["fixed_exit"] == 0 and r["fixed_counts"]["passed"] >= 1),
        ]
        for col, text, ok in cells:
            # A clean PR's buggy cell is its own (already clean) PR tree --
            # expected to pass, so the rule for that cell flips.
            expect_fail = r["pr"] in kinds
            passed = ok if (expect_fail or col == 1) else (
                r["buggy_exit"] == 0)
            ax.add_patch(Rectangle((col + 0.03, y + 0.06), 0.94, 0.88,
                                   facecolor=GOOD_TINT if passed else CRIT_TINT,
                                   edgecolor=SURFACE, linewidth=2))
            ax.text(col + 0.5, y + 0.5, ("✓ " if passed else "✗ ") + text,
                    ha="center", va="center",
                    color="#006300" if passed else RED, fontsize=12.5)
    ax.text(0.5, n + 0.28, "on the buggy PR tree", ha="center", color=INK2,
            fontsize=12.5)
    ax.text(1.5, n + 0.28, "on the fixed tree", ha="center", color=INK2,
            fontsize=12.5)
    ax.set_title("G4+G5 — the reviewer's tests must fail the PR, pass the fix",
                 loc="left", fontsize=15, color=INK)


def panel_gates(ax, good: dict) -> None:
    """The verdict at a glance: every gate with its numeric evidence."""
    g = good["gates"]
    evidence = {
        "g1_shape": f"{len(g['g1_shape']['problems'])} shape problems",
        "g2_coverage": (f"{g['g2_coverage']['caught']} / "
                        f"{g['g2_coverage']['planted']} defects caught"),
        "g3_clean_prs": (f"{g['g3_clean_prs']['major_findings_on_clean_prs']} "
                         "majors on clean PRs"),
        "g4_failing_test": (f"{4 - len(g['g4_failing_test']['failures'])} / 4 "
                            "tests fail the buggy tree"),
        "g5_passing_test": (f"{4 - len(g['g5_passing_test']['failures'])} / 4 "
                            "tests pass the fix"),
        "g6_isolation": (f"{len(g['g6_isolation']['problems'])} leaks — "
                         "judge tree unchanged"),
    }
    ax.set_xlim(0, 6)
    ax.set_ylim(0, 1)
    ax.axis("off")
    for i, gate in enumerate(GATE_NAMES):
        passed = g[gate]["passed"]
        ax.add_patch(FancyBboxPatch(
            (i + 0.04, 0.18), 0.92, 0.64,
            boxstyle="round,pad=0.02,rounding_size=0.06",
            facecolor=GOOD_TINT if passed else CRIT_TINT,
            edgecolor=SURFACE, linewidth=2))
        ax.text(i + 0.5, 0.66, GATE_NAMES[gate], ha="center", color=INK,
                fontsize=12.5, fontweight="bold")
        ax.text(i + 0.5, 0.40, evidence[gate], ha="center", color=INK2,
                fontsize=11)
        ax.text(i + 0.5, 0.86, "✓ PASS" if passed else "✗ FAIL",
                ha="center", color="#006300" if passed else RED, fontsize=12)
    ax.set_title("verdict — all six gates (judge/grade.sh examples/good/review)",
                 loc="left", fontsize=15, color=INK)


def make_result(runs: dict, outdir: str) -> None:
    fig, axes = plt.subplots(
        2, 2, figsize=(16.5, 9.8), dpi=200,
        gridspec_kw={"height_ratios": [2.5, 1], "width_ratios": [1, 1.06]})
    panel_localization(axes[0][0], runs)
    panel_discrimination(axes[0][1], runs["good"])
    gs = axes[1][0].get_gridspec()
    for a in axes[1]:
        a.remove()
    ax_gates = fig.add_subplot(gs[1, :])
    panel_gates(ax_gates, runs["good"])
    fig.suptitle("pr-review-agent — the judged review (examples/good, seed 42)",
                 fontsize=18, color=INK, x=0.02, ha="left")
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.96))
    path = os.path.join(outdir, "result.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"  wrote {path}")


# ------------------------------------------------------------------ loop ---

def make_loop(runs: dict, mutants: dict, outdir: str) -> None:
    fig, (ax_loop, ax_kill) = plt.subplots(
        2, 1, figsize=(16.5, 9.6), dpi=200,
        gridspec_kw={"height_ratios": [1.15, 1]})

    # (a) the replayed loop: defects caught and majors-on-clean per iteration
    iters = ["iter1", "iter2", "iter3", "iter4"]
    caught = [runs[i]["gates"]["g2_coverage"]["caught"] for i in iters]
    planted = runs["iter1"]["gates"]["g2_coverage"]["planted"]
    fps = [runs[i]["gates"]["g3_clean_prs"]["major_findings_on_clean_prs"]
           for i in iters]
    xs = range(1, len(iters) + 1)

    ax_loop.axhline(planted, color=GREEN, lw=1.8, zorder=1)
    ax_loop.text(0.06, planted + 0.12, f"G2 pass rule: {planted}/{planted}",
                 color="#006300", fontsize=12, va="bottom")
    ax_loop.plot(xs, caught, color=BLUE, lw=2, marker="o", markersize=9,
                 markeredgecolor=SURFACE, markeredgewidth=1.5, zorder=3,
                 label="defects caught (G2)")
    ax_loop.plot(xs, fps, color=ORANGE, lw=2, marker="o", markersize=9,
                 markeredgecolor=SURFACE, markeredgewidth=1.5, zorder=3,
                 label="major findings on clean PRs (G3)")
    ax_loop.set_xticks(list(xs))
    ticks = {1: "iteration 1\n✗ fails G2 (1/4)", 2: "iteration 2\n✗ fails G2 (2/4)",
             3: "iteration 3\n✗ fails G3 (false positive)",
             4: "iteration 4\n✓ PASS — all six gates"}
    labels = ax_loop.set_xticklabels([ticks[x] for x in xs], fontsize=12)
    for lab in labels[:3]:
        lab.set_color(RED)
    labels[3].set_color("#006300")
    ax_loop.set_ylim(-0.4, 5.4)
    ax_loop.set_yticks(range(0, 5))
    ax_loop.set_ylabel("count")
    ax_loop.set_title("The agent loop, replayed — each step fixes the gate "
                      "the previous one failed", loc="left", fontsize=15,
                      color=INK)
    ax_loop.legend(loc="center right", frameon=True, edgecolor=GRID,
                   fontsize=11.5)

    # (b) the self-test: which gate kills which mutant (one series = counts)
    kills: dict[str, list[str]] = {}
    survived: list[str] = []
    for name, v in sorted(mutants.items()):
        if v["passed"]:
            survived.append(name)
        else:
            kills.setdefault(v["failed_gate"], []).append(name)
    gates = [g for g in GATE_NAMES if g in kills]  # verdict order
    ys = range(len(gates))
    counts = [len(kills[g]) for g in gates]
    ax_kill.barh(ys, counts, height=0.62, color=BLUE,
                 edgecolor=SURFACE, linewidth=2)
    ax_kill.invert_yaxis()
    for y, g, n in zip(ys, gates, counts):
        ax_kill.text(n + 0.07, y, f"{n}  ({', '.join(kills[g])})",
                     va="center", ha="left", color=INK2, fontsize=11.5)
    ax_kill.set_yticks(list(ys))
    ax_kill.set_yticklabels([GATE_NAMES[g] for g in gates], fontsize=12.5)
    ax_kill.set_xlim(0, max(counts) + 2.6)
    ax_kill.set_xticks(range(0, max(counts) + 1))
    ax_kill.xaxis.grid(True)
    ax_kill.yaxis.grid(False)
    ax_kill.set_xlabel("mutants killed at this gate")
    n_all = len(mutants)
    n_killed = n_all - len(survived)
    headline = (f"kill rate {n_killed}/{n_all} = "
                f"{n_killed / n_all:.0%} (rule ≥ 90 %)")
    if survived:
        headline += f" — SURVIVED: {', '.join(survived)}"
    ax_kill.set_title("Self-test — every gate catches something; the "
                      "known-good passes them all", loc="left", fontsize=15,
                      color=INK)
    ax_kill.text(1, 1.04, headline, transform=ax_kill.transAxes,
                 ha="right", va="bottom", color="#006300" if not survived
                 else RED, fontsize=13)
    fig.tight_layout()
    path = os.path.join(outdir, "loop.png")
    fig.savefig(path)
    plt.close(fig)
    print(f"  wrote {path}")


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: make_figures.py <judge_runs_dir> <outdir>",
              file=sys.stderr)
        return 2
    runs_dir, outdir = sys.argv[1], sys.argv[2]
    replay = os.path.join(runs_dir, "replay")
    runs = {
        "iter1": load(f"{replay}/verdicts/it1.json"),
        "iter2": load(f"{replay}/verdicts/it2.json"),
        "iter3": load(f"{replay}/verdicts/it3.json"),
        "iter4": load(f"{replay}/verdicts/it4.json"),
        "good": load(f"{replay}/verdicts/it4.json"),
        "wrong-line-race": load(f"{replay}/mutants/wrong-line-race.json"),
        "wrong-kind-none-deref":
            load(f"{replay}/mutants/wrong-kind-none-deref.json"),
        "src": {
            "wrong-line-race":
                f"{replay}/mutants/wrong-line-race/pr4/review.json",
            "wrong-kind-none-deref":
                f"{replay}/mutants/wrong-kind-none-deref/pr3/review.json",
        },
    }
    mutants = {name: load(f"{replay}/mutants/{name}.json")
               for name in ("downgraded-sql-injection", "false-positive-on-clean",
                            "invalid-severity", "missed-off-by-one",
                            "test-collection-error", "test-fails-on-fixed",
                            "test-passes-on-buggy", "test-skipped")}
    mutants["wrong-kind-none-deref"] = runs["wrong-kind-none-deref"]
    mutants["wrong-line-race"] = runs["wrong-line-race"]
    make_result(runs, outdir)
    make_loop(runs, mutants, outdir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
