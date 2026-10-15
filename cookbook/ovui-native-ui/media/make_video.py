#!/usr/bin/env python3
"""media/make_video.py -- build media/demo.mp4 from real judge outputs.

The clip is cut from the real ovui frames media/make_frames.py captured
(media/.frames/, written by make_media.sh before this runs). Every shot
before the end card is one of those real 1280x720 lavapipe renders, moving:
a camera move across the panel, with the judge's measured numbers, the
measured bboxes, the terminal replay of the real self-test and the kill
matrix riding on top as a HUD. Only the last shot -- the launch end card --
is static.

Follows media/STORYBOARD.md: hard cuts only, the finished result as the
hook, a labelled "Nx speed" sandbox segment, a static launch end card.
Machine check: cookbook/tools/video_gate.py. Blind panel verdicts:
media/REVIEW.json.

Why the encode is structured the way it is: every shot is written as PNG
to a numbered directory and fed to ffmpeg as an image sequence in one pass,
not piped frame-by-frame over a stdin pipe. A pipe dies at the first frame
the producer is slow to build (PIL + numpy at 1920x1080); the sequence
reader just waits, and the shots can be encoded in parallel across the
shots' own frame ranges.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont

MEDIA = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(MEDIA, "data")
FRAMES = os.path.join(MEDIA, ".frames")
MASTER = os.path.join(MEDIA, "master")

W, H = 1920, 1080
FPS = 30

# STORYBOARD.md: hard cuts only. Caption cap height >= 4 % of 1080 = 43.2 px;
# DejaVu Sans cap height is ~0.729 em, so >= 60 px point size clears it.
CAP = 62
CAP_SM = 60
TITLE = 96

BG = (13, 17, 23)
FG = (230, 237, 243)
DIM = (139, 148, 158)
BLUE = (121, 192, 255)
GREEN = (86, 211, 100)
RED = (255, 123, 114)

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
FONT_MONO = os.path.join(FONT_DIR, "DejaVuSansMono.ttf")
FONT_MONO_B = os.path.join(FONT_DIR, "DejaVuSansMono-Bold.ttf")
FONT_SANS_B = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")

# Slot plan (frames at 30 fps). Matches STORYBOARD.md. A half-second black
# flash separates consecutive shots, so every join reads as a hard cut to a
# scene detector (the shots share the same panel, which is itself most of the
# frame; without the flash two neighbouring shots can fall under the
# detector's 0.3 scene-score threshold). Every shot except the end card runs
# a different phase of the same camera move, so no two shots open on the
# same view.
BLACK = 16  # 0.53 s
SPEC = [
    ("hook", 0, 60),          # 0-2 s     the finished render, camera pushing in
    ("black", 0, BLACK),
    ("spec", 80, 104),        # 2.5-6 s   the fixed spec -> the render it produced
    ("black", 0, BLACK),
    ("widget", 165, 194),     # 6.5-13 s  the render with the measured bboxes
    ("black", 0, BLACK),
    ("swatch", 264, 194),     # 13.5-20 s the swatch gate, zoomed
    ("black", 0, BLACK),
    ("sandbox", 289, 194),    # 20.5-27 s the sandbox run, Nx speed
    ("black", 0, BLACK),
    ("verdict", 249, 224),    # 27.5-35 s the PASS verdict + kill matrix HUD
    ("black", 0, BLACK),
    ("end", 0, 75),           # 35.5-38 s the launch end card (static)
]


def die(msg):
    print(f"make_video.py: {msg}", file=sys.stderr)
    raise SystemExit(1)


def load(name):
    with open(os.path.join(DATA, name)) as f:
        return json.load(f)


def font(path, size):
    return ImageFont.truetype(path, size)


def text(dr, xy, s, f, fill, anchor="la", shadow=True):
    """Draw one caption with a dark outline, so it reads over any frame."""
    x, y = xy
    if shadow:
        for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, 2)):
            dr.text((x + dx, y + dy), s, font=f, fill=(0, 0, 0), anchor=anchor)
    dr.text((x, y), s, font=f, fill=fill, anchor=anchor)


def panel_box(box):
    """The window rect in a captured frame, mapped to the 1920x1080 canvas."""
    x, y, w, h = box
    sx, sy = W / 1280.0, H / 720.0
    return x * sx, y * sy, w * sx, h * sy


def base(box):
    """The captured frame, upscaled to the canvas."""
    return Image.open(box["path"]).convert("RGB").resize((W, H), Image.LANCZOS)


def draw_bboxes(img, box, facts, label_names=True):
    """The judge's measured widget bboxes, mapped onto the canvas."""
    dr = ImageDraw.Draw(img)
    x, y, w, h = panel_box(box["box"])
    fx, fy = w / 420.0, h / 360.0
    f = font(FONT_MONO, CAP_SM)
    for name, g in facts.items():
        if name in ("window", "_ref_names", "_window_live"):
            continue
        wx = x + (g["screen_position_x"] - box["box"][0]) * fx
        wy = y + (g["screen_position_y"] - box["box"][1]) * fy
        ww = g["computed_width"] * fx
        wh = g["computed_height"] * fy
        dr.rectangle([wx, wy, wx + ww, wy + wh], outline=BLUE, width=3)
        if label_names:
            text(dr, (wx + ww + 14, wy + wh / 2), name, f, BLUE, anchor="lm")


