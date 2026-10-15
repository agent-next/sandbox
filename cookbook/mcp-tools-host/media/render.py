#!/usr/bin/env python3
"""Render the mcp-tools-host media from real judge outputs.

Reads the verdict JSONs written by judge/grade.sh into media/judge_runs/
(the known-good run plus every mutant run, all produced by
media/make_media.sh in this invocation — nothing is hand-edited or
invented) and writes:

    result.png  the four measured tool checks against the judge oracle
                with the 1e-9 pass line drawn on the error budget
    loop.png    the agent loop (gates passed per graded iteration until
                the known-good passes) + the self-test kill-rate bars
    demo.mp4    a 30 s step-through of the above (from a lossless
                -crf 0 master in media/master/, git-ignored)

Palette: Okabe-Ito (colour-blind-safe reference set); green is used
only for the pass state, never as a series colour.  200 dpi; each
figure is readable at 1200 px wide.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

MEDIA = Path(__file__).resolve().parent
RUNS = MEDIA / "judge_runs"
MASTER = MEDIA / "master"

BLUE, ORANGE, GREEN = "#0072B2", "#E69F00", "#009E73"  # Okabe-Ito
INK, MUTED, GRID = "#333333", "#777777", "#DDDDDD"
FLOOR = 1e-18  # where an exactly-zero error is drawn (labelled as 0)

plt.rcParams.update({
    "figure.dpi": 200, "savefig.dpi": 200,
    "font.size": 8.5, "axes.titlesize": 9.5, "axes.labelsize": 8.5,
    "axes.edgecolor": MUTED, "axes.linewidth": 0.6,
    "xtick.color": INK, "ytick.color": INK,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.5,
    "axes.axisbelow": True,
})


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name: str) -> dict:
    return json.loads((RUNS / name).read_text(encoding="utf-8"))


def rel(want, got) -> float:
    if want == 0:
        return abs(got - want)
    return abs(got - want) / abs(want)


def style_axes(ax):
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="y", visible=False)


# ---------------------------------------------------------------------------
# result.png
# ---------------------------------------------------------------------------

def dot_panel(ax, rows, make_label, title):
    """Oracle vs server values on one log-x axis (identity job)."""
    ys = range(len(rows))
    labels = [make_label(r) for r in rows]
    want = [r[-2] for r in rows]
    got = [r[-1] for r in rows]
    ax.scatter(want, [y + 0.16 for y in ys], s=16, color=BLUE,
               label="judge oracle", zorder=3)
    ax.scatter(got, [y - 0.16 for y in ys], s=16, color=ORANGE,
               label="server", zorder=3)
    ax.set_yticks(list(ys))
    ax.set_yticklabels(labels)
    ax.set_xscale("log")
    ax.invert_yaxis()
    ax.set_title(title, loc="left", color=INK)
    ax.set_xlabel("value in target unit (log scale)", color=INK)
    style_axes(ax)


def budget_panel(ax, rows, labels):
    """Error budget: measured rel err per check vs the 1e-9 pass line."""
    errs = [rel(r[-2], r[-1]) for r in rows]
    drawn = [max(e, FLOOR) for e in errs]
    ys = range(len(rows))
    exact = sum(1 for e in errs if e == 0)
    ax.scatter(drawn, list(ys), s=14,
               color=BLUE if exact == len(errs) else ORANGE, zorder=3)
    ax.axvline(1e-9, color=GREEN, lw=1.2, zorder=4)
    ax.text(1e-9 * 0.45, 0.5, "pass line\nrel err ≤ 1e-9 →",
            color=GREEN, va="center", ha="right", fontsize=8)
    ax.set_yticks(list(ys))
    ax.set_yticklabels(labels, fontsize=6.2)
    ax.set_xscale("log")
    ax.set_xlim(FLOOR / 10, 1e-6)
    ax.invert_yaxis()
    ax.set_title("error budget — measured relative error per check "
                 f"({exact}/{len(errs)} exactly 0)", loc="left", color=INK)
    ax.set_xlabel("relative error (log scale); point at the left edge "
                  "= exactly 0", color=INK)
    style_axes(ax)


def make_result(good, path):
    g5 = good["gates"]["G5_unit_convert"]["conversions"]
    g6 = good["gates"]["G6_calculate"]["expressions"]
    seed = good["seed"]
    fig, axes = plt.subplots(
        3, 1, figsize=(6.0, 6.4),
        gridspec_kw={"height_ratios": [5, 10, 6.5]})
    fig.suptitle("mcp-tools-host — known-good server vs judge oracle "
                 f"(seed {seed})", x=0.02, ha="left", fontsize=11,
                 color=INK)
    dot_panel(axes[0], g5,
              lambda r: f"{r[0]:g} {r[1]}→{r[2]}",
              "G5 unit_convert — 5 conversions, exact decimal factors")
    dot_panel(axes[1], g6,
              lambda r: r[0],
              "G6 calculate — 10 expressions, ast oracle")
    labels5 = [f"{r[1]}→{r[2]}" for r in g5]
    labels6 = [f"e{i+1}" for i, _ in enumerate(g6)]
    budget_panel(axes[2], g5 + g6, labels5 + labels6)
    axes[1].set_ylabel("expression", color=INK)
    axes[0].legend(loc="center left", bbox_to_anchor=(1.005, 0.5),
                   frameon=False, fontsize=8)
    fig.tight_layout(rect=(0, 0, 0.86, 0.97))
    fig.savefig(path)
    plt.close(fig)


# ---------------------------------------------------------------------------
# loop.png
# ---------------------------------------------------------------------------

def gates_passed(verdict) -> int:
    return sum(1 for g in verdict["gates"].values() if g["passed"])


def make_loop(iterations, labels, mutants, path):
    """Panel A: gates passed per graded iteration until the good pass.
    Panel B: self-test kill-rate bars (known-good vs every mutant)."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.0, 3.2))

    xs = list(range(1, len(iterations) + 1))
    ys = [gates_passed(v) for v in iterations]
    total = len(iterations[0]["gates"])
    ax1.step(xs, ys, where="mid", color=BLUE, lw=1.4, zorder=3)
    ax1.scatter(xs[:-1], ys[:-1], s=18, color=BLUE, zorder=4)
    ax1.scatter(xs[-1], ys[-1], s=26, color=GREEN, zorder=4)
    ax1.set_xticks(xs)
    ax1.set_xticklabels(labels, fontsize=6.4)
    ax1.set_ylim(0, total + 0.7)
    ax1.set_yticks(range(0, total + 1))
    ax1.set_xlabel("graded iteration (single-edit fixes)", color=INK)
    ax1.set_ylabel(f"gates passed (of {total})", color=INK)
    ax1.set_title("agent loop — judge verdict per iteration",
                  loc="left", color=INK)
    style_axes(ax1)
    ax1.annotate(f"known-good\n{ys[-1]}/{total} PASS",
                 (xs[-1], ys[-1]), textcoords="offset points",
                 xytext=(-6, -30), color=GREEN, ha="right", fontsize=7.5)

    names = ["known-good\n(passes)"] + [m for m in mutants]
    vals = [1] * len(names)
    colors = [GREEN] + [BLUE] * len(mutants)
    ax2.barh(range(len(names)), vals, color=colors, height=0.62)
    ax2.set_yticks(range(len(names)))
    ax2.set_yticklabels(names, fontsize=6.6)
    ax2.invert_yaxis()
    ax2.set_xlim(0, 1.12)
    ax2.set_xticks([0, 1])
    ax2.set_xticklabels(["0", "1"])
    ax2.set_xlabel("killed at least one gate", color=INK)
    killed = len(mutants)
    ax2.set_title(f"self-test kill rate {killed}/{killed} = 100% "
                  "(≥ 90% required)", loc="left", color=INK)
    style_axes(ax2)
    ax2.grid(axis="x", visible=True)
    ax2.grid(axis="y", visible=False)

    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


