#!/usr/bin/env python3
"""result.png and loop.png for the skill-ab-bench demo.

Every number is read from the files judge/grade.sh, judge/bench.py,
judge/selftest.sh and judge/mutants.py wrote during the replay in this
sandbox (media/data/); nothing is synthesised.  Run media/replay_judge.sh
first.

    python3 media/figures.py          # writes media/result.png media/loop.png

Both figures get the layout check the demo standard requires: any text
bbox that leaves the figure or intersects another text bbox fails the
run (media/scripts/common.py:check_layout).
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent / "scripts"))
import common as C  # noqa: E402

PT100 = 100.0
GATES = ["G1_record_shape", "G2_arm_isolation", "G3_verifier_replay",
         "G4_task_identifiability", "G5_power", "G6_effect_size",
         "G7_placebo_control", "G8_judge_integrity", "G9_arm_fidelity"]
GATE_SHORT = {g: g.split("_", 1)[0] for g in GATES}


def pts(value: float) -> str:
    """A JSON fraction (0.9375) in pass-rate points, without trailing zeros."""
    return f"{value * PT100:g}"


def figure_frame(rows: int):
    fig = plt.figure(figsize=(12.0, 6.75), dpi=200, facecolor="white")
    return fig


# ------------------------------------------------------------------ result

def result_figure() -> plt.Figure:
    """The key figure: pass counts per arm, and the deltas with their
    bootstrap CIs against the judge's pass line (verdict-bench-fresh.json)."""
    v = C.load_verdict("verdict-bench-fresh")
    g6, g7 = C.gate(v, "G6_effect_size"), C.gate(v, "G7_placebo_control")
    n = int(g6["n"])
    arms = [
        ("skill", g6["skill_passes"], C.SKILL),
        ("noskill", g6["noskill_passes"], C.NOSKILL),
        ("placebo", g7["placebo_passes"], C.PLACEBO),
    ]
    ci = C.ci_block(v)
    ci7 = C.ci_block(v, "G7_placebo_control")
    seed = v["seed"]
    resamples = v["bootstrap_resamples"]
    p = C.fisher_p(v)

    fig = figure_frame(2)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.45], wspace=0.24,
                          left=0.075, right=0.965, top=0.76, bottom=0.155)

    # -- left: pass counts ---------------------------------------------------
    ax = fig.add_subplot(gs[0, 0])
    ax.set_title("one bench run: 48 fresh-interpreter pairs", fontsize=13,
                 pad=14)
    xs = range(len(arms))
    counts = [a[1] for a in arms]
    bars = ax.bar(xs, counts, width=0.62,
                  color=[a[2] for a in arms], edgecolor="none")
    for x, bar, count in zip(xs, bars, counts):
        ax.text(x, count + 0.45, f"{count}/{n}", ha="center", va="bottom",
                fontsize=13, fontweight="bold", color=bar.get_facecolor())
    ax.set_xticks(list(xs), [a[0] for a in arms], fontsize=13)
    ax.set_xlim(-0.6, len(arms) - 0.4)
    ax.set_ylim(0, n * 1.22)
    ax.set_yticks(range(0, n + 1, 4))
    ax.set_ylabel(f"tasks passed (of {n})", fontsize=12)
    ax.grid(axis="y", color=C.GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)

    # -- right: the deltas the judge gates on --------------------------------
    ax = fig.add_subplot(gs[0, 1])
    ax.set_title("pass-rate deltas with bootstrap CIs (resampling tasks)",
                 fontsize=13, pad=14)
    rows = [
        ("skill − noskill\n(the skill's effect)",
         g6["delta_pts"], ci["lo"] * PT100, ci["hi"] * PT100, C.SKILL),
        ("noskill − placebo\n(the placebo control)",
         g7["delta_pts"], ci7["lo"] * PT100, ci7["hi"] * PT100, C.PLACEBO),
    ]
    ax.axvspan(PASS := C.PASS_LINE_PTS, 105, color=C.PLACEBO, alpha=0.07)
    ax.axvline(0, color=C.MUTED, linewidth=1.2)
    ax.axvline(PASS, color=C.FAIL, linewidth=1.8, linestyle=(0, (5, 3)))
    for y, (label, delta, lo, hi, color) in enumerate(rows):
        ax.plot([lo, hi], [y, y], color=color, linewidth=5,
                solid_capstyle="round")
        ax.plot(delta, y, "o", markersize=11, color=color)
    ax.set_yticks([0, 1], [r[0] for r in rows], fontsize=11.5)
    ax.set_ylim(-0.85, 1.75)
    ax.set_xlim(-48, 105)
    ax.set_xticks([-25, 0, 25, 50, 75, 100])
    ax.set_xlabel("pass-rate delta (points; 16 tasks per arm)", fontsize=12)
    ax.grid(axis="x", color=C.GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.text(PASS + 2, 1.62, "judge's pass line: Δ ≥ 25.0 pts", fontsize=11.5,
            color=C.FAIL, va="center", ha="left")
    ax.text(1, 0.38, f"Δ = +{g6['delta_pts']:g} pts,  CI [{pts(ci['lo'])}, "
                     f"{pts(ci['hi'])}] → PASS", fontsize=12.5,
            fontweight="bold", color=C.SKILL, ha="left", va="center")
    ax.text(1, -0.52, f"Δ = {g7['delta_pts']:g} pts,  CI "
                      f"[{pts(ci7['lo'])}, {pts(ci7['hi'])}] contains 0 → "
                      "placebo not crowned", fontsize=12.5, fontweight="bold",
            color=C.PLACEBO, ha="left", va="center")

    fig.suptitle("skill-ab-bench: 16/16 with the skill vs 4/16 without — "
                 f"Δ = +{g6['delta_pts']:g} pts, CI "
                 f"[{ci['lo']:.3f}, {ci['hi']:.3f}], Fisher p = {p:.2e}",
                 fontsize=15.5, fontweight="bold", x=0.075, ha="left", y=0.965)
    fig.text(0.075, 0.052,
             f"known-good record and a fresh bench run both PASS every gate; "
             f"seed {seed}, {resamples:,} bootstrap resamples",
             fontsize=11.5, color=C.MUTED)
    fig.text(0.075, 0.016,
             "source: bash media/replay_judge.sh — judge/grade.sh on a fresh "
             "judge/bench.py record  ·  media/data/verdict-bench-fresh.json",
             fontsize=10.5, color=C.MUTED)
    C.check_layout(fig)
    return fig


# -------------------------------------------------------------------- loop

def loop_figure() -> plt.Figure:
    """The agent loop (three graded records until pass) and the self-test
    kill matrix (known-good vs every known-bad)."""
    fresh = C.load_verdict("verdict-bench-fresh")
    swapped = C.load_verdict("verdict-arms-swapped")
    marginal = C.load_verdict("verdict-marginal-win")
    killed, total, rate = C.kill_rate()
    good = C.gate(fresh, "G6_effect_size")
    bad = C.gate(swapped, "G6_effect_size")
    m5 = C.gate(marginal, "G5_power")
    m_delta = (m5["skill_passes"] - m5["noskill_passes"]) * PT100 / m5["n"]
    bad_ci = C.ci_block(swapped)
    good_ci = C.ci_block(fresh)

    fig = figure_frame(2)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.05], wspace=0.26,
                          left=0.08, right=0.965, top=0.75, bottom=0.16)

    # -- left: delta per graded record, until pass ---------------------------
    ax = fig.add_subplot(gs[0, 0])
    ax.set_title("the loop: grade → fix → grade (a replay of graded records)",
                 fontsize=13, pad=14)
    iters = [
        ("1\narms-swapped", bad["delta_pts"], bad_ci["lo"] * PT100,
         bad_ci["hi"] * PT100, "G6 ✗", C.FAIL),
        ("2\nmarginal-win", m_delta, None, None,
         f"G5 ✗  p = {C.fisher_p(marginal):.3f}", C.FAIL),
        ("3\nbench-fresh", good["delta_pts"], good_ci["lo"] * PT100,
         good_ci["hi"] * PT100, "PASS", C.PLACEBO),
    ]
    ax.axhline(0, color=C.MUTED, linewidth=1.2)
    ax.axhline(C.PASS_LINE_PTS, color=C.FAIL, linewidth=1.8,
               linestyle=(0, (5, 3)))
    for x, (label, delta, lo, hi, stamp, color) in enumerate(iters):
        if lo is not None:
            ax.plot([x, x], [lo, hi], color=color, linewidth=5,
                    solid_capstyle="round")
        ax.plot(x, delta, "o", markersize=13, color=color)
        ax.text(x, delta + (13 if delta >= 0 else -13),
                f"Δ = {delta:+g} pts", ha="center",
                va="bottom" if delta >= 0 else "top", fontsize=12.5,
                fontweight="bold", color=color)
        ax.text(x + 0.16, delta, stamp, ha="left", va="center",
                fontsize=12.5, fontweight="bold", color=color)
    ax.text(2.42, 34, "G6 pass line: Δ ≥ 25.0 pts", fontsize=11.5,
            color=C.FAIL, ha="right", va="bottom")
    ax.text(-0.44, -97, "no CI on record 2: G5 stopped\nthe grade before G6",
            fontsize=10.5, color=C.MUTED, ha="left", va="bottom")
    ax.set_xticks(range(3), [it[0] for it in iters], fontsize=11.5)
    ax.set_xlim(-0.55, 2.55)
    ax.set_ylim(-118, 118)
    ax.set_ylabel("measured pass-rate delta (points)", fontsize=12)
    ax.grid(axis="y", color=C.GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)

    # -- right: the self-test kill matrix ------------------------------------
    ax = fig.add_subplot(gs[0, 1])
    ax.set_title(f"self-test: known-good passes, every known-bad is killed "
                 f"({killed}/{total} = {rate:.0f} %)", fontsize=13, pad=14)
    rows = [("known-good\n(examples/good)", None)] + [
        (r["record"].removesuffix("/results.json").removesuffix("/")
         .removeprefix("records/").removeprefix("judge/"), r["gate"])
        for r in C.kill_matrix()
    ]
    ys = range(len(rows))
    for y, (name, gate_name) in zip(ys, rows):
        if gate_name is None:
            ax.barh(y, 1.0, height=0.62, color=C.SKILL)
            ax.text(0.985, y, "passes every gate — must not be killed",
                    ha="right", va="center", fontsize=10.5, color="white",
                    fontweight="bold")
        else:
            ax.barh(y, 1.0, height=0.62, color=C.PLACEBO)
            ax.text(0.985, y, f"killed at {GATE_SHORT[gate_name]}",
                    ha="right", va="center", fontsize=10.5, color="white",
                    fontweight="bold")
    ax.set_yticks(list(ys), [r[0] for r in rows], fontsize=10)
    ax.set_ylim(len(rows) - 0.4, -0.6)
    ax.set_xlim(0, 1.0)
    ax.set_xticks([])
    for side in ("top", "right", "bottom", "left"):
        ax.spines[side].set_visible(False)

    fig.suptitle("skill-ab-bench: −75 → +25 (not significant) → +75 PASS — "
                 "the judge decides, and the self-test proves it can fail",
                 fontsize=15.5, fontweight="bold", x=0.08, ha="left", y=0.965)
    fig.text(0.08, 0.052,
             "records graded in sequence: arms-swapped dies at G6 "
             f"(Δ = {bad['delta_pts']:g} pts), marginal-win (16/16 vs "
             f"{m5['noskill_passes']}/16) dies at G5 (p = "
             f"{C.fisher_p(marginal):.3f}), the fresh bench record passes",
             fontsize=11.5, color=C.MUTED)
    fig.text(0.08, 0.016,
             "source: bash media/replay_judge.sh — one grade per record  ·  "
             "media/data/verdict-*.json, selftest.log, mutants.log",
             fontsize=10.5, color=C.MUTED)
    C.check_layout(fig)
    return fig


def main() -> int:
    C.require_sources()
    out = C.MEDIA
    for name, maker in (("result.png", result_figure),
                        ("loop.png", loop_figure)):
        fig = maker()
        path = out / name
        fig.savefig(path, facecolor="white")
        print(f"figures: wrote {path.relative_to(C.DEMO)} "
              f"({path.stat().st_size / 1024:.0f} kB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
