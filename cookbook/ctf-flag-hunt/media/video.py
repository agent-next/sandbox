"""The ctf-flag-hunt demo video: real judge output, animated headless.

Shot list (DEMO-STANDARD.md slots; the full storyboard lives in
media/STORYBOARD.md, written before the cut):
  0-2 s   hook: the PASS verdict fills the frame (the finished result)
  2-10 s  input -> output: the five services vs the judge gates
  10-26 s escalate: the token mixer sweeping (sped-up real trace) and a
          camera move over the PASS verdict, labelled "2x speed"
  26-35 s proof: the mutant kill matrix as a HUD overlay on the moving
          mixer, one row filling per killed mutant
  35-38 s end card: the one-command run on a static frame

Frames are rendered from the real verdict JSONs in <data_dir> (written by
make_data.py); ffmpeg assembles the lossless master and the web encode.
The master is written under media/master/ (gitignored); only the web
encode is committed.

usage: python3 -I video.py <data_dir> <frames_dir> <master.mp4> <web.mp4>
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

MIX_A = 6364136223846793005
MIX_B = 1442695040888963407
MASK64 = (1 << 64) - 1
WINDOW = 300

W, H = 1920, 1080
FPS = 30
HOOK_S, INPUT_S, ESCALATE_S, PROOF_S, ENDCARD_S = 2, 8, 16, 9, 3
TOTAL_S = HOOK_S + INPUT_S + ESCALATE_S + PROOF_S + ENDCARD_S  # 38 s

# colour-blind-safe (Okabe-Ito)
BLUE = "#0072B2"
ORANGE = "#E69F00"
GREEN = "#009E73"
RED = "#D55E00"
GREY = "#666666"
BG = "#0d1117"
FG = "#e6edf3"


def mix(seed: int, salt: int, t: int) -> int:
    x = seed & MASK64
    x = (x * MIX_A + MIX_B) & MASK64
    x ^= (salt << 13) & MASK64
    x = (x * MIX_A + MIX_B) & MASK64
    x ^= (t << 7) & MASK64
    return x


class Verdicts:
    def __init__(self, data: Path):
        v = data / "verdicts"
        self.good = json.loads((v / "03-good.json").read_text())
        self.loop = []
        for name in ("01-broken", "02-partial", "03-good"):
            self.loop.append(json.loads((v / f"{name}.json").read_text()))
        self.mutants = []
        for p in sorted(v.glob("mutant-*.json")):
            self.mutants.append((p.stem[len("mutant-"):],
                                 json.loads(p.read_text())))


def caption(ax, text: str, y: float = 0.93, size: int = 26) -> None:
    ax.text(0.5, y, text, transform=ax.transAxes, ha="center", va="top",
            fontsize=size, color=FG, weight="bold",
            bbox=dict(facecolor=BG, edgecolor="none", alpha=0.85, pad=6))


def style(ax) -> None:
    ax.set_facecolor(BG)
    for spine in ax.spines.values():
        spine.set_color(GREY)


def frame_hook(ax, V: Verdicts) -> None:
    ax.clear()
    style(ax)
    g = V.good["gates"]
    ax.text(0.5, 0.62, "JUDGE VERDICT: PASS", transform=ax.transAxes,
            ha="center", fontsize=72, color=GREEN, weight="bold")
    rows = [
        f"flags captured        {g['flags']['captured']}/{g['flags']['required']}",
        f"independent oracle    {g['oracle']['passed']}/{g['oracle']['required']}",
        f"negative control      {g['negative_control']['captured']}/{g['negative_control']['required']} flags, "
        f"{len(g['negative_control']['sweep_hits'])} sweep hits",
        f"blast radius          {'clean' if g['blast_radius']['passed'] else 'DIRTY'}",
    ]
    for i, r in enumerate(rows):
        ax.text(0.5, 0.44 - i * 0.075, r, transform=ax.transAxes, ha="center",
                fontsize=30, color=FG, family="monospace")
    ax.text(0.5, 0.04, "ctf-flag-hunt — a CTF range a judge grades",
            transform=ax.transAxes, ha="center", fontsize=24, color=GREY)


def frame_input(ax, V: Verdicts, i: int) -> None:
    ax.clear()
    style(ax)
    n = i / (INPUT_S * FPS - 1)
    services = [("notes", "off-by-one"), ("retrieve", "path traversal"),
                ("token", "weak crypto"), ("status", "config leak"),
                ("admin", "logic bug")]
    ax.text(0.5, 0.90, "Five services, five pinned vulnerabilities",
            transform=ax.transAxes, ha="center", fontsize=36, color=FG,
            weight="bold")
    shown = min(5, int(n * 6) + 1)
    for k, (name, cls) in enumerate(services[:shown]):
        y = 0.74 - k * 0.13
        ax.add_patch(plt.Rectangle((0.12, y - 0.045), 0.76, 0.09,
                                   facecolor="#161b22", edgecolor=BLUE,
                                   lw=1.5, transform=ax.transAxes))
        ax.text(0.16, y, f"{name}", transform=ax.transAxes, fontsize=26,
                color=FG, family="monospace", va="center")
        ax.text(0.55, y, f"{cls}", transform=ax.transAxes, fontsize=24,
                color=GREY, va="center")
        ax.text(0.84, y, "plants its flag", transform=ax.transAxes,
                fontsize=22, color=GREEN, va="center")
    if shown < 5:
        ax.text(0.5, 0.08, "compiling with the pinned gcc-12 …",
                transform=ax.transAxes, ha="center", fontsize=24, color=GREY)


def frame_escalate(ax, V: Verdicts, i: int, phase: int) -> None:
    """phase 0: the mixer sweeping (2x speed); phase 1: PASS verdict zoom."""
    ax.clear()
    style(ax)
    if phase == 0:
        n = i / (8 * FPS - 1)
        t0 = V.good["timing"]["c3_forge_t"]
        # sweep the mixer over a real 600 s of t, shown at 2x speed
        span = int(600 * n)
        ts = list(range(t0 - 300, t0 - 300 + max(1, span) + 1, 8))
        vals = [mix(V.good["seed"], 7919, t) for t in ts]
        ax.plot(ts, vals, color=BLUE, lw=2.0)
        ax.axvline(t0, color=ORANGE, ls="--", lw=1.6)
        ax.set_xlabel("t (unix time, s)", color=FG)
        ax.set_ylabel("mix(seed, salt, t) mod 2$^{64}$", color=FG)
        ax.set_title("The weakness the judge proves: token = f(public "
                     "seed, salt, t)", color=FG, fontsize=26)
        ax.tick_params(colors=FG)
        ax.grid(alpha=0.2)
        ax.text(0.98, 0.05, "2x speed", transform=ax.transAxes, ha="right",
                fontsize=22, color=GREY)
    else:
        n = i / (8 * FPS - 1)
        # camera move over the verdict: pan+zoom via axis limits
        x0, x1 = 0.0, 1.0
        ax.set_xlim(x0 + 0.5 * n, x1 - 0.5 * n)
        ax.set_ylim(0.25 - 0.25 * n, 0.75 + 0.25 * n)
        g = V.good["gates"]
        ax.text(0.5, 0.62, "JUDGE VERDICT: PASS", transform=ax.transAxes,
                ha="center", fontsize=72, color=GREEN, weight="bold")
        rows = [
            f"flags captured        {g['flags']['captured']}/{g['flags']['required']}",
            f"independent oracle    {g['oracle']['passed']}/{g['oracle']['required']}",
            f"negative control      {g['negative_control']['captured']}/{g['negative_control']['required']} flags, "
            f"{len(g['negative_control']['sweep_hits'])} sweep hits",
            f"blast radius          {'clean' if g['blast_radius']['passed'] else 'DIRTY'}",
        ]
        for k, r in enumerate(rows):
            ax.text(0.5, 0.44 - k * 0.075, r, transform=ax.transAxes,
                    ha="center", fontsize=30, color=FG, family="monospace")
        ax.text(0.5, 0.04, "every flag matched by sha256 against the plant",
                transform=ax.transAxes, ha="center", fontsize=24, color=GREY)


def frame_proof(ax, V: Verdicts, i: int) -> None:
    """The kill matrix HUD over the still-moving mixer (real t sweep)."""
    ax.clear()
    style(ax)
    n = i / (PROOF_S * FPS - 1)
    t0 = V.good["timing"]["c3_forge_t"]
    ts = list(range(t0 - 300, t0 + 301, 4))
    vals = [mix(V.good["seed"], 7919, t) for t in ts]
    ax.plot(ts, vals, color=BLUE, lw=1.8, alpha=0.9)
    ax.axvline(t0, color=ORANGE, ls="--", lw=1.4)
    ax.set_xlabel("t (unix time, s)", color=FG)
    ax.set_ylabel("mix(seed, salt, t) mod 2$^{64}$", color=FG)
    ax.tick_params(colors=FG)
    ax.grid(alpha=0.2)
    # HUD: the mutant kill matrix, one row filling in as its mutant is killed
    names = [m[0] for m in V.mutants]
    shown = min(len(names), int(n * (len(names) + 1)))
    for k, (name, v) in enumerate(V.mutants[:shown]):
        killed = not v.get("passed")
        y = 0.90 - k * 0.085
        colour = GREEN if killed else RED
        ax.add_patch(plt.Rectangle((0.60, y - 0.032), 0.38, 0.064,
                                   facecolor=BG, edgecolor=colour, lw=1.5,
                                   transform=ax.transAxes))
        ax.text(0.615, y, name, transform=ax.transAxes, fontsize=19,
                color=FG, family="monospace", va="center")
        ax.text(0.965, y, "killed" if killed else "SURVIVED",
                transform=ax.transAxes, fontsize=19, color=colour,
                ha="right", va="center", weight="bold")
    rate = sum(1 for _, v in V.mutants if not v.get("passed"))
    total = len(V.mutants)
    ax.text(0.79, 0.995, f"self-test kill rate {rate}/{total}",
            transform=ax.transAxes, ha="center", fontsize=24, color=FG,
            weight="bold")
    ax.text(0.79, 0.02, "judge proof: the mutant matrix, on the real trace",
            transform=ax.transAxes, ha="center", fontsize=20, color=GREY)


def frame_endcard(ax, V: Verdicts) -> None:
    ax.clear()
    style(ax)
    ax.set_xticks([])
    ax.set_yticks([])
    lines = [
        "run it in one command:",
        "python3 cookbook/ctf-flag-hunt/run.py",
        "",
        "a disposable sandbox, the pinned judge,",
        "five services, five flags — PASS.",
    ]
    for k, r in enumerate(lines):
        size = 40 if k == 1 else 28
        colour = GREEN if k == 1 else FG
        ax.text(0.5, 0.72 - k * 0.11, r, transform=ax.transAxes, ha="center",
                fontsize=size, color=colour, family="monospace")


def main() -> int:
    data, frames_dir, master, web = map(Path, sys.argv[1:5])
    V = Verdicts(data)
    frames_dir.mkdir(parents=True, exist_ok=True)

    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    ax = fig.add_subplot(111)
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

    idx = 0
    n_hook = HOOK_S * FPS
    n_input = INPUT_S * FPS
    n_esc = ESCALATE_S * FPS
    n_proof = PROOF_S * FPS
    n_end = ENDCARD_S * FPS
    for i in range(n_hook):
        frame_hook(ax, V)
        fig.savefig(frames_dir / f"f{idx:05d}.png")
        idx += 1
    for i in range(n_input):
        frame_input(ax, V, i)
        fig.savefig(frames_dir / f"f{idx:05d}.png")
        idx += 1
    for i in range(n_esc):
        frame_escalate(ax, V, i % (8 * FPS), i // (8 * FPS))
        fig.savefig(frames_dir / f"f{idx:05d}.png")
        idx += 1
    for i in range(n_proof):
        frame_proof(ax, V, i)
        fig.savefig(frames_dir / f"f{idx:05d}.png")
        idx += 1
    for i in range(n_end):
        frame_endcard(ax, V)
        fig.savefig(frames_dir / f"f{idx:05d}.png")
        idx += 1
    plt.close(fig)
    print(f"video: wrote {idx} frames to {frames_dir}")

    # lossless master (crf 0), then the web encode (crf 18, faststart)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
         "-i", str(frames_dir / "f%05d.png"),
         "-c:v", "libx264", "-preset", "veryslow", "-qp", "0",
         "-pix_fmt", "yuv420p", str(master)],
        check=True)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(master),
         "-c:v", "libx264", "-preset", "slow", "-crf", "18",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an",
         str(web)],
        check=True)
    print(f"video: master {master.stat().st_size} bytes, "
          f"web {web.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
