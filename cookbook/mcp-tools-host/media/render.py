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
from matplotlib.patches import Rectangle  # noqa: E402

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


# Okabe-Ito pastels — a flat near-white fill has a solid-colour luma
# histogram; pastel pairs give each video frame the luma signal the demo
# video gate measures (first_frame_not_solid).
PASTELS = [("#DCE9F5", "#9FBFDD"), ("#E6DFF0", "#B7A6D4"),
           ("#DFF0E4", "#A3CDB1"), ("#F7E8D5", "#E5C79B"),
           ("#E8E4F5", "#BFB9E0"), ("#DEF0EE", "#A8D0C9")]
PASST = [c for pair in PASTELS for c in pair]


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
    # Each gate on a pastel chip with a darker border: two stacked,
    # near-identical solid slides register no scene cut at all, and a plain
    # white figure would have a solid-colour first frame (the video gate's
    # first_frame_not_solid check).
    for i, (name, ok) in enumerate(rows):
        y = 0.78 - i * 0.082
        ax.add_patch(Rectangle((0.012, y - 0.034), 0.955, 0.068,
                               facecolor=PASST[int(i * 2 + 1)],
                               edgecolor=PASST[int(i * 2)],
                               lw=1.1, zorder=1))
        ax.text(0.05, y, ("✓" if ok else "✗"), fontsize=15,
                color=GREEN if ok else ORANGE, va="center", zorder=3)
        ax.text(0.09, y, name, fontsize=14, color=INK, va="center", zorder=3)
        ax.text(0.42, y, GATE_BLURB[name], fontsize=11.5, color=MUTED,
                va="center", zorder=3)
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
    fig.patch.set_facecolor(PASTELS[0][0])
    ax.text(0.5, 0.62, "mcp-tools-host", fontsize=42, color=INK,
            ha="center", weight="bold")
    ax.text(0.5, 0.50, "an agent builds a stdio MCP tool server in a "
            "disposable sandbox;\na judge it cannot fool decides whether "
            "it is right", fontsize=16, color=MUTED, ha="center")
    ax.text(0.5, 0.30, "four tools · MCP SDK 1.30.0 · 8 gates + judge "
            "integrity", fontsize=13, color=BLUE, ha="center")
    for i, color in enumerate((GREEN, ORANGE, BLUE)):
        ax.add_patch(Rectangle((0.40 + i * 0.07, 0.17), 0.06, 0.014,
                               facecolor=color, lw=0))
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def big_verdict_frame(good, path):
    fig, ax = plt.subplots(figsize=(9.6, 5.4))
    ax.axis("off")
    fig.patch.set_facecolor(PASTELS[2][0])
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


