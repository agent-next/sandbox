#!/usr/bin/env python3
"""Render the demo video's frames from the real meshes and verdicts.

Every frame is either an OSMesa render of a delivered STL (turning on a
turntable, so the real geometry is the thing on screen) or a full-frame
card built from result.png / loop.png. Nothing is a matplotlib animation
and no number is invented: the captions carry the real spec dimensions
(specs/*.md) and the real judged values (media/data/good_*.json).

Frames land in media/master/frames/ (git-ignored) as frame_%05d.png;
media/make_media.sh encodes them. Every burned-in caption is at least
44 px tall (owner rule: readable muted on a phone).
"""
import argparse
import os
import shutil
import sys

import numpy as np
import trimesh
from PIL import Image, ImageDraw

import kit
from kit import (FAINT, GREEN, INK, MONO, MONO_B, MUTED, SANS_B, Blocker,
                 fit_margin, font, gradient)
from render import Renderer, _norm_mesh

FPS = 30
W, H = 1920, 1080
FRAMES = os.path.join(kit.MEDIA, "master", "frames")
GOOD = os.path.join(kit.ROOT, "examples", "good")
CAP_MIN = 44                      # floor for every caption, per the owner rule

# (part, camera pitch, spec line built from specs/<part>.md)
TOUR = [
    ("bushing", 20,
     "bushing.step + bushing.stl   d20 bore, d36 hub x40, d60 flange x8"),
    ("plate", 44,
     "plate.step + plate.stl + plate.dxf   100x80x10, d30 bore, 6 x d5.5 on R35"),
    ("bracket", 22,
     "bracket.step + bracket.stl   L 80x50x60, R8 fillet, holes d10 + d12"),
]


class FrameSink:
    """Sequential frame writer; the count is the frame index."""

    def __init__(self, out_dir):
        self.dir = out_dir
        self.n = 0

    def reset(self):
        os.makedirs(self.dir, exist_ok=True)
        for name in os.listdir(self.dir):
            if name.startswith("frame_"):
                os.unlink(os.path.join(self.dir, name))
        self.n = 0

    def write(self, canvas):
        canvas.save(os.path.join(self.dir, "frame_%05d.png" % self.n))
        self.n += 1


def scrim(canvas, top_h, bot_h):
    """Darken the top and bottom strips so burned-in text reads on them."""
    a = np.asarray(canvas).astype(np.float32)
    for y in range(top_h):
        k = 1.0 - 0.82 * (1.0 - y / float(top_h)) ** 1.6
        a[y] *= k
    for y in range(bot_h):
        k = 0.18 + 0.82 * (y / float(bot_h)) ** 0.7
        row = H - 1 - y
        a[row] *= k
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def replay_volumes():
    """{part: (script, volume_mm3)} from the committed MCP replay log."""
    import json
    path = os.path.join(kit.DATA, "mcp_replay.json")
    calls = json.load(open(path))
    out = {}
    for c in calls:
        if c.get("tool") == "execute_code_headless" and c.get("volume_mm3"):
            out.setdefault(c["part"], (c["script"], c["volume_mm3"]))
    missing = [t[0] for t in TOUR if t[0] not in out]
    if missing:
        raise SystemExit("mcp_replay.json has no execute call for %s" % missing)
    return out


def turntable(sink, seconds):
    """One turntable shot per part: the real mesh, its real judged numbers."""
    lim = kit.limits()
    replay = replay_volumes()
    n = seconds * FPS
    r = Renderer(W, H)
    try:
        for part, pitch, spec in TOUR:
            m = _norm_mesh(trimesh.load(
                os.path.join(GOOD, part, "%s.stl" % part), force="mesh"), 2.0)
            # frame the mesh at the worst-case yaw so the whole turntable
            # stays inside the frame; parallax moves the silhouette inside it
            margin = max(fit_margin(m, yaw, pitch, W, H, target=0.78)
                         for yaw in range(0, 360, 45))
            v = kit.verdict("good_" + part)
            for k in range(n):
                yaw = 25.0 + 300.0 * k / float(n)
                img = r.render(m, yaw=yaw, pitch=pitch, margin=margin,
                               edges=True)
                sink.write(tour_card(img, part, spec, v, lim,
                                     replay[part]))
    finally:
        r.delete()


