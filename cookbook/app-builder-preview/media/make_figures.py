#!/usr/bin/env python3
"""Figures for the app-builder-preview demo. Measured numbers only.

  result.png  the judge's key numbers for the known-good artifact: every
              flow's final DOM counts against the exact expected values,
              the build size against the 250 KiB budget, and the console
              error count against zero - the pass lines are drawn.
  loop.png    the scripted fixing replay (failing gates + failing flows per
              iteration until pass) and the self-test kill-rate bars.

Reads media/data/*.json (written by make_data.py from judge verdicts).
Colour-blind-safe Okabe-Ito palette.
"""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

MEDIA = Path(__file__).resolve().parent
DATA = MEDIA / "data"

# Okabe-Ito
BLUE, ORANGE, GREEN = "#0072B2", "#E69F00", "#009E73"
RED, GREY = "#D55E00", "#666666"
DPI = 200

FLOW_TITLES = {
    "add": "add 3 todos",
    "complete": "add 2, toggle first",
    "delete": "add 3, delete 2nd",
    "filter": "add 3, toggle 1st,\nfilter active",
    "persist": "add 2, toggle 1st,\nreload",
    "stats": "add 5, toggle 2,\ndelete 1",
}


def load(name):
    return json.loads((DATA / name).read_text())


def result_figure():
    good = load("grade_good.json")
    states = good["states"]
    flows = ["add", "complete", "delete", "filter", "persist", "stats"]
    expected_total = {"add": 3, "complete": 2, "delete": 2, "filter": 3,
                      "persist": 2, "stats": 4}

    fig = plt.figure(figsize=(12, 6.4), dpi=DPI)
    gs = fig.add_gridspec(2, 2, height_ratios=[2.1, 1], hspace=0.42,
                          wspace=0.24,
                          left=0.09, right=0.97, top=0.86, bottom=0.13)

    # --- observed vs expected DOM counts per flow -------------------------
    ax = fig.add_subplot(gs[0, :])
    width = 0.38
    for i, name in enumerate(flows):
        state = states.get(name) or {}
        obs = state.get("items") or []
        seen = len(obs)
        stats = state.get("stats") or {}
        total = int(stats.get("total") or 0)
        ax.bar(i - width / 2, seen, width, color=BLUE,
               edgecolor="black", linewidth=0.5)
        ax.bar(i + width / 2, total, width, color=ORANGE,
               edgecolor="black", linewidth=0.5)
        exp = expected_total[name]
        ax.hlines(exp, i - 0.75, i + 0.75, color=RED, linewidth=2.2,
                  linestyle="--")
    ax.set_xticks(range(len(flows)))
    ax.set_xticklabels([FLOW_TITLES[f] for f in flows], fontsize=8.5)
    ax.set_ylabel("items in the DOM")
    ax.set_yticks(range(0, 6))
    ax.bar(0, 0, color=BLUE, edgecolor="black", label="visible list items")
    ax.bar(0, 0, color=ORANGE, edgecolor="black", label="stats-total")
    ax.plot([], [], color=RED, linewidth=2.2, linestyle="--",
            label="spec expectation")
    ax.legend(loc="upper right", fontsize=8, framealpha=0.9)
    ax.set_title("Judge gate 4 - final DOM state after each scripted flow "
                 "(known-good artifact)", fontsize=10)

    # --- build size vs budget --------------------------------------------
    ax2 = fig.add_subplot(gs[1, 0])
    size_kib = good["gates"]["hygiene"]["dist_bytes"] / 1024
    ax2.bar([0], [size_kib], width=0.5, color=BLUE, edgecolor="black")
    ax2.axhline(250, color=RED, linewidth=2.2, linestyle="--")
    ax2.annotate(f"budget 250 KiB", xy=(0, 250), xytext=(0.32, 258),
                 fontsize=8.5, color=RED)
    ax2.annotate(f"{size_kib:.1f} KiB", xy=(0, size_kib),
                 xytext=(-0.08, size_kib + 8), fontsize=9)
    ax2.set_xlim(-0.6, 1.2)
    ax2.set_ylim(0, 300)
    ax2.set_xticks([])
    ax2.set_ylabel("dist/ size (KiB)")
    ax2.set_title("Judge gate 5 - build size budget", fontsize=10)

    # --- console errors vs zero ------------------------------------------
    ax3 = fig.add_subplot(gs[1, 1])
    n_err = len(good["gates"]["hygiene"]["console_errors"])
    ax3.bar([0], [n_err], width=0.5, color=BLUE, edgecolor="black")
    ax3.axhline(0, color=RED, linewidth=2.2, linestyle="--")
    ax3.annotate("budget 0 errors", xy=(0, 0), xytext=(0.28, 0.35),
                 fontsize=8.5, color=RED)
    ax3.annotate(f"{n_err} errors", xy=(0, n_err), xytext=(-0.05, 0.35),
                 fontsize=9)
    ax3.set_xlim(-0.6, 1.2)
    ax3.set_ylim(0, 1.2)
    ax3.set_xticks([])
    ax3.set_yticks([0, 1])
    ax3.set_ylabel("browser console errors")
    ax3.set_title("Judge gate 5 - console hygiene", fontsize=10)

    gates = good["gates"]
    fig.suptitle("app-builder-preview - prompt-to-running-web-app judged by "
                 "exact DOM state", fontsize=13)
    fig.text(0.09, 0.035,
             f"verdict: {'all 5 gates pass' if all(g['pass'] for g in gates.values()) else 'FAIL'} "
             f"(seed {good['seed']}) - flows {'/'.join(flows)} - reference "
             f"cross-check agrees - judge_intact "
             f"{str(good['judge_intact']).lower()}   "
             f"[bash judge/grade.sh examples/good/app --seed "
             f"{good['seed']}]", fontsize=8, color=GREY)
    fig.savefig(MEDIA / "result.png")
    plt.close(fig)