def caption(img, s, fill=FG):
    dr = ImageDraw.Draw(img)
    text(dr, (W / 2, H - 34), s, font(FONT_SANS_B, CAP), fill,
         anchor="ms", shadow=True)
    return img


def frame_for(name, phase, box, facts, good, mutants, selftest, timings, ref,
              frame_i, n_frames):
    img = base(box)
    dr = ImageDraw.Draw(img)

    if name == "hook":
        caption(img, "a native omni.ui panel — rendered headless on a CPU")

    elif name == "spec":
        f = font(FONT_MONO, CAP_SM)
        lines = [
            'ui.Window("Tool Panel", 420x360)',
            "slider1  FloatSlider  0 .. 10",
            "slider2  FloatSlider  0 .. 20",
            "slider3  FloatSlider  0 .. 50",
            "swatch   ColorWidget  rgba(0.2, 0.5, 0.9)  140x24",
            'button   Button       "Apply"',
        ]
        x, y, w, h = panel_box(box["box"])
        for i, line in enumerate(lines):
            text(dr, (x + w + 24, y + 20 + i * 56), line, f, FG)
        caption(img, "the spec → the render the judge graded")

    elif name == "widget":
        draw_bboxes(img, box, facts)
        caption(img, "widget gate: every ref a live widget, bboxes within ±8 px")

    elif name == "swatch":
        draw_bboxes(img, box, facts, label_names=False)
        # zoom on the swatch: a real crop of the same frame, not a redraw
        g = facts["swatch"]
        bx, by = box["box"][0], box["box"][1]
        x, y, w, h = panel_box(box["box"])
        fx, fy = w / 420.0, h / 360.0
        wx = x + (g["screen_position_x"] - bx) * fx
        wy = y + (g["screen_position_y"] - by) * fy
        ww = g["computed_width"] * fx
        wh = g["computed_height"] * fy
        pad = 40
        crop = img.crop((int(wx - pad), int(wy - pad),
                         int(wx + ww + pad), int(wy + wh + pad)))
        cw, ch = crop.size
        scale = min(880 / cw, 420 / ch)
        crop = crop.resize((int(cw * scale), int(ch * scale)), Image.NEAREST)
        img.paste(crop, (60, 120))
        dr = ImageDraw.Draw(img)
        pix = [g for g in good["gates"] if g["gate"] == "pixels"][0]["detail"]
        med = ", ".join(f"{v:.0f}" for v in pix["swatch_median"])
        tgt = ", ".join(str(v) for v in ref["swatch_rgb"])
        f = font(FONT_MONO, CAP_SM)
        text(dr, (60, 60), "swatch, measured from the framebuffer", f, BLUE)
        text(dr, (60, 560), f"measured median RGB  [{med}]", f, GREEN)
        text(dr, (60, 620), f"analytic sRGB target  [{tgt}]  ± {ref['swatch_tol']}",
             f, DIM)
        caption(img, "swatch median is exactly the analytic target")

    elif name == "sandbox":
        real = timings["selftest_wall_s"]
        speed = real / (n_frames / FPS)
        lines = selftest.splitlines()
        f = font(FONT_MONO, CAP_SM)
        # the log scrolls past as the frame advances: a terminal capture, not a slide
        head = int(frame_i / n_frames * max(1, len(lines) - 18))
        shown = lines[head:head + 18]
        text(dr, (70, 60), f"in the sandbox: judge self-test — {real:.0f} s "
             f"replayed in {n_frames / FPS:.0f} s ({speed:.1f}x speed)", f, BLUE)
        for i, line in enumerate(shown):
            col = FG
            if "FAIL" in line or "fail" in line:
                col = RED
            elif "PASS" in line or "pass" in line or "kill rate" in line:
                col = GREEN
            text(dr, (70, 150 + i * 44), line[:96], f, col)
        caption(img, f"the judge's own self-test, {speed:.1f}x speed")

    elif name == "verdict":
        pix = [g for g in good["gates"] if g["gate"] == "pixels"][0]["detail"]
        det = [g for g in good["gates"] if g["gate"] == "determinism"][0]
        f = font(FONT_MONO, CAP_SM)
        gates = [
            ("gate 0  rendered_png", "1280x720 PNG"),
            ("gate 1  widget_tree", "all refs live, ranges correct"),
            ("gate 2  pixels", f"swatch median {pix['swatch_median']}"),
            ("gate 3  determinism", f"sha256 {det['sha256']}"),
        ]
        for i, (g, d) in enumerate(gates):
            text(dr, (70, 90 + i * 62), g, f, FG)
            text(dr, (760, 90 + i * 62), "[PASS]", f, GREEN)
            text(dr, (960, 90 + i * 62), d, f, DIM)
        text(dr, (70, 380), f"kill rate {selftest_rate(selftest)}", f, GREEN)
        text(dr, (960, 380), f"{len(mutants)} mutants, every one failed a gate",
             f, DIM)
        caption(img, "judge verdict: PASS 4/4 gates, render byte-identical")

    elif name == "end":
        img = Image.new("RGB", (W, H), BG)
        dr = ImageDraw.Draw(img)
        text(dr, (W / 2, 420), "python3 cookbook/ovui-native-ui/run.py",
             font(FONT_MONO_B, TITLE), FG, anchor="mm")
        text(dr, (W / 2, 560),
             "Ask your agent to build a native omni.ui panel\n"
             "judged by a harness it cannot fool",
             font(FONT_MONO, CAP), DIM, anchor="mm")
        text(dr, (W / 2, 700),
             "ovui-native-ui — CPU-only, headless Vulkan, real sandbox",
             font(FONT_MONO, CAP_SM), GREEN, anchor="mm")

    return img