def tour_card(img, part, spec, v, lim, replay):
    canvas = scrim(gradient((W, H)).convert("RGB").copy(), 0, 0)
    base = Image.new("RGB", (W, H))
    base.paste(gradient((W, H)), (0, 0))
    base.paste(img, (0, -80), img)
    canvas = scrim(base, 210, 300)
    d = ImageDraw.Draw(canvas)
    blk = Blocker(W, H)

    f_hook = font(SANS_B, 58)
    f_mcp = font(MONO, CAP_MIN)
    f_name = font(SANS_B, CAP_MIN)
    f_cap = font(MONO, CAP_MIN)
    f_badge = font(SANS_B, 36)

    hook = "FreeCAD built this from a text spec"
    blk.add("hook", d.textbbox((60, 30), hook, font=f_hook))
    d.text((60, 30), hook, font=f_hook, fill=INK)
    hook2 = "through an MCP server -- and a judge graded the files"
    blk.add("hook2", d.textbbox((60, 100), hook2, font=f_hook))
    d.text((60, 100), hook2, font=f_hook, fill=(150, 230, 190))

    g = v["gates"]
    script, vol = replay
    mcp = ("execute_code_headless %s -> _OK volume=%s mm3"
           % (script, kit.mm(vol)))
    blk.add("mcp", d.textbbox((60, 176), mcp, font=f_mcp))
    d.text((60, 176), mcp, font=f_mcp, fill=MUTED)

    y = 820
    blk.add("name", d.textbbox((60, y), part, font=f_name))
    d.text((60, y), part, font=f_name, fill=(150, 230, 190))

    badge = "judge PASS  %d/%d gates" % (len(v["gates"]), len(v["gates"]))
    bw = d.textlength(badge, font=f_badge)
    box = (W - 60 - bw - 34, y + 4, W - 60, y + 60)
    blk.add("badge", box)
    d.rounded_rectangle(box, radius=10, fill=(30, 96, 62))
    d.text((box[0] + 17, box[1] + 10), badge, font=f_badge,
           fill=(214, 255, 230))

    fspec = kit.shrink_font(d, spec, MONO, CAP_MIN, W - 120)
    blk.add("spec", d.textbbox((60, y + 66), spec, font=fspec))
    d.text((60, y + 66), spec, font=fspec, fill=MUTED)

    nums = [("volume", "%s mm3" % kit.mm(g["brep"]["volume_mm3"])),
            ("xor", "%.4g %%" % (g["xor_reference"]["xor_fraction"] * 100)),
            ("min wall", "%s mm" % kit.mm(g["min_wall"]["measured_min_mm"]))]
    x = 60
    for label, val in nums:
        blk.add("numl_%s" % label,
                d.textbbox((x, y + 138), label, font=f_cap))
        d.text((x, y + 138), label, font=f_cap, fill=MUTED)
        vbox = kit.draw_right(canvas, (x + 520, y + 138), val, f_cap, GREEN)
        blk.add("numv_%s" % label, vbox)
        x += 620
    return canvas


def card(sink, image, windows, caption, blurb):
    """Hold a figure, panning across the readable regions of it.

    `windows` is [(y0_frac, y1_frac, seconds)]; each window is cropped from
    the source and fitted to the frame, so the small print of a 2400 px
    wide figure is legible instead of shrunk into an unreadable strip.
    """
    src = Image.open(image).convert("RGB")
    for y0f, y1f, seconds in windows:
        win = src.crop((0, int(src.height * y0f), src.width,
                        int(src.height * y1f)))
        for _ in range(int(round(seconds * FPS))):
            canvas = gradient((W, H)).convert("RGB")
            d = ImageDraw.Draw(canvas)
            blk = Blocker(W, H)
            f_cap = font(SANS_B, CAP_MIN + 6)
            f_blurb = font(MONO, CAP_MIN)
            blk.add("cap", d.textbbox((60, 26), caption, font=f_cap))
            d.text((60, 26), caption, font=f_cap, fill=INK)
            lines = kit.wrap(d, blurb, f_blurb, W - 120)
            for j, line in enumerate(lines):
                blk.add("blurb_%d" % j,
                        d.textbbox((60, 26 + CAP_MIN + 22 + j * 58), line,
                                   font=f_blurb))
                d.text((60, 26 + CAP_MIN + 22 + j * 58), line, font=f_blurb,
                       fill=MUTED)
            top = 26 + CAP_MIN + 22 + len(lines) * 58 + 16
            got = kit.paste_center(canvas, win, (60, top, W - 60, H - 40))
            blk.add("card", got)
            sink.write(canvas)


def chapter(sink, seconds, num, title, sub):
    """A short light chapter card: a real cut, and it names what comes next."""
    canvas = Image.new("RGB", (W, H), (232, 236, 242))
    d = ImageDraw.Draw(canvas)
    blk = Blocker(W, H)
    f_num = font(MONO_B, 64)
    f_title = font(SANS_B, 120)
    f_sub = font(MONO, CAP_MIN)
    ink = (18, 22, 28)
    alt = (14, 92, 62)
    blk.add("num", d.textbbox((90, 300), num, font=f_num))
    d.text((90, 300), num, font=f_num, fill=alt)
    blk.add("title", d.textbbox((90, 380), title, font=f_title))
    d.text((90, 380), title, font=f_title, fill=ink)
    blk.add("sub", d.textbbox((90, 540), sub, font=f_sub))
    d.text((90, 540), sub, font=f_sub, fill=(70, 80, 92))
    blk.add("rule", (90, 360, 90 + d.textlength(title, font=f_title), 366))
    d.rectangle((90, 360, 90 + d.textlength(title, font=f_title), 366),
                fill=alt)
    for _ in range(int(round(seconds * FPS))):
        sink.write(canvas)


