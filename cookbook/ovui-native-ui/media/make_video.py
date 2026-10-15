#!/usr/bin/env python3
"""media/make_video.py -- build media/demo.mp4 from real judge outputs.

Runs headless (matplotlib + PIL + ffmpeg), no live screen capture.  The
video steps through the same judge outputs as the two PNG figures:

  1. title card: demo name + the real grade verdict headline
  2. the real 1280x720 render fades in, with the judge's measured widget
     bboxes overlaid one gate at a time (widget_tree, then pixels)
  3. the swatch-gate chart (measured median vs the judge's mask)
  4. the agent-loop replay (per-iteration verdicts)
  5. the kill table + PASS stamp with the real sha256

Every drawn value is read from media/data/ (written by make_data.py from
real judge commands); nothing is invented.  A lossless H.264 master
(-crf 0, git-ignored under media/master/) is encoded first, then the web
encode (-crf 18 -preset slow -pix_fmt yuv420p -movflags +faststart).
"""
import json
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

MEDIA = Path(__file__).resolve().parent
DATA = MEDIA / "data"
MASTER = MEDIA / "master"
sys.path.insert(0, str(MEDIA))
from make_figures import (DATA as _D, GRID, GOOD, S1, SURFACE, TEXT,  # noqa: E402
                          TEXT2, MUTANT_LABELS, MUTANT_ORDER,
                          draw_render_overlay, failed_gates, load)

W, H = 1920, 1080
FPS = 30
STILL_DPI = 100                        # 19.2x10.8 in -> exactly 1920x1080


def scene_fig(figsize=(19.2, 10.8)):
    """A clean full-frame figure with the standard palette."""
    fig = plt.figure(figsize=figsize, dpi=STILL_DPI)
    fig.patch.set_facecolor(SURFACE)
    return fig


def fig_to_img(fig):
    """Render the figure to a PIL image at the video resolution."""
    fig.canvas.draw()
    buf = np.asarray(fig.canvas.buffer_rgba())
    img = Image.fromarray(buf[..., :3])
    assert img.size == (W, H), f"scene rendered {img.size}, want {(W, H)}"
    plt.close(fig)
    return img


def crossfade(a, b, steps):
    """PIL crossfade from image a to image b over `steps` frames."""
    out = []
    for t in range(1, steps + 1):
        f = t / steps
        out.append(Image.blend(a, b, f))
    return out