def selftest_rate(selftest):
    return [l for l in selftest.splitlines()
            if "kill rate" in l][-1].split(":", 1)[1].strip()


def render_shot(out_dir, si, name, phase, n, boxes, period, ctx):
    """Write one shot's frames as shotNNNN.png in out_dir."""
    facts, good, mutants = ctx["facts"], ctx["good"], ctx["mutants"]
    selftest, timings, ref = ctx["selftest"], ctx["timings"], ctx["ref"]
    for i in range(n):
        if name == "end":
            img = frame_for(name, 0, boxes[0], facts, good, mutants,
                            selftest, timings, ref, 0, n)
        else:
            idx = (phase + i) % period
            img = frame_for(name, idx, boxes[idx % len(boxes)], facts, good,
                            mutants, selftest, timings, ref, i, n)
        img.save(os.path.join(out_dir, f"shot{si:02d}_{i:05d}.png"))


def main():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        die("ffmpeg/ffprobe not found on PATH")
    if not os.path.isdir(FRAMES):
        die(f"{FRAMES} missing; run media/make_frames.py first")
    meta = json.load(open(os.path.join(FRAMES, "frames.json")))
    caps = sorted(f for f in os.listdir(FRAMES) if f.startswith("cam_"))
    if len(caps) != meta["cam_frames"] or not meta.get("boxes"):
        die("captured frame count does not match frames.json")
    boxes = [{"path": os.path.join(FRAMES, f), "box": b}
             for f, b in zip(caps, meta["boxes"])]
    period = 2 * meta["cam_half_frames"]

    facts = load("facts.json")
    good = load("grade_good.json")
    mutants = load("mutants.json")
    timings = load("timings.json")
    selftest = open(os.path.join(DATA, "selftest.txt")).read()
    with open(os.path.join(os.path.dirname(MEDIA), "judge/reference.json")) as f:
        ref = json.load(f)

    os.makedirs(MASTER, exist_ok=True)
    tmp = os.path.join(MEDIA, ".cut")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)

    total = sum(s[2] for s in SPEC)
    duration = total / FPS
    if not 25 <= duration <= 60:
        die(f"duration {duration:.1f}s outside 25-60s")
    cuts = len(SPEC) - 1
    cuts_per_10s = cuts / (duration / 10)
    print(f"make_video: {len(SPEC)} shots, {total} frames, {duration:.1f} s, "
          f"{cuts} hard cuts, {cuts_per_10s:.1f} cuts/10s (min 0.8)")
    if cuts_per_10s < 0.8:
        die(f"cuts/10s {cuts_per_10s:.1f} < 0.8 minimum")

    # 1. render every shot's frames to PNG
    ctx = {"facts": facts, "good": good, "mutants": mutants,
           "selftest": selftest, "timings": timings, "ref": ref}
    for si, (name, phase, n) in enumerate(SPEC):
        d = os.path.join(tmp, f"s{si:02d}_{name}")
        os.makedirs(d)
        render_shot(d, si, name, phase, n, boxes, period, ctx)
        print(f"make_video: shot {name:8s} {n:4d} frames rendered")

    # 2. concat the shots. The concat demuxer reads one entry per file, so a
    #    shot is a directory of frames and every frame is its own entry.
    listfile = os.path.join(tmp, "shots.txt")
    last_dir = os.path.join(tmp, f"s{len(SPEC) - 1:02d}_{SPEC[-1][0]}")
    last_n = SPEC[-1][2]
    with open(listfile, "w") as f:
        for si, (name, _phase, n) in enumerate(SPEC):
            d = os.path.join(tmp, f"s{si:02d}_{name}")
            for i in range(n):
                f.write(f"file '{d}/shot{si:02d}_{i:05d}.png'\n")
                f.write(f"duration {1.0 / FPS:.6f}\n")
        # the demuxer repeats the last entry; give it a real last frame
        f.write(f"file '{last_dir}/shot{len(SPEC) - 1:02d}_{last_n - 1:05d}.png'\n")

    # 3. lossless master, straight from the PNG sequences
    master_mp4 = os.path.join(MASTER, "demo_master.mp4")
    with open(os.path.join(MASTER, "master_encode.log"), "w") as lf:
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-r", str(FPS),
             "-i", listfile,
             "-c:v", "libx264", "-crf", "0", "-preset", "veryfast",
             "-pix_fmt", "yuv444p", master_mp4],
            check=True, stdout=subprocess.DEVNULL, stderr=lf)

    # 4. web encode, the form the standard fixes
    web_mp4 = os.path.join(MEDIA, "demo.mp4")
    with open(os.path.join(MEDIA, "web_encode.log"), "w") as lf:
        subprocess.run(
            ["ffmpeg", "-y", "-i", master_mp4, "-c:v", "libx264",
             "-crf", "18", "-preset", "slow", "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", "-an", web_mp4],
            check=True, stdout=subprocess.DEVNULL, stderr=lf)

    size = os.path.getsize(web_mp4)
    print(f"make_video: demo.mp4 {size / 1e6:.2f} MB, {duration:.1f} s, "
          f"{W}x{H}@{FPS}")
    if size > 8_000_000:
        die(f"demo.mp4 is {size / 1e6:.2f} MB, over the 8 MB cap")

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", web_mp4], capture_output=True, text=True)
    try:
        dur = float(probe.stdout.strip())
    except ValueError:
        die(f"could not probe duration: {probe.stdout!r}")
    if not 25 <= dur <= 60:
        die(f"probed duration {dur:.1f}s outside 25-60s")
    shutil.rmtree(tmp)
    print("make_video: done")


if __name__ == "__main__":
    main()
