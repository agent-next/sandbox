#!/usr/bin/env python3
"""Render media/demo.mp4 (1920x1080, 30 fps, H.264) from the judge data.

    make_video.py <demo_dir> <master_dir>

Scenes: the source fixture with its burned frame counter, the two renditions
side by side, the counter decoded back out frame by frame, the caption word
error rate, and the self-test kill-rate bars. The real frames come from
decoding fixtures/source.mp4 and the pipeline's renditions; the plots come
from media/data/*.json. Nothing here is invented.

Writes a lossless crf-0 master to <master_dir> (git-ignored) and the web
encode to media/demo.mp4.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

FPS = 30
W, H = 1920, 1080
BLUE, ORANGE, GREEN, PINK, GREY = "#0072B2", "#E69F00", "#009E73", "#CC79A7", "#999999"
plt.rcParams.update({"font.size": 13, "figure.dpi": 100,
                     "axes.grid": True, "grid.alpha": 0.3, "axes.axisbelow": True})


def load(name: str) -> dict:
    return json.loads((DATA / name).read_text())


def concat_of(directory: Path) -> str:
    """The rendition as a player sees it: the segments its playlist lists."""
    playlist = (directory / "index.m3u8").read_text().splitlines()
    segs = [directory / ln.strip() for ln in playlist
            if ln.strip() and not ln.startswith("#")]
    return "concat:" + "|".join(str(s) for s in segs)


def grab(clip: str, t: float, out: Path) -> Path:
    """One frame of a clip, scaled to fit the 1920x1080 canvas.

    Seeking into a single .ts segment can land before its first keyframe, so
    renditions are handed in as their whole concatenated stream.
    """
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t}", "-i", clip,
                    "-frames:v", "1", "-vf", "scale=1280:-2", str(out)],
                   check=True)
    if not out.is_file():
        raise SystemExit(f"could not grab a frame at t={t} from {clip[:120]}")
    return out


class Renderer:
    """One canvas; each scene draws itself for a given frame."""

    def __init__(self, work: Path):
        self.work = work
        self.fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
        self.n = 0

    def save(self) -> None:
        if OFFLINE:
            self.n += 1
            return
        self.fig.savefig(self.work / f"f{self.n:05d}.png")
        self.n += 1

    def hold(self, frames: int) -> None:
        for _ in range(frames):
            self.save()

    def title(self, text: str, sub: str, frames: int) -> None:
        if FAST and (self.work / f"f{self.n + frames - 1:05d}.png").is_file():
            self.n += frames
            return
        for _ in range(frames):
            self.fig.clear()
            ax = self.fig.add_axes((0, 0, 1, 1)); ax.axis("off")
            ax.text(0.5, 0.56, text, ha="center", va="center", fontsize=30,
                    fontweight="bold")
            ax.text(0.5, 0.45, sub, ha="center", va="center", fontsize=16,
                    color="#444444")
            self.save()

    def source(self, frame_png: Path, t: float, value: int, frames: int) -> None:
        img = mpimg.imread(frame_png)
        for i in range(frames):
            self.fig.clear()
            ax = self.fig.add_axes((0.06, 0.16, 0.88, 0.66)); ax.axis("off")
            ax.imshow(img)
            ax.set_title(f"fixtures/source.mp4 — the burned counter at t = {t:.1f} s "
                         f"reads {value:05d}", fontsize=16)
            cap = self.fig.add_axes((0, 0, 1, 0.12)); cap.axis("off")
            cap.text(0.5, 0.5, "the counter is a pure function of the frame index: "
                               "drawtext %{eif:n:d:5}",
                     ha="center", va="center", fontsize=15, color="#444444")
            self.save()

    def renditions(self, left: Path, right: Path, frames: int) -> None:
        a, b = mpimg.imread(left), mpimg.imread(right)
        for _ in range(frames):
            self.fig.clear()
            for x, img, label in ((0.04, a, "360p · 640x360"), (0.52, b, "720p · 1280x720")):
                ax = self.fig.add_axes((x, 0.22, 0.44, 0.55)); ax.axis("off")
                ax.imshow(img)
                ax.set_title(label, fontsize=16)
            cap = self.fig.add_axes((0, 0, 1, 0.16)); cap.axis("off")
            cap.text(0.5, 0.5, "HLS ladder: 2 s segments on a 4 s keyframe grid, "
                               "H.264 + AAC",
                     ha="center", va="center", fontsize=16, color="#444444")
            self.save()

    def counter(self, counter: dict, frames: int) -> None:
        r360 = counter["renditions"]["360p"]
        n = len(r360["index"])
        for i in range(frames):
            upto = max(1, round(n * (i + 1) / frames))
            self.fig.clear()
            ax = self.fig.add_axes((0.09, 0.16, 0.84, 0.68))
            ax.plot([0, 480], [0, 480], color=GREY, lw=1.4, ls="--",
                    label="expected = frame index (analytic)")
            tol = counter["tolerance"]
            ax.fill_between([0, 480], [-tol, 480 - tol], [tol, 480 + tol],
                            color=GREY, alpha=0.25, lw=0, label=f"±{tol}-frame tolerance")
            for name, style in (("360p", dict(color=BLUE, marker="o")),
                                ("720p", dict(color=ORANGE, marker="s"))):
                r = counter["renditions"][name]
                ax.plot(r["index"][:upto], r["decoded"][:upto], ls="none", ms=5,
                        label=f"{name} decoded", **style)
            ax.set_xlim(0, 480); ax.set_ylim(-10, 490)
            ax.set_xlabel("frame index in the rendition")
            ax.set_ylabel("frame counter decoded from the pixels")
            ax.set_title("G5 · the judge reads the counter back out of the renditions",
                         fontsize=17)
            ax.legend(fontsize=12, loc="upper left")
            self.save()

    def captions(self, good: dict, frames: int) -> None:
        cap = good["gates"]["captions"]
        for _ in range(frames):
            self.fig.clear()
            ax = self.fig.add_axes((0.12, 0.24, 0.76, 0.5))
            bars = [("examples/good", cap["wer"], GREEN), ("limit", 0.20, PINK)]
            ax.barh([0, 1], [b[1] for b in bars], height=0.4,
                    color=[b[2] for b in bars])
            for y, (_, v, _) in zip([0, 1], bars):
                ax.text(v + 0.006, y, f"{v:.4f}", va="center", fontsize=16)
            ax.axvline(0.20, color=PINK, lw=2, ls="--")
            ax.set_yticks([0, 1], [b[0] for b in bars])
            ax.set_xlim(0, 0.26)
            ax.set_xlabel("caption word error rate vs the known transcript")
            ax.set_title(f"G8 · captions: {cap['cues']} cues, "
                         f"{cap['coverage']:.0%} coverage, "
                         f"{cap['errors']}/{cap['ref_words']} word errors", fontsize=17)
            ax.grid(axis="y", visible=False)
            self.save()

    def killrate(self, mut: dict, frames: int) -> None:
        names = ["known-good"] + [m["name"] for m in mut["mutants"]]
        vals = [1.0] + [0.0 if m["passed"] else 1.0 for m in mut["mutants"]]
        for _ in range(frames):
            self.fig.clear()
            ax = self.fig.add_axes((0.24, 0.14, 0.62, 0.7))
            ax.barh(range(len(names)), vals, height=0.6,
                    color=[GREEN] + [BLUE] * len(mut["mutants"]))
            ax.set_yticks(range(len(names)), names, fontsize=13)
            ax.invert_yaxis()
            ax.set_xlim(0, 1.05)
            ax.set_xlabel("judge verdict (1 = killed / failed, 0 = passed)")
            for i, (v, m) in enumerate(zip(vals, [None] + mut["mutants"])):
                ax.text(v + 0.02, i, "passed all gates" if i == 0
                        else f"killed by {m['failed_gate']}", va="center", fontsize=12)
            ax.set_title(f"self-test kill rate {mut['killed']}/{mut['total']} = "
                         f"{mut['kill_rate']:.0%} (requirement ≥ 90 %)", fontsize=17)
            ax.grid(axis="y", visible=False)
            self.save()

    def closing(self, good: dict, frames: int) -> None:
        g = good["gates"]
        lines = [
            f"runs: pipeline.sh exit 0 in {good['timing']['pipeline_s']:.1f} s",
            f"geometry: 360p 640x360, 720p 1280x720, h264 + aac",
            f"duration: {g['duration']['360p']['seconds']:.4f} s "
            f"(deviation {g['duration']['360p']['deviation_s']:.4f} s)",
            f"keyframes: gaps {g['keyframes']['360p']['gaps']} s",
            f"counter: {g['counter']['360p']['matched']}/"
            f"{g['counter']['360p']['samples']} samples match",
            f"poster: {g['poster']['width']}x{g['poster']['height']}, "
            f"{g['poster']['distinct_levels']}/256 luminance levels",
            f"captions: WER {g['captions']['wer']:.4f}, {g['captions']['cues']} cues",
        ]
        for _ in range(frames):
            self.fig.clear()
            ax = self.fig.add_axes((0, 0, 1, 1)); ax.axis("off")
            ax.text(0.5, 0.9, "verdict: PASSED — every gate", ha="center",
                    va="center", fontsize=28, fontweight="bold", color=GREEN)
            ax.text(0.08, 0.78, "\n".join(lines), ha="left", va="top",
                    fontsize=15, family="monospace", linespacing=1.9)
            ax.text(0.5, 0.06, "measured, seed 0, Debian sandbox, 2 vCPU",
                    ha="center", va="center", fontsize=13, color="#444444")
            self.save()


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    demo, master = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
    work = master / "frames"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    master.mkdir(parents=True, exist_ok=True)

    good, counter, mut = load("good.json"), load("counter.json"), load("mutants.json")

    # Real frames, decoded from the fixtures and the pipeline's own output.
    run = master / "run"
    if not (run / "out" / "360p" / "seg-000.ts").is_file():
        run.mkdir(parents=True, exist_ok=True)
        shutil.copy2(demo / "examples" / "good" / "pipeline.sh", run / "pipeline.sh")
        shutil.copytree(demo / "fixtures", run / "fixtures", dirs_exist_ok=True)
        subprocess.run(["bash", str(run / "pipeline.sh"), "--input",
                        str(demo / "fixtures" / "source.mp4"), "--out",
                        str(run / "out"), "--seed", "0"], check=True,
                       capture_output=True, cwd=run)
    src_frames = [grab(str(demo / "fixtures" / "source.mp4"), t,
                       master / f"src-{i}.png")
                  for i, t in enumerate((0.5, 2.0, 4.0))]
    r360 = grab(concat_of(run / "out" / "360p"), 1.0, master / "r360.png")
    r720 = grab(concat_of(run / "out" / "720p"), 1.0, master / "r720.png")

    r = Renderer(work)
    r.title("video-transcode-pipeline", "an agent builds an HLS ladder, a poster "
            "and captions — a judge it cannot fool decides", 2 * FPS)
    for i, (png, t) in enumerate(zip(src_frames, (0.5, 2.0, 4.0))):
        r.source(png, t, round(t * 24), 2 * FPS)
    r.renditions(r360, r720, 3 * FPS)
    r.counter(counter, 6 * FPS)
    r.captions(good, 4 * FPS)
    r.killrate(mut, 4 * FPS)
    r.closing(good, 5 * FPS)
    print(f"video: {r.n} frames ({r.n / FPS:.1f} s)")

    master_mp4 = master / "demo-master.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS),
                    "-i", str(work / "f%05d.png"), "-c:v", "libx264",
                    "-preset", "veryfast", "-crf", "0", "-pix_fmt", "yuv420p",
                    str(master_mp4)], check=True)
    out = HERE / "demo.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(master_mp4),
                    "-c:v", "libx264", "-crf", "18", "-preset", "slow",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                    "-an", str(out)], check=True)
    size = out.stat().st_size
    print(f"video: wrote demo.mp4 ({size / 1024:.0f} KB) and the master "
          f"{master_mp4.name} ({master_mp4.stat().st_size / 1024:.0f} KB, git-ignored)")
    if size > 8 * 1024 * 1024:
        print("video: demo.mp4 is over the 8 MB budget", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
