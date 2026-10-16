#!/usr/bin/env python3
"""make_figures.py — media/result.png + media/loop.png from real run outputs.

Every plotted number is read from the run's own verdict/receipt/selftest
files; nothing is illustrative.  The hero panel is the renderer's own
output frame (the standard forbids matplotlib 2D substitutes for 3D-sim
demos), with the judge's measured numbers and pass lines overlaid.

Usage:
  python3 media/make_figures.py RUN_DIR
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                     # noqa: E402
import numpy as np
from PIL import Image

MAGENTA = "#D55E00"

HERE = Path(__file__).resolve().parent
BLUE, ORANGE, GREEN, RED, GREY = "#0072B2", "#E69F00", "#009E73", "#D55E00", "#666666"
plt.rcParams.update({"font.size": 11, "axes.titlesize": 12,
                     "axes.titleweight": "bold", "figure.dpi": 200})


def load(run: Path):
    verdict = json.loads((run / "verdict.json").read_text())
    receipt = json.loads((run / "run-receipt.json").read_text())
    return verdict, receipt


def hero_frame(run: Path) -> Path:
    p = run / "hero.png"
    if p.exists():
        return p
    cands = sorted(run.glob("frames/arm/*.png"))
    if not cands:
        cands = sorted(run.glob("frames/*/*.png"))
    if not cands:
        raise SystemExit(f"no rendered frames under {run}")
    return cands[len(cands) // 2]


def gate_numbers(verdict: dict):
    rows = []
    for scene, entry in sorted(verdict.get("scenes", {}).items()):
        g1 = entry["gates"]["G1_silhouette"]
        g2 = entry["gates"]["G2_texture"]
        g3 = entry["gates"]["G3_temporal"]
        rows.append({
            "scene": scene,
            "iou_min": g1.get("iou_min"),
            "cov_min": g1.get("coverage_min"),
            "magenta": g2.get("magenta_max"),
            "grey": g2.get("grey_max"),
            "diff_p50": g3.get("diff_p50"),
            "frozen": g3.get("frozen"),
            "black": g3.get("black"),
        })
    return rows


def result_figure(run: Path, out: Path, throughput: dict) -> None:
    verdict, receipt = load(run)
    rows = gate_numbers(verdict)
    hero = hero_frame(run)
    img = Image.open(hero)
    fig = plt.figure(figsize=(14, 7.6), dpi=200)
    gs = fig.add_gridspec(2, 3, height_ratios=[1.15, 1.0], hspace=0.46,
                          wspace=0.30)
    ax = fig.add_subplot(gs[0, 0])
    ax.imshow(np.asarray(img))
    ax.set_title("RTX path-traced hero frame (lease output)")
    ax.axis("off")

    ax = fig.add_subplot(gs[0, 1])
    ious = [r["iou_min"] for r in rows if r["iou_min"] is not None]
    names = [r["scene"] for r in rows if r["iou_min"] is not None]
    ax.bar(names, ious, color=[GREEN if v >= 0.90 else RED for v in ious])
    ax.axhline(0.90, color=GREY, ls="--", lw=1.2)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("worst silhouette IoU vs projected bbox")
    ax.set_title("G1 silhouette IoU\n(pass >= 0.90)", fontsize=11)
    for i, v in enumerate(ious):
        ax.text(i, min(v + 0.03, 1.0), f"{v:.3f}", ha="center", fontsize=10)

    ax = fig.add_subplot(gs[0, 2])
    mag = [r["magenta"] or 0 for r in rows]
    grey = [r["grey"] or 0 for r in rows]
    x = np.arange(len(rows))
    ax.bar(x - 0.19, mag, width=0.38, color=MAGENTA,
           label="magenta (missing texture)")
    ax.bar(x + 0.19, grey, width=0.38, color=BLUE, label="default grey")
    ax.set_xticks(x)
    ax.set_xticklabels([r["scene"] for r in rows])
    ax.axhline(0.002, color=GREY, ls="--", lw=1.0)
    ax.set_ylabel("worst pixel fraction")
    ax.set_title("G2 no missing texture\n(magenta pass < 0.002)", fontsize=11)
    for i, (m, g) in enumerate(zip(mag, grey)):
        ax.text(i - 0.19, m + 0.001, f"{m:.4f}", ha="center", fontsize=8)
        ax.text(i + 0.19, g + 0.001, f"{g:.3f}", ha="center", fontsize=8)
    ax.legend(fontsize=8, loc="upper right")

    ax = fig.add_subplot(gs[1, 0])
    diffs = [r["diff_p50"] or 0 for r in rows]
    ax.bar([r["scene"] for r in rows], diffs, color=ORANGE)
    ax.axhline(1.0, color=GREY, ls="--", lw=1.2)
    ax.set_ylabel("median |luma diff| between frames")
    ax.set_title("G3 temporal consistency\n(no frozen/flash frames)", fontsize=11)

    ax = fig.add_subplot(gs[1, 1])
    renders = receipt.get("render_report", {}).get("jobs", {})
    scenes = list(renders)
    spf = [renders[s].get("s_per_frame", 0) for s in scenes]
    ax.bar(scenes, spf, color="#6C4F9E")
    ax.set_ylabel("seconds per 1920x1080 frame")
    ax.set_title(f"RTX render cost\n({throughput.get('steps', 1)} step/frame)", fontsize=11)

    ax = fig.add_subplot(gs[1, 2])
    total = receipt.get("total_seconds")
    steps = {
        "build+bundle": None,
        "lease-create": (receipt.get("create") or {}).get("seconds"),
        "upload": sum((u or {}).get("seconds", 0)
                      for u in (receipt.get("uploads") or {}).values()),
        "render": receipt.get("render_seconds"),
        "download": None,
    }
    steps = {k: v for k, v in steps.items() if v is not None}
    ax.bar(list(steps), list(steps.values()), color=BLUE)
    ax.set_ylabel("seconds")
    ax.set_title(f"run.py wall time\n(total {total:.0f} s)" if total else "run.py\nwall time", fontsize=11)
    plt.setp(ax.get_xticklabels(), rotation=18, ha="right")

    meters = receipt.get("final_meters") or {}
    billed = meters.get("billed_s")
    sub = "measured run · metered GPU seconds: "
    sub += f"{billed:.0f} s billed" if billed else "n/a"
    fig.suptitle(sub, y=0.02, fontsize=10, color=GREY)
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def loop_figure(run: Path, out: Path) -> None:
    """Self-test kill rate + per-gate worst numbers."""
    verdict, receipt = load(run)
    sf = run / "selftest.txt"
    mutants = []
    if sf.exists():
        for ln in sf.read_text().splitlines():
            ln = ln.strip()
            if ln.startswith(("missing_texture", "untextured_grey", "black_frame",
                              "frozen", "camera_off", "underexposed", "wrong_units")):
                parts = ln.split()
                mutants.append((parts[0].rstrip(":"), "KILLED" in ln))
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.4), dpi=200)
    if mutants:
        names = [m[0].replace("_", "\n") for m in mutants]
        vals = [1 if k else 0 for _, k in mutants]
        ax1.bar(names, vals, color=[GREEN if v else RED for v in vals])
        ax1.set_ylim(0, 1.35)
        ax1.set_yticks([0, 1], ["survived", "killed"])
        ax1.set_title(f"known-bad mutants killed: {sum(vals)}/{len(vals)}")
        ax1.tick_params(axis="x", labelsize=8)
    else:
        ax1.text(0.5, 0.5, "selftest not run", ha="center")
    rows = gate_numbers(verdict)
    ax2.bar([r["scene"] for r in rows],
            [r["iou_min"] or 0 for r in rows], color=BLUE)
    ax2.axhline(0.90, color=GREY, ls="--", label="pass 0.90")
    ax2.set_ylim(0, 1.1)
    ax2.set_ylabel("worst IoU")
    ax2.set_title("G1 by scene")
    ax2.legend()
    fig.savefig(out, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def main() -> int:
    run = Path(sys.argv[1]).resolve()
    steps = {"steps": 1}
    rr = json.loads((run / "run-receipt.json").read_text()).get("render_report", {})
    for job in (rr.get("jobs") or {}).values():
        if job.get("steps_per_frame"):
            steps = {"steps": job["steps_per_frame"]}
            break
    result_figure(run, HERE / "result.png", steps)
    loop_figure(run, HERE / "loop.png")
    print(f"wrote {HERE / 'result.png'} and {HERE / 'loop.png'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
