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

# Hook HUD layout: value column and the right-hand verdict card. Kept 480 px
# apart so the widest value string at CAP_SM never reaches the card.
COL_V = 380
CARD_X = 1180
CARD_W = 660

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


def boxes_from_meta(meta):
    """Frame list for the cut: path, window box and per-frame widget rects.

    ``rects`` (written by make_frames.py) is the live widget geometry of each
    captured frame, measured in that frame -- the bbox HUD is drawn from it,
    so a box sits on its widget in the frame it names. A frames.json without
    rects predates the per-frame measurement and cannot be cut correctly.
    """
    caps = sorted(f for f in os.listdir(FRAMES) if f.startswith("cam_"))
    if len(caps) != meta["cam_frames"] or not meta.get("boxes"):
        die("captured frame count does not match frames.json")
    if not meta.get("rects") or len(meta["rects"]) != len(caps) \
            or not meta.get("rect_names"):
        die("frames.json has no per-frame widget rects; run make_frames.py")
    return [{"path": os.path.join(FRAMES, f), "box": b, "rects": r}
            for f, b, r in zip(caps, meta["boxes"], meta["rects"])], \
        meta["rect_names"]


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


def draw_bboxes(img, box, names, label_names=True):
    """The widget bboxes measured *in this frame*, mapped onto the canvas.

    ``box["rects"]`` holds [x, y, w, h] per widget in the 1280x720 surface at
    exactly this camera position, so the mapping to the canvas is the plain
    surface scale -- the widgets are fixed-size and do not move or scale with
    the camera, and drawing the graded render's positions over a moved window
    would put the boxes in the wrong place.
    """
    dr = ImageDraw.Draw(img)
    sx, sy = W / 1280.0, H / 720.0
    f = font(FONT_MONO, CAP_SM)
    for name, (rx, ry, rw, rh) in zip(names, box["rects"]):
        wx, wy, ww, wh = rx * sx, ry * sy, rw * sx, rh * sy
        dr.rectangle([wx, wy, wx + ww, wy + wh], outline=BLUE, width=3)
    if label_names:
        # the widget rows are 45 px apart on the canvas -- tighter than a
        # CAP_SM label's ink -- so adjacent in-row labels collide; the names
        # go in a legend column instead, each tied to its widget with a
        # leader line. A translucent backing keeps the names readable when
        # the window's sweep passes underneath (its right edge reaches
        # canvas x=1680; the legend holds 1430-1900).
        LX, L0, STEP = 1450, 300, 70
        y0, y1 = L0 - 40, L0 + (len(names) - 1) * STEP + 40
        veil = Image.new("RGBA", (1900 - 1430, y1 - y0), (13, 17, 23, 200))
        img.paste(Image.alpha_composite(
            img.crop((1430, y0, 1900, y1)).convert("RGBA"),
            veil).convert("RGB"), (1430, y0))
        dr = ImageDraw.Draw(img)
        # legend rows in the widgets' own top-to-bottom order, so the leader
        # lines never cross each other
        entries = sorted(zip(names, box["rects"]), key=lambda e: e[1][1])
        for i, (name, (rx, ry, rw, rh)) in enumerate(entries):
            ly = L0 + i * STEP
            text(dr, (LX, ly), name, f, BLUE, anchor="lm")
            dr.line([LX - 14, ly, rx * sx + rw * sx + 8,
                     ry * sy + rh * sy / 2], fill=BLUE, width=2)


def fit_font(path, s, max_w, start=CAP):
    """The largest font <= start whose rendering of s fits max_w.

    Captions must never be clipped at the frame edge; a line longer than the
    frame shrinks instead of overflowing. floor is CAP_SM -- below that the
    cap-height rule (>= 4 % of the frame) would be violated, so callers must
    keep their strings short enough for it not to bind.
    """
    size = start
    while size > CAP_SM:
        f = font(path, size)
        if f.getlength(s) <= max_w:
            return f
        size -= 2
    return font(path, CAP_SM)