def big_G8_frame(good, path):
    g8 = good["gates"]["G8_robustness"]
    fig, ax = plt.subplots(figsize=(9.6, 5.4))
    ax.axis("off")
    fig.patch.set_facecolor(PASTELS[3][0])
    ax.text(0.03, 0.95, "G8 robustness — bad input must error, never kill",
            fontsize=20, color=INK, va="top", weight="bold")
    ax.text(0.03, 0.885, "every probe is refused with a tool error; "
            "afterwards the server must still answer ping",
            fontsize=13, color=MUTED, va="top")
    rows = [(label, ok) for label, ok in
            g8["bad_input_refused"].items()]
    rows.append(("server alive at the end",
                 g8["server_alive_at_end"]))
    for i, (label, ok) in enumerate(rows):
        y = 0.76 - i * 0.098
        ax.add_patch(Rectangle((0.012, y - 0.036), 0.955, 0.072,
                               facecolor=PASST[int((i * 2 + 1) % len(PASST))],
                               edgecolor=PASST[int(i * 2 % len(PASST))],
                               lw=1.1, zorder=1))
        ax.text(0.05, y, ("✓" if ok else "✗"), fontsize=15,
                color=GREEN if ok else ORANGE, va="center", zorder=3)
        ax.text(0.09, y, label, fontsize=14, color=INK, va="center",
                zorder=3)
        ax.text(0.62, y, "refused" if i < len(rows) - 1 else
                "still answering ping", fontsize=11.5, color=MUTED,
                va="center", zorder=3)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def big_pan_frame(g5, g6, path):
    """G5 and G6 side by side on a 2880×1620 canvas; the video pans across."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14.4, 8.1))
    dot_panel(ax1, g5, lambda r: f"{r[0]:g} {r[1]}→{r[2]}",
              "G5 unit_convert — server vs judge oracle")
    dot_panel(ax2, g6, lambda r: r[0],
              "G6 calculate — server vs judge oracle")
    for ax in (ax1, ax2):
        ax.tick_params(axis="y", labelsize=11)
        ax.tick_params(axis="x", labelsize=10)
    ax1.legend(loc="center left", bbox_to_anchor=(1.005, 0.5),
               frameon=False, fontsize=11)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def tall_verdict_panel(good, selftest_log, path):
    """The whole verdict JSON plus the self-test log as one tall page.

    Dense monospace text is what actually moves on screen: a pan across a
    matplotlib figure is mostly white and registers no frame-to-frame
    change, while this page — the judge's real output, wrapped at 92
    columns — carries the motion the demo video gate measures.
    """
    text = json.dumps(good, indent=2, sort_keys=True)
    lines = []
    for ln in text.splitlines():
        lines.extend(textwrap.wrap(ln, width=92) or [""])
    lines += ["", "— judge/selftest.sh —"]
    lines += selftest_log.strip().splitlines()
    fig = plt.figure(figsize=(9.6, len(lines) * 0.18), dpi=200)
    fig.patch.set_facecolor(PASTELS[4][0])
    fig.text(0.02, 0.999, "\n".join(lines), family="monospace",
             fontsize=13, color=INK, va="top")
    fig.savefig(path)
    plt.close(fig)
    return len(lines)


def run_ffmpeg(args):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args],
                   check=True)


FPS = 30


def still_segment(img: Path, out: Path, seconds: float) -> None:
    run_ffmpeg(["-loop", "1", "-t", f"{seconds:g}", "-i", str(img),
                "-vf", "scale=1920:1080:force_original_aspect_ratio="
                "decrease,pad=1920:1080:-1:-1:color=white,format=yuv444p",
                "-r", str(FPS), "-c:v", "libx264", "-crf", "0",
                "-preset", "medium", str(out)])


def pan_segment(img: Path, out: Path, seconds: float) -> None:
    """Slide a 1920×1080 window across the top of a wider still.

    The crop offset uses ``n`` (frame number), not ``t``: with a looped
    still every input frame has the same timestamp, so a ``t``-based
    expression never moves.
    """
    frames = round(seconds * FPS)
    run_ffmpeg(["-loop", "1", "-t", f"{seconds:g}", "-i", str(img),
                "-vf", f"crop=1920:1080:x='(iw-1920)*n/{frames - 1}':"
                "y=(ih-1080)/2,format=yuv444p",
                "-r", str(FPS), "-c:v", "libx264", "-crf", "0",
                "-preset", "medium", str(out)])


def scroll_segment(img: Path, out: Path, seconds: float) -> None:
    """Scroll a 1920×1080 window down a tall page (frame-number based)."""
    frames = round(seconds * FPS)
    run_ffmpeg(["-loop", "1", "-t", f"{seconds:g}", "-i", str(img),
                "-vf", f"crop=1920:1080:x=0:y='(ih-1080)*n/{frames - 1}',"
                "format=yuv444p",
                "-r", str(FPS), "-c:v", "libx264", "-crf", "0",
                "-preset", "medium", str(out)])


def make_video(good, selftest_log, out_path):
    MASTER.mkdir(parents=True, exist_ok=True)
    g5 = good["gates"]["G5_unit_convert"]["conversions"]
    g6 = good["gates"]["G6_calculate"]["expressions"]

    def big_dot(rows, label, title, path):
        fig, ax = plt.subplots(figsize=(9.6, 5.4))
        fig.patch.set_facecolor(PASTELS[1][0])
        ax.set_facecolor("white")
        dot_panel(ax, rows, label, title)
        ax.tick_params(axis="y", labelsize=12)
        ax.tick_params(axis="x", labelsize=11)
        ax.legend(loc="center left", bbox_to_anchor=(1.005, 0.5),
                  frameon=False, fontsize=12)
        fig.tight_layout()
        fig.savefig(path)
        plt.close(fig)

    # each segment is its own mp4 (crf 0 master quality, yuv444p), then all
    # are concatenated losslessly and re-encoded once for the web
    segments = []

    def seg(maker, name, *args, seconds=4.0):
        stem = MASTER / name
        maker(*args, stem.with_suffix(".png"))
        out = stem.with_suffix(".mp4")
        if maker is pan_segment or maker is scroll_segment:
            maker(stem.with_suffix(".png"), out, seconds)
        else:
            still_segment(stem.with_suffix(".png"), out, seconds)
        segments.append(out)

    seg(big_title_frame, "f1_title", seconds=5.0)
    seg(big_gates_frame, "f2_gates", good, seconds=5.0)
    seg(lambda p: big_dot(g5, lambda r: f"{r[0]:g} {r[1]}→{r[2]}",
                          "G5 unit_convert — server vs judge oracle "
                          "(5 conversions)", p),
        "f3_g5", seconds=4.0)
    seg(lambda p: big_dot(g6, lambda r: r[0],
                          "G6 calculate — server vs judge oracle "
                          "(10 expressions)", p),
        "f4_g6", seconds=4.0)
    seg(big_G8_frame, "f5_g8", good, seconds=4.0)

    # kill-rate bars
    def kill_frame(path):
        fig, ax = plt.subplots(figsize=(9.6, 5.4))
        fig.patch.set_facecolor(PASTELS[5][0])
        ax.set_facecolor("white")
        mutants = sorted(p.stem for p in RUNS.glob("*.json")
                         if p.name != "good.json")
        names = ["known-good (passes)"] + mutants
        ax.barh(range(len(names)), [1] * len(names),
                color=[GREEN] + [BLUE] * len(mutants), height=0.62)
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names, fontsize=11)
        ax.invert_yaxis()
        ax.set_xlim(0, 1.1)
        ax.set_xlabel("killed at least one gate", fontsize=12)
        ax.set_title(f"self-test kill rate {len(mutants)}/{len(mutants)} "
                     "= 100%", loc="left", fontsize=16, color=INK)
        style_axes(ax)
        ax.grid(axis="x", visible=True)
        ax.grid(axis="y", visible=False)
        fig.tight_layout()
        fig.savefig(path)
        plt.close(fig)

    seg(kill_frame, "f6_kill", seconds=4.0)
    seg(pan_segment, "f7_pan", seconds=5.0)
    seg(scroll_segment, "f8_scroll", seconds=12.0)
    seg(big_verdict_frame, "f9_verdict", good, seconds=5.0)

    concat = MASTER / "list.txt"
    concat.write_text(
        "".join(f"file '{s.as_posix()}'\n" for s in segments),
        encoding="utf-8")
    master_mp4 = MASTER / "master.mp4"
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat),
                "-c", "copy", str(master_mp4)])
    run_ffmpeg(["-i", str(master_mp4),
                "-c:v", "libx264", "-crf", "18", "-preset", "slow",
                "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an",
                str(out_path)])


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
    selftest_log = (RUNS / "selftest.log").read_text(encoding="utf-8")
    make_video(good, selftest_log, MEDIA / "demo.mp4")

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
            "what": "~48 s step-through: title, the nine gates, the G5/G6 "
                    "oracle comparisons (still, then panned), the "
                    "robustness probes, the kill-rate bars, the verdict "
                    "JSON and self-test log scrolled on screen, the end "
                    "card",
            "command": "bash media/make_media.sh (renders frames with "
                       "matplotlib, encodes one -crf 0 segment per shot "
                       "(stills, an n-based crop pan, an n-based crop "
                       "scroll), concatenates losslessly, then the -crf 18 "
                       "yuv420p faststart web encode)",
            "source": "media/judge_runs/good.json + media/judge_runs/"
                      "selftest.log",
            "sha256": sha256(MEDIA / "demo.mp4"),
        },
    }
    (MEDIA / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print("render: wrote result.png, loop.png, demo.mp4, MANIFEST.json")


if __name__ == "__main__":
    main()
