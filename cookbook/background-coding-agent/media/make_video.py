#!/usr/bin/env python3
"""Render demo.mp4 frames for the background-coding-agent demo.

A captioned step-through of the agent loop (no time-dependent physics to
animate): the replay staircase builds iteration by iteration, the oracle
panel draws against its pass line, the self-test kill bars fall in, and
the verdict card closes.  Every number comes from media/data/*.json --
no invented traces.

Writes frame%05d.png into $FRAMES_DIR (a temp dir made by make_media.sh).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

MEDIA = Path(__file__).resolve().parent
DATA = MEDIA / "data"
FRAMES_DIR = Path(os.environ.get("FRAMES_DIR", MEDIA / ".frames"))
FPS = 30

# reference palette (dataviz skill, validated): light mode
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT2 = "#52514e"
GRID = "#e8e8e6"
S1 = "#2a78d6"
S2 = "#eb6834"
GOOD = "#0ca30c"
CRIT = "#d03b3b"
MASK = TEXT2

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "text.color": TEXT, "axes.labelcolor": TEXT,
    "xtick.color": TEXT2, "ytick.color": TEXT2,
    "axes.edgecolor": TEXT2, "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
})

ERROR_FLOOR = 1e-18
EPS = 2.220446049250313e-16


def load(name):
    return json.loads((DATA / name).read_text())


def new_fig():
    fig = plt.figure(figsize=(19.2, 10.8), dpi=100)
    return fig


def caption(fig, text):
    fig.text(0.5, 0.055, text, ha="center", fontsize=21, color=TEXT2)


def title_card(frame_in, total):
    fig = new_fig()
    fig.text(0.5, 0.62, "background-coding-agent", ha="center",
             fontsize=64, fontweight="bold", color=TEXT)
    fig.text(0.5, 0.50, "an agent delivers a patch — a judge it cannot "
             "fool grades it", ha="center", fontsize=30, color=TEXT2)
    fig.text(0.5, 0.33, "measurectl --json  ·  7 gates  ·  "
             "oracle tolerance 1e-9 relative", ha="center", fontsize=24,
             color=TEXT2)
    caption(fig, "cookbook/background-coding-agent · run.py --ref <branch>")
    return fig


def loop_scene(replay, shown):
    fig = new_fig()
    ax = fig.add_axes([0.14, 0.30, 0.80, 0.48])
    xs = list(range(len(replay)))
    steps = replay[:shown]
    ys = [s["gates_passed"] for s in steps]
    ax.plot(xs[:shown], ys, color=TEXT2, lw=3, solid_capstyle="round",
            zorder=2)
    for xi, step in zip(xs[:shown], steps):
        if step["passed"]:
            ax.plot([xi], [step["gates_passed"]], "o", color=GOOD, ms=22,
                    markeredgecolor=SURFACE, markeredgewidth=3, zorder=4)
            ax.annotate("PASS", (xi, step["gates_passed"]),
                        textcoords="offset points", xytext=(0, 16),
                        ha="center", fontsize=26, fontweight="bold",
                        color=GOOD)
        else:
            ax.plot([xi], [step["gates_passed"]], "s", color=CRIT, ms=18,
                    markeredgecolor=SURFACE, markeredgewidth=3, zorder=4)
            ax.annotate(f"✗ {step['failed_gate']}",
                        (xi, step["gates_passed"]),
                        textcoords="offset points", xytext=(0, 16),
                        ha="center", fontsize=20, color=CRIT)
    ax.axhline(7, color=MASK, lw=2, ls=(0, (4, 3)))
    ax.text(-0.35, 7.15, "all 7 gates", fontsize=22, color=TEXT2)
    ax.set_xticks(xs, [s["label"] for s in replay], fontsize=17,
                  rotation=16, ha="right")
    ax.set_ylim(-0.5, 8.4)
    ax.set_yticks(range(0, 8))
    ax.tick_params(labelsize=18)
    ax.set_ylabel("gates passed", fontsize=22)
    ax.set_title("agent loop — judge score per iteration until pass",
                 fontsize=30)
    ax.grid(True, axis="y", color=GRID, lw=1)
    ax.set_axisbelow(True)
    caption(fig, "each delivery is graded; a failing gate names itself — "
                 "the loop ends at 7/7")
    return fig


def oracle_scene(oracle, reveal):
    fig = new_fig()
    ax = fig.add_axes([0.16, 0.34, 0.68, 0.42])
    inputs = oracle["inputs"][:reveal]
    names = [i["input"] for i in oracle["inputs"]]
    errs = [i["max_rel_error"] for i in inputs]
    tol = oracle["tolerance_rel"]
    ax.bar(range(len(errs)), [max(e, ERROR_FLOOR) for e in errs], width=0.4,
           color=S1, edgecolor=SURFACE, linewidth=2)
    for xi, e in enumerate(errs):
        label = "0 (exact)" if e == 0 else f"{e:.1e}"
        ax.annotate(label, (xi, max(e, ERROR_FLOOR)),
                    textcoords="offset points", xytext=(0, 6), ha="center",
                    fontsize=20, color=TEXT)
    ax.set_yscale("log")
    ax.set_ylim(ERROR_FLOOR / 3, 1e-4)
    ax.axhline(tol, color=MASK, lw=2, ls=(0, (4, 3)))
    ax.text(2.42, tol * 2.0, f"tolerance {tol:.0e} rel", fontsize=20,
            color=TEXT2, ha="right")
    ax.axhline(EPS, color=GRID, lw=1.4)
    ax.set_xticks(range(len(names)), names, fontsize=20)
    ax.tick_params(labelsize=19)
    ax.set_ylabel("max relative error\nvs judge reference", fontsize=22)
    ax.set_title("oracle gate — the delivered --json vs an independent "
                 "reference", fontsize=30)
    ax.grid(True, axis="y", which="major", color=GRID, lw=1)
    ax.set_axisbelow(True)
    caption(fig, "the judge recomputes every statistic on inputs the "
                 "agent never saw")
    return fig


def kill_scene(selftest, shown):
    fig = new_fig()
    ax = fig.add_axes([0.10, 0.36, 0.86, 0.40])
    good_row = {"label": "known-good", "gates_passed": 7, "passed": True}
    rows = [good_row] + sorted(selftest["kills"],
                               key=lambda k: k["gates_passed"])
    rows = rows[:shown]
    for xi, row in enumerate(rows):
        color = GOOD if row["passed"] else S1
        ax.bar([xi], [row["gates_passed"]], width=0.55, color=color,
               edgecolor=SURFACE, linewidth=2)
        label = "passes" if row["passed"] else row["failed_gate"]
        ax.annotate(label, (xi, row["gates_passed"]),
                    textcoords="offset points", xytext=(0, 5), ha="center",
                    fontsize=15, color=TEXT2, rotation=0)
    ax.set_xticks(range(len(rows)), [r["label"] for r in rows], fontsize=15,
                  rotation=34, ha="right")
    ax.set_ylim(0, 9.4)
    ax.set_yticks(range(0, 8))
    ax.tick_params(labelsize=18)
    ax.set_ylabel("gates passed before death", fontsize=22)
    rate = selftest["kill_rate"]
    ax.set_title(f"self-test — kill rate "
                 f"{selftest['mutants']}/{selftest['mutants']} = {rate:.0%} "
                 f"(≥ 90% required)", fontsize=30)
    ax.grid(True, axis="y", color=GRID, lw=1)
    ax.set_axisbelow(True)
    caption(fig, "eleven single-edit mutants of a passing delivery — "
                 "the judge kills every one")
    return fig


def verdict_scene(good):
    fig = new_fig()
    g = good["gates"]
    rows = [
        ("patch", f"{g['patch']['files']} files, "
         f"{g['patch']['added_lines']} added lines"),
        ("integrity", "tests/ + tool config untouched"),
        ("regression", f"{g['regression']['tests_collected']} collected, "
         f"{g['regression']['failed']} failed  (≥ 12)"),
        ("acceptance", f"{g['acceptance']['tests_collected']} collected, "
         f"{g['acceptance']['failed']} failed  (≥ 18)"),
        ("lint", f"{g['lint']['findings']} ruff diagnostics"),
        ("oracle", f"{len(g['oracle']['cases'])}/"
         f"{len(g['oracle']['cases'])} inputs ≤ 1e-9 rel"),
        ("pr", f"{g['pr']['chars']} chars, both sections"),
    ]
    fig.text(0.5, 0.80, "verdict — 7/7 gates pass", ha="center",
             fontsize=44, fontweight="bold", color=TEXT)
    for i, (gate, note) in enumerate(rows):
        y = 0.66 - i * 0.075
        fig.text(0.30, y, gate, ha="right", fontsize=28, color=TEXT2)
        fig.text(0.34, y, note, ha="left", fontsize=28, color=TEXT)
        fig.text(0.90, y, "✓", ha="center", fontsize=28, color=GOOD)
    fig.text(0.5, 0.045, "run.py --ref <branch>  →  exit 0, sandbox "
             "killed and confirmed gone", ha="center", fontsize=22,
             color=TEXT2)
    return fig


def main():
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    replay = load("replay.json")
    oracle = load("oracle_detail.json")
    selftest = load("selftest.json")
    good = load("verdict_good.json")

    # 30 s at 30 fps: title 3 s, loop 7.5 s, oracle 7.5 s, kills 7.5 s,
    # verdict 4.5 s.
    phases = [
        (0, 90, lambda f, n: title_card(f, n)),
        (90, 315, lambda f, n: loop_scene(
            replay, 1 + min(7, (f - 90) // 28))),
        (315, 540, lambda f, n: oracle_scene(
            oracle, 1 + min(2, (f - 315) // 45))),
        (540, 765, lambda f, n: kill_scene(
            selftest, 1 + min(11, (f - 540) // 18))),
        (765, 900, lambda f, n: verdict_scene(good)),
    ]
    total = phases[-1][1]
    print(f"Rendering {total} frames ({total / FPS:.0f} s) "
          f"to {FRAMES_DIR}", flush=True)
    for start, end, draw in phases:
        for f in range(start, end):
            fig = draw(f, end - start)
            fig.savefig(FRAMES_DIR / f"frame{f:05d}.png")
            plt.close(fig)
    print("Done rendering frames")


if __name__ == "__main__":
    main()