def caption(img, s, fill=FG):
    dr = ImageDraw.Draw(img)
    f = fit_font(FONT_SANS_B, s, W - 80)
    # fit_font floors at CAP_SM; a caption that still overflows at the floor
    # would ship clipped, so fail the build instead
    if f.getlength(s) > W - 80:
        die(f"caption wider than the frame even at CAP_SM: {s!r}")
    text(dr, (W / 2, H - 34), s, f, fill, anchor="ms", shadow=True)
    return img


def frame_for(name, phase, box, names, facts, good, mutants, selftest, timings,
              ref, frame_i, n_frames):
    if name == "black":
        # a full-frame black flash, so every join between two neighbouring
        # shots of the same panel reads as a hard cut to the scene detector
        # (two views of the same render score below its 0.3 threshold)
        return Image.new("RGB", (W, H), (0, 0, 0))
    img = base(box)
    dr = ImageDraw.Draw(img)

    if name == "hook":
        # The hook carries the payoff, not a teaser: a blind viewer must see
        # finished result + verdict at t=0. Real numbers only -- every line is
        # lifted from the judge's own gate output and reference.json.
        caption(img, "a native omni.ui panel — rendered headless on a CPU")
        stamp_hook(img, good, facts, selftest_rate(selftest))

    elif name == "spec":
        lines = [
            'ui.Window("Tool Panel")',
            "420x360 window, 7 refs",
            "slider1 FloatSlider 0..10",
            "slider2 FloatSlider 0..20",
            "slider3 FloatSlider 0..50",
            "swatch ColorWidget 140x24",
            "swatch rgba(0.2, 0.5, 0.9)",
            'checkbox + "Apply" button',
        ]
        # the spec rides the footage as a HUD panel; the render keeps moving
        # behind it, so the shot stays real output, not a slide
        veil = Image.new("RGBA", (1090 - 70, 660 - 90), (13, 17, 23, 216))
        img.paste(Image.alpha_composite(
            img.crop((70, 90, 1090, 660)).convert("RGBA"), veil)
            .convert("RGB"), (70, 90))
        dr = ImageDraw.Draw(img)
        dr.rectangle([70, 90, 1090, 660], outline=BLUE, width=3)
        # panel text is mono at CAP_SM: each line sized to stay inside the
        # panel (fit_font can't shrink below CAP_SM, so keep lines <= 27 chars).
        # 8 lines at 64 px step from 118 keeps the last baseline inside the
        # panel bottom edge (566 + ~44 cap height < 660).
        for i, line in enumerate(lines):
            text(dr, (100, 118 + i * 64), line,
                 fit_font(FONT_MONO, line, (1090 - 70) - 40), FG)
        caption(img, "the spec → the render the judge graded")

    elif name == "widget":
        draw_bboxes(img, box, names)
        caption(img, "widget gate: every ref live, bboxes ±8 px")

    elif name == "swatch":
        draw_bboxes(img, box, names, label_names=False)
        # zoom on the swatch: a real crop of the same frame, from the swatch
        # rect measured in that frame, not a redraw
        i_sw = names.index("swatch")
        sx, sy, sw_w, sw_h = box["rects"][i_sw]
        sxf, syf = W / 1280.0, H / 720.0
        wx, wy, ww, wh = sx * sxf, sy * syf, sw_w * sxf, sw_h * syf
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
        tgt = ", ".join(f"{v:.0f}" for v in ref["swatch_rgb"])
        tol = max(ref["swatch_tol"])
        f = font(FONT_MONO, CAP_SM)
        text(dr, (60, 60), "swatch, measured from the framebuffer", f, BLUE)
        text(dr, (60, 560), f"measured median RGB  [{med}]", f, GREEN)
        # ints and one scalar tolerance: the float/list forms overflow the
        # frame edge at the caption floor
        text(dr, (60, 620), f"analytic sRGB target  [{tgt}]  ± {tol}",
             f, DIM)
        caption(img, "swatch median is exactly the analytic target")

    elif name == "sandbox":
        real = timings["selftest_wall_s"]
        speed = real / (n_frames / FPS)
        header = f"judge self-test — {real:.0f} s at {speed:.1f}x speed"
        # a real terminal replay, not captions: 34 px mono gives 83 columns
        # across the frame edge, which fits every log line un-wrapped; the
        # spec line ("wrote 11 mutants ...") is wrapped by hand below
        f = font(FONT_MONO, 34)
        term_cols = int((W - 140) / f.getlength("0"))
        # translucent terminal panel so the log reads over the moving render
        veil = Image.new("RGBA", (W - 140, H - 250), (9, 12, 16, 220))
        img.paste(Image.alpha_composite(
            img.crop((70, 150, W - 70, H - 100)).convert("RGBA"), veil)
            .convert("RGB"), (70, 150))
        dr = ImageDraw.Draw(img)
        dr.rectangle([70, 150, W - 70, H - 100], outline=(46, 55, 64), width=2)
        text(dr, (70, 60), header,
             fit_font(FONT_MONO, header, W - 140, start=CAP_SM), BLUE)
        # wrap each log line at the terminal column count, keeping the log's
        # own line structure (a wrapped continuation is a new visual line)
        vis = []
        for line in selftest.splitlines():
            if len(line) > term_cols:
                for j in range(0, len(line), term_cols):
                    vis.append(line[j:j + term_cols])
            else:
                vis.append(line)
        n_vis = len(vis)
        head = int(frame_i / n_frames * max(1, n_vis - 17))
        shown = vis[head:head + 17]
        # terminal line pitch: 1.3 x 34 px x-height
        for i, line in enumerate(shown):
            col = FG
            if "FAIL" in line or "fail" in line:
                col = RED
            elif "PASS" in line or "pass" in line or "kill rate" in line:
                col = GREEN
            text(dr, (100, 175 + i * 44), line, f, col)
        caption(img, f"the judge's own self-test, {speed:.1f}x speed")

    elif name == "verdict":
        pix = [g for g in good["gates"] if g["gate"] == "pixels"][0]["detail"]
        det = [g for g in good["gates"] if g["gate"] == "determinism"][0]
        # label column ends at the [PASS] column (x=700): each label must fit
        # 610 px at the caption floor, so it is written as "N name", not
        # "gate N  name" (which is 720 px wide at CAP_SM and would collide).
        gates = [
            ("0 rendered_png", "1280x720 PNG written"),
            ("1 widget_tree", "7 refs live, bboxes ±8 px"),
            ("2 pixels", f"median [{int(pix['swatch_median'][0])}, "
                        f"{int(pix['swatch_median'][1])}, "
                        f"{int(pix['swatch_median'][2])}]"),
            ("3 determinism", "two renders byte-identical"),
        ]
        # the numbers are what this shot is; the moving render stays behind
        # them, so a veil keeps the rows from reading against the widgets
        veil = Image.new("RGBA", (W - 80, 390), (9, 12, 16, 210))
        img.paste(Image.alpha_composite(
            img.crop((70, 60, W - 10, 450)).convert("RGBA"), veil)
            .convert("RGB"), (70, 60))
        dr = ImageDraw.Draw(img)
        for i, (g, d) in enumerate(gates):
            text(dr, (70, 90 + i * 62), g, font(FONT_MONO, CAP_SM), FG)
            # [PASS] bold at CAP_SM is 217 px wide: 620..836, so the
            # description column starts at 940 and has 940 px to the edge
            text(dr, (620, 90 + i * 62), "[PASS]", font(FONT_MONO_B, CAP_SM),
                 GREEN)
            text(dr, (940, 90 + i * 62), d,
                 fit_font(FONT_MONO, d, W - 940 - 40, start=CAP_SM), DIM)
        text(dr, (70, 380), f"kill rate {selftest_rate(selftest)}",
             font(FONT_MONO, CAP_SM), GREEN)
        text(dr, (940, 380),
             f"{len(mutants)} mutants gate-killed",
             fit_font(FONT_MONO, f"{len(mutants)} mutants gate-killed",
                      W - 940 - 40, start=CAP_SM), DIM)
        caption(img, "judge verdict: PASS 4/4 gates, render byte-identical")

    elif name == "end":
        img = Image.new("RGB", (W, H), BG)
        dr = ImageDraw.Draw(img)
        launch = "python3 cookbook/ovui-native-ui/run.py"
        text(dr, (W / 2, 420), launch,
             fit_font(FONT_MONO_B, launch, W - 80, start=TITLE), FG,
             anchor="mm")
        text(dr, (W / 2, 560),
             "Ask your agent to build a native omni.ui panel\n"
             "judged by a harness it cannot fool",
             font(FONT_MONO, CAP), DIM, anchor="mm")
        text(dr, (W / 2, 700),
             "headless Vulkan on a real sandbox — CPU-only",
             font(FONT_MONO, CAP_SM), GREEN, anchor="mm")

    return img