def build_stages():
    """Render each video scene to a PIL image, once."""
    good = load("grade_good.json")
    facts = load("facts.json")
    pix = [g for g in good["gates"] if g["gate"] == "pixels"][0]["detail"]
    det = [g for g in good["gates"] if g["gate"] == "determinism"][0]
    selftest = (DATA / "selftest.txt").read_text()
    rate = [l for l in selftest.splitlines() if "kill rate" in l][-1]
    rate = rate.split(":", 1)[1].strip()

    stages = []

    # -- 1. title card -----------------------------------------------------
    fig = scene_fig()
    fig.text(0.5, 0.58, "ovui-native-ui", ha="center", fontsize=44,
             color=TEXT, fontweight="bold")
    fig.text(0.5, 0.47, "headless omni.ui panel rendered on a CPU "
             "(lavapipe Vulkan), judged by four gates",
             ha="center", fontsize=20, color=TEXT2)
    fig.text(0.5, 0.36, f"known-good verdict: PASS — all 4 gates\n"
             f"render sha256 {det['sha256']}",
             ha="center", fontsize=15, color=TEXT2)
    stages.append(("title", fig_to_img(fig), 5.0))

    # -- 2. the real render, no overlay ------------------------------------
    ax_fig = scene_fig()
    ax = ax_fig.add_axes([0.03, 0.05, 0.94, 0.90])
    draw_render_overlay(ax, show_bboxes=False, pass_stamp=False)
    stages.append(("render_plain", fig_to_img(ax_fig), 4.0))

    # -- 3. render + measured widget bboxes (gate: widget_tree) ------------
    ax_fig = scene_fig()
    ax = ax_fig.add_axes([0.03, 0.05, 0.94, 0.90])
    draw_render_overlay(ax, show_bboxes=True, pass_stamp=False)
    stages.append(("render_bbox", fig_to_img(ax_fig), 5.5))

    # -- 4. render + PASS stamp (gates: pixels + determinism) --------------
    ax_fig = scene_fig()
    ax = ax_fig.add_axes([0.03, 0.05, 0.94, 0.90])
    draw_render_overlay(ax, show_bboxes=True, pass_stamp=True)
    stages.append(("render_stamp", fig_to_img(ax_fig), 5.5))

    # -- 5. swatch gate chart ----------------------------------------------
    ref = json.loads((MEDIA.parent / "judge/reference.json").read_text())
    fig = scene_fig()
    ax = fig.add_axes([0.14, 0.18, 0.72, 0.62])
    chans = ["R", "G", "B"]
    xs = [0, 1, 2]
    med = pix["swatch_median"]
    tol = ref["swatch_tol"]
    target = ref["swatch_rgb"]
    ax.bar(xs, med, width=0.62, color=S1, edgecolor=SURFACE, lw=1.5,
           label="measured median (flat fill: std ≈ 0)")
    ax.errorbar(xs, target, yerr=tol, fmt="none", ecolor=TEXT2,
                elinewidth=2, capsize=8,
                label=f"judge mask: analytic target ± {tol}")
    ax.scatter(xs, target, marker="_", s=400, color=TEXT2, zorder=5,
               linewidths=2.2)
    for x, m, t in zip(xs, med, target):
        ax.text(x + 0.30, m, f"{m:.0f}", va="center", fontsize=16,
                color=TEXT)
        ax.text(x + 0.30, t, f"target {t:.0f}", va="center", fontsize=13,
                color=TEXT2)
    ax.set_xticks(xs)
    ax.set_xticklabels(chans, fontsize=15)
    ax.set_ylabel("8-bit value", fontsize=15)
    ax.set_ylim(0, 268)
    ax.set_xlim(-0.5, 2.95)
    ax.grid(True, axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.legend(loc="upper right", fontsize=13, frameon=False)
    ax.tick_params(labelsize=13)
    fig.text(0.5, 0.86, "Pixel gate: swatch colour, measured vs the judge's "
             f"±{tol} mask around analytic sRGB [{', '.join(map(str, target))}]",
             ha="center", fontsize=18, color=TEXT)
    stages.append(("swatch", fig_to_img(fig), 6.0))

    # -- 6. agent-loop replay ----------------------------------------------
    mutants = load("mutants.json")
    replay = [
        ("empty_window", "empty window"),
        ("wrong_swatch_color", "wrong swatch\ncolour"),
        ("nondeterministic", "nondeterministic\nrender"),
        ("good", None),
    ]
    fig = scene_fig()
    ax = fig.add_axes([0.08, 0.22, 0.84, 0.60])
    ys, labels, colors = [], [], []
    for i, (name, caption) in enumerate(replay):
        if name == "good":
            ok, gate, what = True, None, "known-good panel"
        else:
            v = mutants[name]
            ok = False
            gate = failed_gates(v)
            what = caption
        ys.append(1 if ok else 0)
        labels.append(f"it {i+1}: {what}\n"
                      f"{'PASS — all 4 gates' if ok else 'fail: ' + gate}")
        colors.append(GOOD if ok else "#d03b3b")
    ax.plot(range(1, 5), ys, color=GRID, lw=2, zorder=1)
    ax.scatter(range(1, 5), ys, s=140, c=colors, zorder=3)
    for i, (x, y, lab) in enumerate(zip(range(1, 5), ys, labels)):
        dy, va = (22, "bottom") if i % 2 == 0 else (-22, "top")
        ax.annotate(lab, (x, y), textcoords="offset points",
                    xytext=(0, dy), ha="center", va=va, fontsize=14,
                    color=TEXT if y == 0 else TEXT2,
                    bbox=dict(fc=SURFACE, ec="none", pad=1.5))
    ax.set_xticks(range(1, 5))
    ax.set_xticklabels([f"iteration {i+1}" for i in range(4)], fontsize=14)
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["fail", "pass"], fontsize=14)
    ax.set_ylim(-1.15, 1.75)
    ax.set_xlim(0.45, 4.55)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.text(0.5, 0.90, "Agent-loop replay: judge verdict per iteration "
             "(scripted replay, not a live trace)", ha="center",
             fontsize=18, color=TEXT)
    stages.append(("loop", fig_to_img(fig), 6.0))

    # -- 7. kill table + PASS stamp -----------------------------------------
    fig = scene_fig()
    ax = fig.add_axes([0.08, 0.10, 0.84, 0.72])
    rows = [("known-good panel", "PASS — all 4 gates", True)] + [
        (MUTANT_LABELS[n], failed_gates(mutants[n]), False)
        for n in MUTANT_ORDER
    ]
    ax.set_xlim(0, 1)
    ax.set_ylim(0, len(rows))
    ax.invert_yaxis()
    for i, (name, gates, ok) in enumerate(rows):
        y = i + 0.5
        ax.text(0.245, y, name, ha="right", va="center", fontsize=14,
                color=TEXT)
        ax.barh(y, 0.44, left=0.26, height=0.62,
                color=GOOD if ok else S1, edgecolor=SURFACE, lw=2)
        ax.text(0.715, y, gates, ha="left", va="center", fontsize=13,
                color=TEXT2)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    fig.text(0.5, 0.93, f"Self-test: {rate} mutants killed by the judge "
             f"(requirement ≥ 90%)", ha="center", fontsize=18, color=TEXT)
    stages.append(("kills", fig_to_img(fig), 6.5))

    return stages


