#!/usr/bin/env python3
"""Render media/demo.mp4 from media/data/gpu-run.log + report.json.

1920x1080, 30 fps, libx264 CRF 18, ~30-45 s.

Scene 1 replays the lease lifecycle — create -> exec -> verdict ->
destroy/verified — as a terminal that reveals the real lines of
data/gpu-run.log verbatim. Scenes 2-3 show result.png then loop.png
(built by make_figures.py from data/report.json), each captioned with
numbers read from data/report.json. No number on screen is invented:
terminal text is log output; captions come from the report.

Any missing data field or required log line exits non-zero naming it.
"""

import itertools
import json
import os
import shutil
import subprocess
import sys
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

MEDIA_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(MEDIA_DIR, "data")
RUN_LOG = os.path.join(DATA_DIR, "gpu-run.log")
REPORT_JSON = os.path.join(DATA_DIR, "report.json")
RESULT_PNG = os.path.join(MEDIA_DIR, "result.png")
LOOP_PNG = os.path.join(MEDIA_DIR, "loop.png")
FRAMES_DIR = os.path.join(MEDIA_DIR, ".frames")
OUT_MP4 = os.path.join(MEDIA_DIR, "demo.mp4")

FPS = 30
W, H = 1920, 1080
HOLD_FINAL_TERMINAL = 75          # frames to linger on the finished log
SLIDE_SECONDS = 7
TITLE_SECONDS = 2

# Markers that must be present verbatim in the run log for the video to
# truthfully show the lease lifecycle.
REQUIRED_LOG_MARKERS = (
    "create GPU lease",
    "created gl-",
    "exec grading job on GPU lease",
    "gpu-kernel demo: PASS",
    "mutants:",
    "destroying gl-",
    "destroyed gl-",
    "verified absent or dead",
    "total:",
)

# terminal styling
BG = "#0d1117"
FG = "#e6edf3"
RED = "#ff7b72"
GREEN = "#56d364"
BLUE = "#79c0ff"
DIM = "#8b949e"


# longest log line that fits the 1920 px frame at fontsize 17
MAX_COLS = 110


def die(msg):
    print(f"make_video.py: {msg}", file=sys.stderr)
    raise SystemExit(1)


def need(obj, *keys):
    cur = obj
    for i, k in enumerate(keys):
        if not isinstance(cur, dict) or k not in cur:
            die(f"report.json missing field: "
                f"{'.'.join(map(str, keys[:i + 1]))}")
        cur = cur[k]
    return cur


def load_inputs():
    if not os.path.isfile(RUN_LOG):
        die(f"missing {os.path.relpath(RUN_LOG)}")
    with open(RUN_LOG) as fh:
        log_text = fh.read()
    for marker in REQUIRED_LOG_MARKERS:
        if marker not in log_text:
            die(f"gpu-run.log missing required line containing {marker!r}")
    if not os.path.isfile(REPORT_JSON):
        die("missing data/report.json: run 'python3 "
            "cookbook/gpu-kernel/run.py --gpu --report-json "
            "cookbook/gpu-kernel/media/data/report.json' on a GPU host "
            "and commit the result first")
    try:
        with open(REPORT_JSON) as fh:
            report = json.load(fh)
    except json.JSONDecodeError as exc:
        die(f"data/report.json is not valid JSON: {exc}")
    for path in (RESULT_PNG, LOOP_PNG):
        if not os.path.isfile(path):
            die(f"missing {os.path.relpath(path)}: run make_figures.py first")
    lines = []
    for line in log_text.splitlines():
        indent = " " * (len(line) - len(line.lstrip()) + 4)
        lines += textwrap.wrap(line, MAX_COLS, subsequent_indent=indent,
                               drop_whitespace=False) or [""]
    return lines, report


def line_frames(line):
    """Reveal duration (in frames) for one log line."""
    s = line.strip()
    if not s:
        return 8
    if ": FAIL (" in s:
        return 15
    if s.startswith("gate ") or s.startswith("mutants:"):
        return 25
    if line.startswith("  "):
        return 22
    return 30


def line_color(line):
    if "FAIL" in line:
        return RED
    if "PASS" in line or ": pass" in line:
        return GREEN
    if line.startswith(("create", "exec", "destroy", "total")):
        return BLUE
    return FG


def new_figure():
    return plt.figure(figsize=(W / 100, H / 100), dpi=100)


def render_terminal(lines, path):
    fig = new_figure()
    fig.patch.set_facecolor(BG)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    shown = ["$ python3 run.py --gpu --report-json media/data/report.json"] + lines
    line_h = 0.031
    top = 0.94
    for i, line in enumerate(shown):
        color = DIM if i == 0 else line_color(line)
        ax.text(0.028, top - i * line_h, line, family="monospace",
                fontsize=17, color=color, va="top", ha="left")
    ax.text(0.028, top - len(shown) * line_h, "\u2588",
            family="monospace", fontsize=17, color=FG, va="top", ha="left")
    fig.savefig(path)
    plt.close(fig)