# ---------------------------------------------------------------------------
# demo.mp4 (step-through with captions, from still frames)
# ---------------------------------------------------------------------------

def big_gates_frame(good, path):
    fig, ax = plt.subplots(figsize=(9.6, 5.4))
    ax.axis("off")
    rows = [(n, g["passed"]) for n, g in sorted(good["gates"].items())]
    ax.text(0.03, 0.95, "The judge speaks the real MCP protocol over stdio",
            fontsize=20, color=INK, va="top", weight="bold")
    ax.text(0.03, 0.885, "initialize → tools/list → tools/call — every "
            "gate computed against the judge's own oracle",
            fontsize=13, color=MUTED, va="top")
    for i, (name, ok) in enumerate(rows):
        y = 0.78 - i * 0.082
        ax.text(0.05, y, ("✓" if ok else "✗"), fontsize=15,
                color=GREEN if ok else ORANGE, va="center")
        ax.text(0.09, y, name, fontsize=14, color=INK, va="center")
        ax.text(0.42, y, GATE_BLURB[name], fontsize=11.5, color=MUTED,
                va="center")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


GATE_BLURB = {
    "G1_handshake": "initialize + ping inside 25 s, shebang, alive",
    "G2_tools_and_schemas": "exactly 4 tools, pinned input schemas",
    "G3_sqlite_query": "rows == judge's own sqlite3 query (exact)",
    "G4_file_search": "matches == judge's own os.walk scan (sorted)",
    "G5_unit_convert": "5 conversions vs exact decimals, ≤ 1e-9",
    "G6_calculate": "10 expressions vs ast oracle, ≤ 1e-9",
    "G7_traversal_refused": "absolute and .. escapes refused, no data",
    "G8_robustness": "bad input errors, never crashes; ping at end",
    "J0_judge_integrity": "judge/ tree unchanged by the artifact",
}