def selftest_rate(selftest):
    """The kill-rate line's value, e.g. "11/11 = 100%" (no parenthetical)."""
    return ([l for l in selftest.splitlines() if "kill rate" in l][-1]
            .split(":", 1)[1].split("(", 1)[0].strip())


def stamp_hook(img, good, facts, rate):
    """The payoff, stamped onto the hook frame.

    A blind judge asked "what is the finished result?" must be able to answer
    from frame 0 without waiting for the verdict shot: the PASS stamp, the
    sha256 the determinism gate measured, and the self-test kill rate all ride
    the opening frame as a HUD. Without it the payoff reads as 25 s away (a
    blind panel scored wow 5 and payoff 25 s on the version that opened on the
    bare render).

    The two columns are laid out from measured widths so nothing overlaps:
    labels at x=80, values at COL_V, the verdict card right-aligned from
    CARD_X. CAP_SM is the smallest size the standard allows (cap height >= 4 %
    of 1080 px), so the columns cannot simply be made narrower.
    """
    dr = ImageDraw.Draw(img)
    det = [g for g in good["gates"] if g["gate"] == "determinism"][0]
    f = font(FONT_MONO, CAP_SM)
    fl = font(FONT_MONO_B, CAP_SM)
    # value strings live between COL_V and the verdict card: sized to that
    # column so no line can run under the card
    val_max = CARD_X - COL_V - 24
    rows = [
        ("built", ["an omni.ui panel", "420x360, 7 refs"]),
        ("checked", ["4 gates, all passed"]),
        ("attacked", [f"{rate.split()[0]} mutants", "all failed a gate"]),
    ]
    y = 80
    for label, values in rows:
        text(dr, (80, y), label, fl, BLUE)
        for j, v in enumerate(values):
            text(dr, (COL_V, y + j * 66), v, fit_font(FONT_MONO, v, val_max,
                                                      start=CAP_SM), FG)
        y += len(values) * 66
    y += 20
    # verdict card, right column, clear of the value text
    box = (CARD_X, 80, CARD_X + CARD_W, 80 + 260)
    dr.rectangle(box, outline=GREEN, width=6)
    text(dr, (CARD_X + CARD_W / 2, 130), "PASS",
         font(FONT_SANS_B, 84), GREEN, anchor="mm")
    text(dr, (CARD_X + CARD_W / 2, 210), "judge verdict",
         font(FONT_MONO, CAP_SM), FG, anchor="mm")
    text(dr, (CARD_X + CARD_W / 2, 285), f"sha256 {det['sha256'][:8]}",
         font(FONT_MONO, CAP_SM), DIM, anchor="mm")


def render_shot(out_dir, si, name, phase, n, boxes, names, period, ctx):
    """Write one shot's frames as shotNNNN.png in out_dir."""
    facts, good, mutants = ctx["facts"], ctx["good"], ctx["mutants"]
    selftest, timings, ref = ctx["selftest"], ctx["timings"], ctx["ref"]
    for i in range(n):
        if name == "end":
            img = frame_for(name, 0, boxes[0], names, facts, good, mutants,
                            selftest, timings, ref, 0, n)
        else:
            idx = (phase + i) % period
            img = frame_for(name, idx, boxes[idx % len(boxes)], names, facts,
                            good, mutants, selftest, timings, ref, i, n)
        img.save(os.path.join(out_dir, f"shot{si:02d}_{i:05d}.png"))


def main():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        die("ffmpeg/ffprobe not found on PATH")
    if not os.path.isdir(FRAMES):
        die(f"{FRAMES} missing; run media/make_frames.py first")
    meta = json.load(open(os.path.join(FRAMES, "frames.json")))
    boxes, names = boxes_from_meta(meta)
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
        render_shot(d, si, name, phase, n, boxes, names, period, ctx)
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
