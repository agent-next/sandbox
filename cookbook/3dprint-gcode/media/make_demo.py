#!/usr/bin/env python3
"""Build media/demo.mp4 from real renders and real verdicts.

Timeline (30 fps, 1920x1080, ~33 s):
  0-12 s   pyvista offscreen turntable of the finished print -- the same bead
           mesh the judge's interpreter measured (media/data/traces trace),
           one hard camera cut at 6 s
 12-21 s   full-frame card of media/result.png
 21-28 s   full-frame card of media/loop.png
 28-33 s   end card: the one command that reproduces the numbers

Captions are burned in with Pillow (>= 44 px). Frames are real renders -- no
matplotlib animation.

Run under Xvfb:  DISPLAY=:99 python3 media/make_demo.py
"""

import json
import os
import shutil
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import render_toolpath as rt

HERE = os.path.dirname(os.path.abspath(__file__))
TRACE = os.path.join(HERE, "data", "traces", "good.trace.json")
LOOP_DIR = os.path.join(HERE, "data", "loop")
RESULT_PNG = os.path.join(HERE, "result.png")
LOOP_PNG = os.path.join(HERE, "loop.png")
OUT = os.path.join(HERE, "demo.mp4")

W, H, FPS = 1920, 1080, 30
BG = "#101418"
INK = "#f0efec"
MUTED = "#9aa2ad"
ACCENT = "#3987e5"
GOOD = "#45d052"

FONT_DIR = "/usr/share/fonts/truetype/dejavu"
FRAMES = "/tmp/demo-frames"

# (n_frames, kind, caption, extra)
#   kind "turn": 3D turntable; extra=(azimuth_start_deg, azimuth_end_deg)
#   kind "card": full-frame PNG card; extra=path
#   kind "end":  end card
SEGMENTS = [
    (180, "turn", "bracket.stl -> OrcaSlicer G-code: the judged print",
     (-55.0, 65.0)),
    (180, "turn", "every bead: judge/interp.py replay of part.gcode",
     (65.0, 185.0)),
    (270, "card", "result.png: 12/12 gates PASS", RESULT_PNG),
    (210, "card", "loop.png: every mutant killed by its SPEC gate", LOOP_PNG),
    (150, "end", "reproduce: python3 cookbook/3dprint-gcode/run.py", None),
]


def font(size, bold=False):
    f = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(os.path.join(FONT_DIR, f), size)


def caption(img, text):
    """Burn a caption bar into the bottom of the frame (44 px+)."""
    d = ImageDraw.Draw(img)
    f = font(46, True)
    tw = d.textlength(text, font=f)
    bar_h = 92
    d.rectangle((0, H - bar_h, W, H), fill="#0b0e12")
    d.text(((W - tw) // 2, H - bar_h + 20), text, font=f, fill=INK)
    return img


def kill_rate():
    """(killed, total) from the real mutant verdicts; (0, 0) if absent."""
    if not os.path.isdir(LOOP_DIR):
        return 0, 0
    vs = [json.load(open(os.path.join(LOOP_DIR, f)))
          for f in sorted(os.listdir(LOOP_DIR))
          if f.endswith(".json") and f != "good.json"]
    if not vs:
        return 0, 0
    return sum(1 for v in vs if v["verdict"] != "PASS"), len(vs)


def build_plotter(trace):
    """One pyvista plotter reused for every turntable frame."""
    import pyvista as pv

    pl = pv.Plotter(off_screen=True, window_size=(W, H))
    pl.set_background(BG)
    rt.add_bed(pl)
    pd, _ = rt.bead_mesh(trace)
    pl.add_mesh(pd, scalars="layer_z", cmap="plasma", smooth_shading=True,
                specular=0.35, specular_power=24, diffuse=0.8, ambient=0.3,
                scalar_bar_args={"title": "layer Z (mm)", "vertical": False,
                                 "position_x": 0.08, "position_y": 0.06,
                                 "color": MUTED, "title_font_size": 18,
                                 "label_font_size": 16, "width": 0.30,
                                 "height": 0.06})
    stl = rt.bracket_mesh()
    pl.add_mesh(stl, color="#2e6f9e", opacity=0.16, smooth_shading=True,
                specular=0.15, diffuse=0.6, ambient=0.3)
    return pl


def turn_frame(pl, az):
    rt.camera_part(pl, azimuth=az, elevation=22.0, dist=92.0)
    arr = pl.screenshot(return_img=True)
    return Image.fromarray(arr)


def card_frame(path):
    return Image.open(path).convert("RGB").resize((W, H), Image.LANCZOS)


def end_frame():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    killed, total = kill_rate()
    d.text((0, 330), "judge: 12/12 gates PASS", font=font(64, True), fill=GOOD,
           align="center", anchor="ma")
    if total:
        d.text((0, 430), "selftest kill rate %d/%d" % (killed, total),
               font=font(48), fill=MUTED, align="center", anchor="ma")
    d.text((0, 580), "python3 cookbook/3dprint-gcode/run.py",
           font=font(56, True), fill=ACCENT, align="center", anchor="ma")
    d.text((0, 680), "sandbox + OrcaSlicer + Klipper, verdict JSON out",
           font=font(40), fill=MUTED, align="center", anchor="ma")
    return img


def main():
    if os.path.isdir(FRAMES):
        shutil.rmtree(FRAMES)
    os.makedirs(FRAMES)

    trace = json.load(open(TRACE))
    n = 0
    for seg_i, (nf, kind, cap, extra) in enumerate(SEGMENTS):
        if kind == "turn":
            pl = build_plotter(trace)
        for k in range(nf):
            t = k / max(nf - 1, 1)
            if kind == "turn":
                az = extra[0] + (extra[1] - extra[0]) * t
                img = turn_frame(pl, az)
            elif kind == "card":
                img = card_frame(extra)
            else:
                img = end_frame()
            caption(img, cap)
            img.save(os.path.join(FRAMES, "f%04d.png" % n))
            n += 1
        if kind == "turn":
            pl.close()
        print("segment %d done (%d frames total)" % (seg_i + 1, n), flush=True)

    cmd = ("ffmpeg -y -loglevel error -framerate %d -i %s/f%%04d.png "
           "-c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p "
           "-movflags +faststart %s" % (FPS, FRAMES, OUT))
    os.system(cmd)
    print("wrote", OUT, os.path.getsize(OUT) / 1e6, "MB")


if __name__ == "__main__":
    main()