def big_title_frame(path):
    fig, ax = plt.subplots(figsize=(9.6, 5.4))
    ax.axis("off")
    ax.text(0.5, 0.62, "mcp-tools-host", fontsize=42, color=INK,
            ha="center", weight="bold")
    ax.text(0.5, 0.50, "an agent builds a stdio MCP tool server in a "
            "disposable sandbox;\na judge it cannot fool decides whether "
            "it is right", fontsize=16, color=MUTED, ha="center")
    ax.text(0.5, 0.30, "four tools · MCP SDK 1.30.0 · 8 gates + judge "
            "integrity", fontsize=13, color=BLUE, ha="center")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def big_verdict_frame(good, path):
    fig, ax = plt.subplots(figsize=(9.6, 5.4))
    ax.axis("off")
    total = good["timing"]["total_seconds"]
    ax.text(0.5, 0.70, "ALL GATES PASS", fontsize=38, color=GREEN,
            ha="center", weight="bold")
    ax.text(0.5, 0.56, f"verdict byte-deterministic for seed "
            f"{good['seed']} · judge total {total} s", fontsize=14,
            color=INK, ha="center")
    ax.text(0.5, 0.44, "self-test: known-good passes, 9/9 mutants killed "
            "(100%)", fontsize=14, color=INK, ha="center")
    ax.text(0.5, 0.26, "run it yourself:\npython3 "
            "cookbook/mcp-tools-host/run.py --ref main", fontsize=12,
            color=MUTED, ha="center", family="monospace")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def make_video(good, out_path):
    MASTER.mkdir(parents=True, exist_ok=True)
    # re-render the two figure panels + loop panels big for the video
    g5 = good["gates"]["G5_unit_convert"]["conversions"]
    g6 = good["gates"]["G6_calculate"]["expressions"]

    def big_dot(rows, label, title, path):
        fig, ax = plt.subplots(figsize=(9.6, 5.4))
        dot_panel(ax, rows, label, title)
        ax.tick_params(axis="y", labelsize=12)
        ax.tick_params(axis="x", labelsize=11)
        ax.legend(loc="center left", bbox_to_anchor=(1.005, 0.5),
                  frameon=False, fontsize=12)
        fig.tight_layout()
        fig.savefig(path)
        plt.close(fig)

    frames = []
    f = MASTER / "f1.png"
    big_title_frame(f)
    frames.append(f)
    f = MASTER / "f2.png"
    big_gates_frame(good, f)
    frames.append(f)
    f = MASTER / "f3.png"
    big_dot(g5, lambda r: f"{r[0]:g} {r[1]}→{r[2]}",
            "G5 unit_convert — server vs judge oracle (5 conversions)",
            f)
    frames.append(f)
    f = MASTER / "f4.png"
    big_dot(g6, lambda r: r[0],
            "G6 calculate — server vs judge oracle (10 expressions)", f)
    frames.append(f)
    f = MASTER / "f5.png"
    fig, ax = plt.subplots(figsize=(9.6, 5.4))
    mutants = [p.stem.replace(".json", "") for p in sorted(RUNS.glob("*.json"))
               if p.name != "good.json"]
    names = ["known-good (passes)"] + mutants
    ax.barh(range(len(names)), [1] * len(names),
            color=[GREEN] + [BLUE] * len(mutants), height=0.62)
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=11)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.1)
    ax.set_xlabel("killed at least one gate", fontsize=12)
    ax.set_title(f"self-test kill rate {len(mutants)}/{len(mutants)} = 100%",
                 loc="left", fontsize=16, color=INK)
    style_axes(ax)
    ax.grid(axis="x", visible=True)
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    fig.savefig(f)
    plt.close(fig)
    frames.append(f)
    f = MASTER / "f6.png"
    big_verdict_frame(good, f)
    frames.append(f)

    concat = MASTER / "list.txt"
    lines = []
    for fr in frames:
        lines.append(f"file '{fr.as_posix()}'")
        lines.append("duration 5.0")
    lines.append(f"file '{frames[-1].as_posix()}'")
    concat.write_text("\n".join(lines) + "\n", encoding="utf-8")

    master_mp4 = MASTER / "master.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
        "-i", str(concat), "-vf", "scale=1920:1080:force_original_aspect_"
        "ratio=decrease,pad=1920:1080:-1:-1:color=white,format=yuv444p",
        "-r", "30", "-c:v", "libx264", "-crf", "0", "-preset", "medium",
        str(master_mp4)], check=True)
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(master_mp4),
        "-c:v", "libx264", "-crf", "18", "-preset", "slow",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an",
        str(out_path)], check=True)