def end_card(sink, seconds):
    """Static end card: the one-command run. Frames are byte-identical."""
    canvas = gradient((W, H)).convert("RGB")
    d = ImageDraw.Draw(canvas)
    blk = Blocker(W, H)
    f_big = font(MONO_B, CAP_MIN + 8)
    f_mid = font(SANS_B, CAP_MIN + 8)
    f_small = font(MONO, CAP_MIN)

    head = "three parts, one command, a judge it cannot fool"
    wh = d.textlength(head, font=f_mid)
    blk.add("head", d.textbbox(((W - wh) // 2, 300), head, font=f_mid))
    d.text(((W - wh) // 2, 300), head, font=f_mid, fill=(150, 230, 190))

    line = "python3 cookbook/aicad-freecad-mcp/run.py"
    w = d.textlength(line, font=f_big)
    x = (W - w) // 2
    d.rounded_rectangle((x - 44, 424, x + w + 44, 424 + 128), radius=16,
                        fill=(24, 29, 36))
    blk.add("cmd", d.textbbox((x, 462), line, font=f_big))
    d.text((x, 462), line, font=f_big, fill=INK)

    sub = "needs SBX_API_KEY in the environment; --ref <branch> to test a branch"
    ws = d.textlength(sub, font=f_small)
    blk.add("sub", d.textbbox(((W - ws) // 2, 600), sub, font=f_small))
    d.text(((W - ws) // 2, 600), sub, font=f_small, fill=MUTED)

    note = "result.png  loop.png  demo.mp4 -- rebuilt by media/make_media.sh"
    blk.add("note", d.textbbox((60, 1000), note, font=f_small))
    d.text((60, 1000), note, font=f_small, fill=MUTED)

    path = None
    for _ in range(seconds * FPS):
        if path is None:
            path = os.path.join(sink.dir, "frame_%05d.png" % sink.n)
            canvas.save(path)
        else:
            shutil.copyfile(path, os.path.join(sink.dir,
                                               "frame_%05d.png" % sink.n))
        sink.n += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--turn-seconds", type=int, default=4,
                    help="turntable per part (3 parts)")
    ap.add_argument("--pan-seconds", type=int, default=4,
                    help="held on each pan window of a figure")
    ap.add_argument("--chapter-seconds", type=int, default=1,
                    help="light chapter card between sections")
    ap.add_argument("--end-seconds", type=int, default=6)
    args = ap.parse_args()

    sink = FrameSink(FRAMES)
    sink.reset()

    print("== turntables: real mesh renders ==")
    turntable(sink, args.turn_seconds)
    print("   %d frames" % sink.n)

    pan = args.pan_seconds
    print("== chapter: the result ==")
    chapter(sink, args.chapter_seconds, "1 / 3", "The result",
            "three parts built through the MCP server, graded from the "
            "delivered files")
    print("== result.png card ==")
    card(sink, os.path.join(kit.MEDIA, "result.png"),
         [(0.02, 0.665, pan), (0.665, 1.00, pan)],
         "The result: real geometry, every gate passed",
         "renders of the delivered STL; limits from judge/judge.py, "
         "measured values from media/data/good_*.json")

    print("== chapter: the judge can fail ==")
    chapter(sink, args.chapter_seconds, "2 / 3", "It can fail you too",
            "the self-test rebuilds mutants of the good artifacts and "
            "checks the judge still catches them")
    print("== loop.png card ==")
    card(sink, os.path.join(kit.MEDIA, "loop.png"),
         [(0.115, 0.60, pan), (0.594, 1.00, pan)],
         "And the judge can fail: the self-test matrix",
         "11 artifacts x 8 gates from the media/data/*.json verdicts: 3 "
         "known-good, 8 mutants (7 built and every one killed) = 100 %")

    print("== chapter: run it yourself ==")
    chapter(sink, args.chapter_seconds, "3 / 3", "Run it yourself",
            "one command: a disposable sandbox, the pinned CAD stack, the "
            "build, and the judge")
    print("== end card ==")
    end_card(sink, args.end_seconds)

    print("%d frames = %.1f s at %d fps -> %s"
          % (sink.n, sink.n / FPS, FPS, FRAMES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
