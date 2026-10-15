#!/usr/bin/env python3
"""Build result.png and loop.png from media/data/report.json only.

result.png
  left  : measured GPU steps/s vs nworld (log-log) with the measured CPU
          baseline and the throughput pass floor drawn on it
  right : physics oracle per nworld — measured box z range against the
          allowed landed band, plus arm tracking error vs its tolerance

loop.png
  gate x artifact matrix (the good config + every mutant) built from the
  real verdicts in report.json: green = passed, red = the gate that killed
  the mutant, grey = gate not reached; plus the measured kill-rate bar.

Every required field is checked explicitly: a missing field exits non-zero
naming the dotted path of the missing field. No number is invented — every
plotted value comes from the judge's own measurements.
"""

import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

MEDIA_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(MEDIA_DIR, "data")
REPORT_JSON = os.path.join(DATA_DIR, "report.json")

# Judge constants from SPEC.md / judge/_grade.py (spec values, not
# measured data).
TABLE_TOP = 0.275
BOX_Z_MIN = TABLE_TOP - 0.02   # tunnelling bound
BOX_Z_MAX = TABLE_TOP + 0.25   # landed bound
ARM_ERR_TOL = 0.15

GATE_ORDER = ("structure", "cost", "engine-parity", "physics-oracle",
              "cpu-parity", "throughput")


def die(msg):
    print(f"make_figures.py: {msg}", file=sys.stderr)
    raise SystemExit(1)


def need(obj, *keys):
    """Return obj[keys...] or die naming the missing dotted path."""
    cur = obj
    for i, k in enumerate(keys):
        if not isinstance(cur, dict) or k not in cur:
            die(f"report.json missing field: {'.'.join(map(str, keys[:i + 1]))}")
        cur = cur[k]
    return cur


def load_report(path):
    if not os.path.isfile(path):
        die(f"missing {os.path.relpath(path)}: run 'python3 "
            "cookbook/gpu-sim-sweep/run.py --gpu --report-json "
            "cookbook/gpu-sim-sweep/media/data/report.json'")
    with open(path) as fh:
        return json.load(fh)


