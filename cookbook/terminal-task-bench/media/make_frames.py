#!/usr/bin/env python3
"""Render the 1920x1080 video frames (a captioned step-through of the
bench's own figures; the bench has no time-dependent physics to animate).

make_media.py calls render(); each slide is also saved into the figure
code paths used by result.png/loop.png so the video never shows a number
the figures do not.
"""

from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import make_media as mm

W, H = 9.6, 5.4          # inches at 200 dpi -> 1920x1080
HOLD = 4.0               # seconds each slide is held


def _new_slide():
    fig = plt.figure(figsize=(W, H), dpi=200)
    return fig


def _footer(fig, text):
    fig.text(0.5, 0.035, text, ha="center", fontsize=8, color="#555555")


def slide_title():
    fig = _new_slide()
    good = mm.load("grade_good.json")
    fig.text(0.5, 0.62, "terminal-task-bench", ha="center",
             fontsize=44, fontweight="bold", color=mm.INK)
    fig.text(0.5, 0.50, "ten broken filesystems · one agent program\n"
             "a judge it cannot fool decides whether each repair is right",
             ha="center", fontsize=18, color="#444444")
    fig.text(0.5, 0.30,
             f"seed {good['seed']} · solved "
             f"{good['gates']['G1_solve_count']['solved']}/10 · "
             f"kill rate 12/12", ha="center", fontsize=14,
             color=mm.GREEN, fontweight="bold")
    _footer(fig, "cookbook/terminal-task-bench — media/make_media.sh")
    return fig


def slide_tasks():
    fig = _new_slide()
    good = mm.load("grade_good.json")
    fig.suptitle("Ten tasks, ten independent oracles", fontsize=22,
                 fontweight="bold", y=0.94)
    oracles = {
        "wal-repair": "analytic expectation", "git-lost-branch": "git itself",
        "systemd-unit": "run the ExecStart program", "perms-maze":
        "run it unprivileged + mode mask", "csv-normalize":
        "canonical bytes", "json-config": "spec mask",
        "symlink-maze": "resolved paths", "tar-restore":
        "per-file sha256 + modes", "bugfix-python": "independent test",
        "cron-repair": "field expansion",
    }
    rows = good["tasks"]
    for i, row in enumerate(reversed(rows)):
        y = 0.09 + i * 0.085
        fig.text(0.08, y, row["task"], fontsize=13, family="monospace",
                 color=mm.INK)
        fig.text(0.38, y, oracles.get(row["task"], ""), fontsize=11,
                 color="#555555")
        fig.text(0.88, y, "solved" if row["solved"] else "FAIL",
                 fontsize=11, fontweight="bold",
                 color=mm.GREEN if row["solved"] else mm.VERM)
    _footer(fig, "verifier data: data/grade_good.json")
    return fig


def slide_result():
    fig = _new_slide()
    fig.suptitle("The judge's pass line", fontsize=22, fontweight="bold",
                 y=0.96)
    ax1 = fig.add_axes([0.07, 0.14, 0.40, 0.70])
    ax2 = fig.add_axes([0.55, 0.14, 0.40, 0.70])
    mm.draw_result(ax1, ax2)
    _footer(fig, "figure: media/result.png · data: grade_good.json, "
                 "grade_cheat.json")
    return fig


def slide_cheat():
    fig = _new_slide()
    cheat = mm.load("grade_cheat.json")
    fig.suptitle("The cheat that used to work", fontsize=22,
                 fontweight="bold", y=0.90)
    fig.text(0.5, 0.74, "An agent that repairs nothing, finds the judge's "
             "temp tree\nand rewrites every verify.sh to `exit 0`.",
             ha="center", fontsize=15, color="#444444")
    failed = [g for g, d in cheat["gates"].items() if not d["passed"]]
    fig.text(0.5, 0.50, "It is dead.  The oracle that grades a task is "
             "staged before the\nagent runs and byte-checked before the "
             "verifier executes.", ha="center", fontsize=15,
             color=mm.GREEN)
    fig.text(0.5, 0.32,
             f"failed gates: {', '.join(failed)}\n"
             f"solved {cheat['gates']['G1_solve_count']['solved']}/10 "
             "(verdict FAIL)", ha="center", fontsize=13,
             color=mm.VERM, fontweight="bold", family="monospace")
    _footer(fig, "regression test: judge/selftest.sh step 7 · "
                 "data: grade_cheat.json")
    return fig


def slide_loop():
    fig = _new_slide()
    fig.suptitle("The judge can fail: 12/12 mutants killed", fontsize=22,
                 fontweight="bold", y=0.96)
    ax1 = fig.add_axes([0.30, 0.10, 0.34, 0.78])
    ax2 = fig.add_axes([0.68, 0.14, 0.29, 0.70])
    ax1.set_yticklabels([])
    mm.draw_loop(ax1, ax2)
    _footer(fig, "figure: media/loop.png · data: selftest.log")
    return fig


def slide_end():
    fig = _new_slide()
    good = mm.load("grade_good.json")
    g1 = good["gates"]["G1_solve_count"]
    g3 = good["gates"]["G3_negative_control"]
    fig.text(0.5, 0.72, "All gates pass", ha="center", fontsize=34,
             fontweight="bold", color=mm.GREEN)
    fig.text(0.5, 0.52,
             f"G1 solved {g1['solved']}/{g1['total']} (pass line "
             f"{g1['required']})\n"
             f"G2 all ten pristine trees rejected\n"
             f"G3 negative control {g3['negctl_solved']}/10\n"
             f"G4 verifier wall time "
             f"{good['timing']['total_verify_seconds']} s of 300 s\n"
             f"G5 oracle untouched, 10/10 byte-verified\n"
             f"self-test kill rate 12/12", ha="center", fontsize=15,
             color=mm.INK, family="monospace")
    _footer(fig, "python3 cookbook/terminal-task-bench/run.py")
    return fig


def render(outdir: str) -> None:
    os.makedirs(outdir, exist_ok=True)
    slides = [slide_title(), slide_tasks(), slide_result(), slide_cheat(),
              slide_loop(), slide_end()]
    for i, fig in enumerate(slides):
        fig.savefig(os.path.join(outdir, f"frame_{i:04d}.png"))
        plt.close(fig)
    # ffmpeg concat list: hold each slide HOLD seconds at 30 fps
    with open(os.path.join(outdir, "concat.txt"), "w") as fh:
        for i in range(len(slides)):
            fh.write(f"file 'frame_{i:04d}.png'\nduration {HOLD:.2f}\n")
        fh.write(f"file 'frame_{len(slides) - 1:04d}.png'\n")
    print(f"make_media: wrote {len(slides)} frames to {outdir}")