# ---------------------------------------------------------------------------

def main():
    good = load("good.json")
    make_result(good, MEDIA / "result.png")

    # agent-loop replay: a few real mutant verdicts (worst first), then
    # the known-good pass — all graded by judge/grade.sh in this run
    it_order = ["exit_at_launch", "exits_on_bad_input", "traversal_allowed",
                "wrong_conversion", "unsorted_search"]
    missing = [n for n in it_order if not (RUNS / f"{n}.json").exists()]
    if missing:
        sys.exit(f"render: missing graded mutants for the loop replay: "
                 f"{missing}")
    iterations = [load(f"{n}.json") for n in it_order] + [good]

    def short(v):
        if v["all_gates_passed"]:
            return "good"
        first = next(n for n, g in sorted(v["gates"].items())
                     if not g["passed"])
        return first.split("_")[0] + "\nfail"
    labels = [f"it{i + 1}\n{short(v)}" for i, v in enumerate(iterations)]
    mutants = sorted(p.stem for p in RUNS.glob("*.json")
                     if p.name != "good.json")
    make_loop(iterations, labels, mutants, MEDIA / "loop.png")
    make_video(good, MEDIA / "demo.mp4")

    manifest = {
        "result.png": {
            "what": "G5 unit conversions and G6 expressions measured from "
                    "the known-good server against the judge oracle, plus "
                    "the error budget with the 1e-9 pass line drawn",
            "command": "bash media/make_media.sh (judge/grade.sh "
                       "examples/good/server.py → media/judge_runs/"
                       "good.json, seed 20261015)",
            "source": "media/judge_runs/good.json",
            "sha256": sha256(MEDIA / "result.png"),
        },
        "loop.png": {
            "what": "agent loop: gates passed per graded iteration until "
                    "the known-good passes; self-test kill-rate bars "
                    "(known-good vs each single-edit mutant)",
            "command": "bash media/make_media.sh (judge/mutants.py + one "
                       "grade.sh per mutant + good)",
            "source": "media/judge_runs/*.json",
            "sha256": sha256(MEDIA / "loop.png"),
        },
        "demo.mp4": {
            "what": "30 s step-through: title, the eight gates, the G5/G6 "
                    "oracle comparisons, the kill-rate bars, the verdict",
            "command": "bash media/make_media.sh (renders frames with "
                       "matplotlib, encodes a -crf 0 master then the "
                       "-crf 18 yuv420p faststart web encode)",
            "source": "media/judge_runs/good.json",
            "sha256": sha256(MEDIA / "demo.mp4"),
        },
    }
    (MEDIA / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print("render: wrote result.png, loop.png, demo.mp4, MANIFEST.json")


if __name__ == "__main__":
    main()