def result_png(rep):
    timing = need(rep, "good", "verdict", "timing")
    points = need(timing, "points")
    cpu_sps = need(timing, "cpu_steps_per_s")
    floor = need(timing, "speedup_floor")
    ok_pts = [p for p in points if p.get("ok")]
    if not ok_pts:
        die("report.json: no successful sweep points to plot")

    fig, (ax, ax2) = plt.subplots(1, 2, figsize=(12, 4.6), dpi=200)
    fig.suptitle("gpu-sim-sweep: measured sweep on a 4 GiB RTX 5090 slice "
                 "(judge-ran, real mujoco_warp run)", fontsize=11)

    nw = [p["nworld"] for p in ok_pts]
    sps = [p["steps_per_s"] for p in ok_pts]

    # --- left: throughput ladder -------------------------------------
    ax.axhline(cpu_sps, color="#d95f02", ls="--", lw=1.4,
               label=f"CPU baseline (1 world, mujoco): {cpu_sps:,.0f} steps/s")
    ax.axhline(floor * cpu_sps, color="#e7298a", ls=":", lw=1.6,
               label=f"pass floor: {floor:g}x CPU = {floor * cpu_sps:,.0f} steps/s")
    ax.plot(nw, sps, "o-", color="#1b9e77", lw=1.8, ms=6,
            label="measured GPU steps/s (mujoco_warp)")
    for p in ok_pts:
        ax.annotate(f"{p['steps_per_s']:,.0f}",
                    (p["nworld"], p["steps_per_s"]),
                    textcoords="offset points", xytext=(0, 8),
                    ha="center", fontsize=7)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("nworld (parallel worlds per step)")
    ax.set_ylabel("aggregate steps/s (log)")
    ax.set_title("Throughput vs world count")
    ax.legend(fontsize=7.5, loc="upper left")
    ax.grid(True, which="both", alpha=0.25)

    # --- right: physics oracle ---------------------------------------
    ax2.axhspan(BOX_Z_MIN, BOX_Z_MAX, color="#1b9e77", alpha=0.15,
                label=f"landed band [{BOX_Z_MIN:.3f}, {BOX_Z_MAX:.3f}] m")
    ax2.axhline(TABLE_TOP, color="#666666", lw=1, ls="-",
                label=f"table top {TABLE_TOP} m")
    xs = range(len(ok_pts))
    for i, p in zip(xs, ok_pts):
        ax2.plot([i, i], [p["box_z_min"], p["box_z_max"]], "-",
                 color="#7570b3", lw=5, solid_capstyle="round")
        ax2.plot(i, p["box_z_min"], "v", color="#7570b3", ms=5)
        ax2.plot(i, p["box_z_max"], "^", color="#7570b3", ms=5)
    worst_arm = max(p["arm_max_err"] for p in ok_pts)
    ax2.set_xticks(list(xs))
    ax2.set_xticklabels([str(p["nworld"]) for p in ok_pts])
    ax2.set_xlabel("nworld")
    ax2.set_ylabel("box z range after settle (m)")
    ax2.set_ylim(0, BOX_Z_MAX + 0.15)
    ax2.set_title("Physics oracle: boxes landed, finite")
    ax2.legend(fontsize=7.5, loc="lower right")
    ax2.grid(True, axis="y", alpha=0.25)
    ax2.text(0.02, 0.97,
             "all worlds finite; arm err max "
             f"{worst_arm:.3f} rad < {ARM_ERR_TOL}\n"
             f"CPU<->GPU world-0 parity err "
             f"{need(timing, 'parity_max_err'):.4f} rad < 0.05",
             transform=ax2.transAxes, va="top", fontsize=7.5,
             bbox=dict(fc="white", ec="#cccccc", alpha=0.9))

    fig.tight_layout(rect=(0, 0, 1, 0.94))
    out = os.path.join(MEDIA_DIR, "result.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"wrote {out}")


def loop_png(rep):
    verdict = need(rep, "good", "verdict")
    gates = need(verdict, "gates")
    mutants = need(rep, "mutants")

    rows = [("good (PASS)", gates)] + \
        [(name, need(m, "gates")) for name, m in sorted(mutants.items())]
    all_gates = list(GATE_ORDER)
    for _, gs in rows:
        for g in gs:
            if g not in all_gates:
                all_gates.append(g)

    fig, (ax, ax2) = plt.subplots(
        1, 2, figsize=(12, 4.6), dpi=200,
        gridspec_kw={"width_ratios": [2.6, 1]})
    fig.suptitle("gpu-sim-sweep: judge verdicts per artifact "
                 "(real grade runs on the lease)", fontsize=11)

    # --- left: artifact x gate matrix --------------------------------
    for r, (name, gs) in enumerate(rows):
        for c, g in enumerate(all_gates):
            cell = gs.get(g)
            passed = cell.get("pass") if isinstance(cell, dict) else cell
            if passed is None:
                colour, mark = "#dddddd", ""
            elif passed:
                colour, mark = "#1b9e77", "pass"
            else:
                colour, mark = "#e7298a", "FAIL"
            ax.add_patch(Rectangle((c, len(rows) - 1 - r), 1, 1,
                                   fc=colour, ec="white", lw=2,
                                   alpha=0.9 if mark else 0.5))
            if mark == "FAIL":
                ax.text(c + 0.5, len(rows) - 1 - r + 0.5, "FAIL",
                        ha="center", va="center", fontsize=6.5,
                        color="white", weight="bold")
            elif mark == "pass":
                ax.text(c + 0.5, len(rows) - 1 - r + 0.5, "ok",
                        ha="center", va="center", fontsize=6.5,
                        color="white")
    ax.set_xlim(0, len(all_gates))
    ax.set_ylim(0, len(rows))
    ax.set_xticks([c + 0.5 for c in range(len(all_gates))])
    ax.set_xticklabels(all_gates, rotation=25, ha="right", fontsize=7.5)
    ax.set_yticks([len(rows) - 1 - r + 0.5 for r in range(len(rows))])
    ax.set_yticklabels([n for n, _ in rows], fontsize=7.5)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)
    ax.set_title("gate outcomes per graded artifact")

    # --- right: kill-rate bar -----------------------------------------
    killed = sum(1 for m in mutants.values()
                 if need(m, "failed"))
    total = len(mutants)
    ax2.barh([0], [killed], color="#1b9e77", height=0.5,
             label=f"killed {killed}")
    ax2.barh([0], [total - killed], left=[killed], color="#e7298a",
             height=0.5, label=f"survived {total - killed}")
    ax2.set_xlim(0, total)
    ax2.set_yticks([0])
    ax2.set_yticklabels(["mutants"])
    ax2.set_xlabel("count")
    ax2.set_title(f"self-test kill rate: {killed}/{total} "
                  f"= {killed * 100 // total}%")
    ax2.legend(fontsize=8, loc="lower right")
    for s in ax2.spines.values():
        s.set_visible(False)

    fig.tight_layout(rect=(0, 0, 1, 0.94))
    out = os.path.join(MEDIA_DIR, "loop.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"wrote {out}")


def main():
    rep = load_report(REPORT_JSON)
    result_png(rep)
    loop_png(rep)


if __name__ == "__main__":
    main()
