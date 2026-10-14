#!/usr/bin/env python3
"""Build result.png and loop.png from media/data/report.json only.

result.png
  left  : per-case max_abs_err vs the correctness tolerance (log y axis)
  right : torch eager vs Triton kernel time bars; effective bandwidth is
          computed as 2*4096*4096*4 bytes / kernel time (decimal GB/s)

loop.png
  mutant x gate matrix; a red cell names the gate that mutant failed.
  A programmatic check dies if any two text artists overlap.

Every required field is checked explicitly: a missing field exits
non-zero and names the dotted path of the missing field.
"""

import itertools
import json
import os
import re
import sys
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

MEDIA_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(MEDIA_DIR, "data")
REPORT_JSON = os.path.join(DATA_DIR, "report.json")

# Judge bound for max abs err vs torch.softmax (SPEC.md gate 3;
# judge/_grade.py allclose rtol). Spec constant, not measured data.
MAX_ABS_TOL = 1e-5
# Display floor for exact-zero errors on the log axis.
LOG_FLOOR = 1e-28

GATE_ORDER = ("structure", "device-compile", "correctness", "speed")


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
            "cookbook/gpu-kernel/run.py --gpu --report-json "
            "cookbook/gpu-kernel/media/data/report.json' on a GPU host "
            "and commit the result first")
    try:
        with open(path) as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        die(f"{os.path.relpath(path)} is not valid JSON: {exc}")


def check_no_overlap(fig, artists):
    """Die if any two text artists' bounding boxes intersect."""
    fig.canvas.draw()
    boxes = [(a.get_text(), a.get_window_extent()) for a in artists]
    for (t1, b1), (t2, b2) in itertools.combinations(boxes, 2):
        if b1.overlaps(b2):
            die(f"overlapping text in figure: {t1!r} vs {t2!r}")


def check_inside_cells(fig, pairs):
    """Die if a cell label's bounding box leaves its cell rectangle."""
    fig.canvas.draw()
    for text, rect in pairs:
        t, r = text.get_window_extent(), rect.get_window_extent()
        if t.x0 < r.x0 or t.x1 > r.x1 or t.y0 < r.y0 or t.y1 > r.y1:
            die(f"cell label {text.get_text()!r} overflows its cell")


def build_result_png(report, out_path):
    verdict = need(report, "good", "verdict")
    cases = need(report, "good", "verdict", "cases")
    timing = need(report, "good", "verdict", "timing")
    mode = need(report, "good", "verdict", "mode")
    kernel_ms = need(report, "good", "verdict", "timing", "kernel_ms")
    eager_ms = need(report, "good", "verdict", "timing", "eager_ms")
    speedup = need(report, "good", "verdict", "timing", "speedup")
    if not isinstance(cases, list) or not cases:
        die("report.json field 'good.verdict.cases' must be a non-empty list")

    labels, errs, oks = [], [], []
    for i, case in enumerate(cases):
        if not isinstance(case, dict):
            die(f"report.json field 'good.verdict.cases[{i}]' must be an object")
        for field in ("max_abs_err", "dist", "shape", "ok"):
            if field not in case:
                die(f"report.json missing field: good.verdict.cases[{i}].{field}")
        rows, cols = case["shape"]
        labels.append(f"{case['dist']}\n{rows}x{cols}")
        errs.append(float(case["max_abs_err"]))
        oks.append(bool(case["ok"]))

    # one read + one write of a 4096x4096 fp32 tensor per launch, decimal GB/s
    bytes_moved = 2 * 4096 * 4096 * 4
    gb_per_s = bytes_moved / (kernel_ms / 1e3) / 1e9

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6.5))
    fig.suptitle(f"gpu-kernel demo — fused row-wise softmax (mode {mode})",
                 fontsize=14)
    texts = []

    # left: per-case max_abs_err, log y, tolerance line
    xs = list(range(len(cases)))
    shown = [max(e, LOG_FLOOR) for e in errs]
    colors = ["#2e9e5b" if ok else "#d0392e" for ok in oks]
    ax1.vlines(xs, LOG_FLOOR, shown, color=colors, linewidth=1.2, alpha=0.7)
    ax1.scatter(xs, shown, c=colors, zorder=3, s=42)
    ax1.axhline(MAX_ABS_TOL, color="#d0392e", linestyle="--", linewidth=1.2)
    texts.append(ax1.text(len(cases) - 1, MAX_ABS_TOL * 1.4,
                          f"tolerance {MAX_ABS_TOL:.0e}",
                          color="#d0392e", ha="right", fontsize=10))
    ax1.set_yscale("log")
    ax1.set_ylim(LOG_FLOOR * 0.5, MAX_ABS_TOL * 60)
    ax1.set_xticks(xs)
    ax1.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax1.set_xlabel("case (distribution / shape)")
    ax1.set_ylabel("max abs err vs torch.softmax")
    ax1.set_title(f"Correctness — {len(cases)} cases")
    ax1.grid(True, which="major", axis="y", alpha=0.3)
    texts.append(ax1.text(0.01, 0.02,
                          f"values below {LOG_FLOOR:.0e} are exact zeros",
                          transform=ax1.transAxes, fontsize=8,
                          color="#666666", zorder=5,
                          bbox=dict(facecolor="white", edgecolor="none", pad=1.5)))

    # right: eager vs Triton timing bars
    names = ["torch eager", "triton kernel"]
    vals = [eager_ms, kernel_ms]
    bars = ax2.bar(names, vals, color=["#8c8c8c", "#2e6fb7"], width=0.55)
    for bar, v in zip(bars, vals):
        texts.append(ax2.text(bar.get_x() + bar.get_width() / 2, v * 1.03,
                              f"{v:.3f} ms", ha="center", fontsize=11))
    top = max(vals) * 1.32
    ax2.set_ylim(0, top)
    ax2.set_ylabel("median time (ms)")
    ax2.set_title("Speed — 4096x4096 fp32, median of 9 CUDA-event runs")
    ax2.grid(True, axis="y", alpha=0.3)
    texts.append(ax2.text(1, kernel_ms * 1.14,
                          f"{gb_per_s:.1f} GB/s effective\n(tensor may be cache-resident;\nnot a DRAM-bandwidth figure)",
                          ha="center", fontsize=10, color="#2e6fb7"))
    texts.append(ax2.text(0.5, 0.9, f"speedup x{speedup:.2f}",
                          transform=ax2.transAxes, ha="center",
                          fontsize=12, fontweight="bold"))

    fig.tight_layout(rect=(0, 0, 1, 0.94))
    check_no_overlap(fig, texts)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"wrote {out_path}")