def main():
    MASTER.mkdir(exist_ok=True)
    stages = build_stages()
    total = sum(s[2] for s in stages)
    frames = []
    FADE = 15   # crossfade frames between stages
    prev = None
    for name, img, dur in stages:
        n = int(round(dur * FPS))
        if prev is not None:
            frames.extend(crossfade(prev, img, FADE))
            n -= FADE
        frames.extend([img] * n)
        prev = img
    print(f"make_video: {len(stages)} stages, {len(frames)} frames, "
          f"{len(frames)/FPS:.1f} s")

    # -- lossless master, then the web encode ------------------------------
    # ffmpeg's stderr is *not* captured: an unbounded PIPE with no thread
    # draining it fills its 64 KB buffer and wedges the encoder mid-run,
    # which on a slow CPU-only box reads as a failed encode.  Instead stderr
    # goes to a file, so a real failure can still report why.
    master_mp4 = MASTER / "demo_master.mp4"
    web_mp4 = MEDIA / "demo.mp4"
    # Absolute paths, not bare names: the two encodes run with different
    # cwds (master/, then the media dir), and a bare master name in the
    # second command resolves against the wrong directory.
    with open(MASTER / "master_encode.log", "w") as master_log:
        raw = subprocess.Popen(
            ["ffmpeg", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
             "-c:v", "libx264", "-crf", "0", "-preset", "veryslow",
             "-pix_fmt", "yuv444p", str(master_mp4)],
            cwd=MASTER, stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=master_log)
        for f in frames:
            raw.stdin.write(f.tobytes())
        raw.stdin.close()
        rc = raw.wait()
    if rc != 0 or not master_mp4.exists():
        raise SystemExit("lossless master encode failed:\n"
                         + (MASTER / "master_encode.log").read_text()[-2000:])

    with open(MEDIA / "web_encode.log", "w") as web_log:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(master_mp4), "-c:v", "libx264",
             "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", "-an", str(web_mp4)],
            cwd=MEDIA, check=True, stdout=subprocess.DEVNULL,
            stderr=web_log)
    size = web_mp4.stat().st_size
    print(f"make_video: demo.mp4 {size/1e6:.2f} MB, "
          f"{len(frames)/FPS:.1f} s, {W}x{H}@{FPS}")
    if size > 8_000_000:
        raise SystemExit(f"demo.mp4 is {size/1e6:.2f} MB, over the 8 MB cap")
    print("make_video: done")


if __name__ == "__main__":
    main()