def render_title(path):
    fig = new_figure()
    fig.patch.set_facecolor(BG)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.axis("off")
    ax.text(0.5, 0.56, "gpu-kernel demo", family="monospace", fontsize=42,
            color=FG, ha="center")
    ax.text(0.5, 0.44, "one 1 GiB GPU lease: create, grade, verdict, destroy",
            family="monospace", fontsize=20, color=DIM, ha="center")
    fig.savefig(path)
    plt.close(fig)


def render_slide(png_path, heading, caption, path):
    img = plt.imread(png_path)
    fig = new_figure()
    fig.patch.set_facecolor(BG)
    ax = fig.add_axes((0.03, 0.10, 0.94, 0.80))
    ax.imshow(img)
    ax.axis("off")
    fig.text(0.5, 0.945, heading, family="monospace", fontsize=22,
             color=FG, ha="center")
    fig.text(0.5, 0.035, caption, family="monospace", fontsize=16,
             color=BLUE, ha="center")
    fig.savefig(path)
    plt.close(fig)


class FrameWriter:
    def __init__(self, frames_dir):
        if os.path.isdir(frames_dir):
            shutil.rmtree(frames_dir)
        os.makedirs(frames_dir)
        self.frames_dir = frames_dir
        self.count = 0

    def emit(self, unique_png, n_frames):
        """Repeat one rendered frame for n_frames via hardlinks."""
        for _ in range(n_frames):
            dst = os.path.join(self.frames_dir, f"f{self.count:05d}.png")
            try:
                os.link(unique_png, dst)
            except OSError:
                shutil.copyfile(unique_png, dst)
            self.count += 1


def main():
    if not shutil.which("ffmpeg"):
        die("ffmpeg not found on PATH")
    if not shutil.which("ffprobe"):
        die("ffprobe not found on PATH")
    log_lines, report = load_inputs()

    kernel_ms = need(report, "good", "verdict", "timing", "kernel_ms")
    eager_ms = need(report, "good", "verdict", "timing", "eager_ms")
    speedup = need(report, "good", "verdict", "timing", "speedup")
    mutants = need(report, "mutants")
    killed = sum(1 for m in mutants.values() if m.get("failed"))
    gb_per_s = 2 * 4096 * 4096 * 4 / (kernel_ms / 1e3) / 1e9

    fw = FrameWriter(FRAMES_DIR)
    # every unique frame gets its own file: emitted frames are hardlinks to
    # it, so re-rendering into the same path would corrupt earlier frames
    uid = itertools.count()

    def unique():
        return os.path.join(FRAMES_DIR, f"_u{next(uid):03d}.png")

    tmp = unique()
    render_title(tmp)
    fw.emit(tmp, TITLE_SECONDS * FPS)

    for i in range(len(log_lines)):
        tmp = unique()
        render_terminal(log_lines[: i + 1], tmp)
        fw.emit(tmp, line_frames(log_lines[i]))
    fw.emit(tmp, HOLD_FINAL_TERMINAL)

    tmp = unique()
    render_slide(RESULT_PNG, "result.png",
                 f"kernel {kernel_ms:.3f} ms vs eager {eager_ms:.3f} ms "
                 f"(speedup x{speedup:.2f})  |  {gb_per_s:.1f} GB/s "
                 "effective (cache-resident, not a DRAM figure)", tmp)
    fw.emit(tmp, SLIDE_SECONDS * FPS)

    tmp = unique()
    render_slide(LOOP_PNG, "loop.png",
                 f"{killed}/{len(mutants)} mutants killed "
                 "(red cell = failing gate)", tmp)
    fw.emit(tmp, SLIDE_SECONDS * FPS)

    for name in os.listdir(FRAMES_DIR):
        if name.startswith("_u"):
            os.unlink(os.path.join(FRAMES_DIR, name))
    seconds = fw.count / FPS
    if not 30 <= seconds <= 45:
        die(f"internal: planned duration {seconds:.1f} s outside 30-45 s")

    proc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
         "-i", os.path.join(FRAMES_DIR, "f%05d.png"),
         "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", OUT_MP4],
        capture_output=True, text=True)
    if proc.returncode != 0:
        die(f"ffmpeg failed: {proc.stderr.strip()[-400:]}")

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", OUT_MP4], capture_output=True, text=True)
    try:
        duration = float(probe.stdout.strip())
    except ValueError:
        die(f"could not probe demo.mp4 duration: {probe.stdout!r}")
    if not 30 <= duration <= 45:
        die(f"demo.mp4 duration {duration:.1f} s outside 30-45 s")

    shutil.rmtree(FRAMES_DIR)
    print(f"wrote {OUT_MP4} ({fw.count} frames, {duration:.1f} s, "
          f"{W}x{H} @{FPS} fps, libx264 crf 18)")


if __name__ == "__main__":
    main()