def build_loop_png(report, out_path):
    mutants = need(report, "mutants")
    good_gates = need(report, "good", "verdict", "gates")
    if not isinstance(mutants, dict) or not mutants:
        die("report.json field 'mutants' must be a non-empty object")

    names = sorted(mutants)
    status, detail = {}, {}
    for name in names:
        st = need(report, "mutants", name, "gates")
        if not isinstance(st, dict):
            die(f"report.json field 'mutants.{name}.gates' must be an object")
        status[name] = st
        detail[name] = report["mutants"][name].get("detail") or {}
    gates = ([g for g in GATE_ORDER if g in good_gates]
             + sorted(g for g in good_gates if g not in GATE_ORDER))
    rows = ["known-good"] + names
    status["known-good"] = {g: good_gates[g].get("pass") for g in gates}
    detail["known-good"] = {}

    n_rows, n_cols = len(rows), len(gates)
    cell_w, cell_h = 2.6, 0.72
    fig, ax = plt.subplots(figsize=(cell_w * n_cols + 4.4,
                                    cell_h * n_rows + 1.8))
    texts, cells = [], []
    styles = {True: ("#e3f1e4", "#2e7d32", "pass"),
              False: ("#c62828", "white", "FAIL"),
              None: ("#eeeeee", "#757575", "not run")}
    for r, name in enumerate(rows):
        y = n_rows - 1 - r
        for c, gate in enumerate(gates):
            st = status[name].get(gate)
            face, fg, label = styles[st if st in (True, False) else None]
            if st is False and detail[name].get(gate):
                err = re.search(r"\b\w+(?:Error|Exception)\b", detail[name][gate])
                short = err.group(0) if err else detail[name][gate]
                label = "FAIL\n" + "\n".join(textwrap.wrap(short, 20)[:2])
            rect = ax.add_patch(Rectangle((c, y), 1, 1, facecolor=face,
                                          edgecolor="white", linewidth=2))
            texts.append(ax.text(
                c + 0.5, y + 0.5, label, ha="center", va="center",
                fontsize=9, fontweight="bold" if st is False else "normal",
                color=fg))
            cells.append((texts[-1], rect))
    ax.add_patch(Rectangle((0, n_rows - 1), n_cols, 1, fill=False,
                           edgecolor="#1565c0", linewidth=2.5))
    for c, gate in enumerate(gates):
        texts.append(ax.text(c + 0.5, n_rows + 0.18, gate,
                             ha="center", va="bottom", fontsize=11,
                             fontweight="bold"))
    for r, name in enumerate(rows):
        y = n_rows - 1 - r
        texts.append(ax.text(-0.08, y + 0.5, name,
                             ha="right", va="center", fontsize=10,
                             family="monospace",
                             fontweight="bold" if name == "known-good" else "normal"))
    killed = sum(1 for n in names if False in status[n].values())
    ax.set_xlim(-1.8, n_cols)
    ax.set_ylim(-0.1, n_rows + 0.7)
    ax.axis("off")
    ax.set_title(f"Mutant kill matrix — {killed}/{len(names)} killed "
                 "(judge stops at the first failing gate; later gates not run)",
                 fontsize=13, pad=14)

    check_inside_cells(fig, cells)
    check_no_overlap(fig, texts)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {out_path}")


def main():
    report = load_report(REPORT_JSON)
    build_result_png(report, os.path.join(MEDIA_DIR, "result.png"))
    build_loop_png(report, os.path.join(MEDIA_DIR, "loop.png"))


if __name__ == "__main__":
    main()