def loop_figure():
    replay = load("replay.json")["iterations"]
    selftest = load("selftest.json")

    fig = plt.figure(figsize=(12, 5.4), dpi=DPI)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.15, 1], wspace=0.28,
                          left=0.08, right=0.97, top=0.82, bottom=0.24)

    ax = fig.add_subplot(gs[0, 0])
    xs = [it["iteration"] for it in replay]
    fails = [len(it["failed_gates"]) for it in replay]
    colors = [GREEN if it["passed"] else BLUE for it in replay]
    ax.bar(xs, fails, width=0.55, color=colors, edgecolor="black",
           linewidth=0.5)
    ax.axhline(0, color=RED, linewidth=2.2, linestyle="--")
    ax.annotate("pass line: 0 failing gates", xy=(1, 0),
                xytext=(1.15, 0.12), fontsize=8.5, color=RED)
    for it in replay:
        label = "good" if it["passed"] else "+".join(it["failed_gates"])
        ax.annotate(label, xy=(it["iteration"], len(it["failed_gates"])),
                    xytext=(it["iteration"], len(it["failed_gates"]) + 0.06),
                    ha="center", fontsize=7.5)
    ax.set_xticks(xs)
    ax.set_xticklabels([it["artifact"] for it in replay], fontsize=8,
                       rotation=20, ha="right")
    ax.set_yticks(range(0, 3))
    ax.set_ylabel("failing gates")
    ax.set_ylim(0, 2.4)
    ax.set_title("Scripted fixing replay - failing gates per iteration\n"
                 "(mutants in the order a fixing agent meets them)", fontsize=10)

    ax2 = fig.add_subplot(gs[0, 1])
    names = [m["name"] for m in selftest["mutants"]] + ["known-good"]
    killed = [1 if m["killed"] else 0 for m in selftest["mutants"]] + [1]
    # good app "survives" the mutant-killer view: bar height = judge verdict
    # agreement (killed mutants are correct kills, good must pass)
    agree = killed[:-1] + [1 if selftest["known_good_passes"] else 0]
    ax2.bar(range(len(names)), agree, width=0.6,
            color=[GREEN if a else RED for a in agree],
            edgecolor="black", linewidth=0.5)
    ax2.axhline(0.9, color=RED, linewidth=2.2, linestyle="--")
    ax2.annotate("required kill rate 90%", xy=(0, 0.9), xytext=(0.3, 0.93),
                 fontsize=8.5, color=RED)
    ax2.set_xticks(range(len(names)))
    ax2.set_xticklabels(names, fontsize=7.5, rotation=30, ha="right")
    ax2.set_yticks([0, 1])
    ax2.set_ylim(0, 1.25)
    ax2.set_ylabel("killed / expected")
    ax2.set_title(f"Self-test - kill rate {selftest['kill_rate']} "
                  f"(known-good passes: "
                  f"{str(selftest['known_good_passes']).lower()})", fontsize=10)

    fig.suptitle("app-builder-preview - the judge fails bad apps, passes the "
                 "good one", fontsize=13)
    fig.text(0.08, 0.05,
             "[python3 -I media/make_data.py - media/make_figures.py; "
             "replay is scripted, not a recorded live trace]", fontsize=8,
             color=GREY)
    fig.savefig(MEDIA / "loop.png")
    plt.close(fig)


if __name__ == "__main__":
    result_figure()
    loop_figure()
    print("media: wrote result.png and loop.png")
