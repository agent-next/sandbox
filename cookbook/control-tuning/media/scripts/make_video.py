#!/usr/bin/env python3
"""make_video.py - compose demo.mp4 master (lossless crf 0) for the
control-tuning demo.

The motion segments are MuJoCo 3-D renders of the exact traces the
judge wrote (media/data/<candidate>/s{1,2}_trace.csv), replayed
kinematically by render3d.py - never re-simulated. Proof sections
(result.png, loop.png) appear as figure frames, plus plain text cards.

Timeline (30 fps, 1920x1080, ~53 s):
  1. title card                          0.0-3.2 s
  2. card: S1 - 0.15 rad lean, good      3.2-4.2 s
  3. S1 replay, hero34 cam               4.2-9.0 s   (trace t 0->4.8)
  4. card: S2 - 1 m displacement, good   9.0-9.7 s
  5. S2 replay, tracking cam             9.7-18.1 s  (trace t 0->8.4)
  6. card: side-by-side torque gate     18.1-19.0 s
  7. too-aggressive vs good, S2         19.0-27.4 s  (0.9 s freeze on the
     t=0 torque-breach frame, then trace t 0->7.5)
  8. card: side-by-side settle gate     27.4-28.4 s
  9. too-sluggish vs good, S2           28.4-34.2 s  (trace t 0->10 @1.7x)
 10. result.png hold                    34.2-40.5 s
 11. loop.png hold                      40.5-47.2 s
 12. closing card                       47.2-52.4 s
"""
import argparse
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

import common as c
import render3d as r3

W, H, FPS = 1920, 1080, 30
FADE = 7  # frames of white-fade between segments


# ------------------------------------------------------------ frame cards
def card(title, sub=None, foot=None, accent=c.BLUE):
    """Plain text card as a PIL image."""
    im = Image.new("RGB", (W, H), r3.SURFACE)
    dr = ImageDraw.Draw(im)
    f_t = r3.font(68, bold=True)
    f_s = r3.font(34)
    f_f = r3.font(24)
    tw = dr.textlength(title, font=f_t)
    dr.text(((W - tw) / 2, H / 2 - 110), title, font=f_t, fill=r3.INK)
    dr.rectangle(((W - tw) / 2, H / 2 - 20, (W + tw) / 2, H / 2 - 14),
                 fill=r3._hex(accent))
    if sub:
        sw = dr.textlength(sub, font=f_s)
        dr.text(((W - sw) / 2, H / 2 + 10), sub, font=f_s, fill=r3.INK2)
    if foot:
        fw = dr.textlength(foot, font=f_f)
        dr.text(((W - fw) / 2, H - 90), foot, font=f_f, fill=r3.MUTED)
    return im


def figure_hold(png_name, caption):
    """Letterbox a media PNG into the frame with a caption strip."""
    im = Image.new("RGB", (W, H), r3.SURFACE)
    src = Image.open(os.path.join(c.MEDIA, png_name)).convert("RGB")
    scale = min((W - 160) / src.width, (H - 160) / src.height)
    src = src.resize((int(src.width * scale), int(src.height * scale)),
                     Image.LANCZOS)
    im.paste(src, ((W - src.width) // 2, (H - 90 - src.height) // 2))
    dr = ImageDraw.Draw(im)
    f_c = r3.font(26)
    cw = dr.textlength(caption, font=f_c)
    dr.text(((W - cw) / 2, H - 66), caption, font=f_c, fill=r3.INK2)
    return im


# -------------------------------------------------------------- streaming
class FFmpegSink:
    def __init__(self, out, fps, crf, preset):
        self.proc = subprocess.Popen(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
             "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
             "-c:v", "libx264", "-crf", str(crf), "-preset", preset,
             "-pix_fmt", "yuv420p", "-movflags", "+faststart", out],
            stdin=subprocess.PIPE)
        self.n = 0
        self.last = None

    def write(self, img):
        a = np.asarray(img, dtype=np.uint8)
        assert a.shape == (H, W, 3), a.shape
        self.proc.stdin.write(a.tobytes())
        self.last = Image.fromarray(a)
        self.n += 1

    def fade_to(self, img, n=FADE):
        if self.last is None:
            self.write(img)
            return
        a = np.asarray(self.last, dtype=float)
        b = np.asarray(img, dtype=float)
        for i in range(1, n + 1):
            f = i / n
            self.write(Image.fromarray(
                np.asarray(a + (b - a) * f, dtype=np.uint8)))

    def hold(self, img, secs):
        for _ in range(int(round(secs * FPS))):
            self.write(img)

    def close(self):
        self.proc.stdin.close()
        if self.proc.wait() != 0:
            sys.exit("make_video: ffmpeg failed")


def replay(rep, info, t0, t1, label=None, accent=c.BLUE, speed=1.0):
    """Generator of overlayed replay frames covering trace [t0, t1] played
    at `speed` trace-seconds per video-second."""
    n = int(round((t1 - t0) / speed * FPS))
    for i in range(n):
        yield rep.frame(t0 + i / FPS * speed, info, label=label,
                        accent=accent)


def sbs_frame(repL, infoL, labelL, accentL,
              repR, infoR, labelR, accentR, t):
    """One composed frame: two 960x1080 tracking renders side by side."""
    L = Image.fromarray(repL.frame(t, infoL, label=labelL,
                                   accent=accentL))
    R = Image.fromarray(repR.frame(t, infoR, label=labelR,
                                   accent=accentR))
    im = Image.new("RGB", (W, H), r3.SURFACE)
    im.paste(L, (0, 0))
    im.paste(R, (960, 0))
    im.paste(Image.new("RGB", (4, H), r3.INK2), (958, 0))
    return im


def side_by_side(repL, infoL, labelL, accentL,
                 repR, infoR, labelR, accentR,
                 t0, t1, speed=1.0):
    """Two 960x1080 tracking renders pasted into one 1920x1080 frame."""
    n = int(round((t1 - t0) / speed * FPS))
    for i in range(n):
        yield sbs_frame(repL, infoL, labelL, accentL,
                        repR, infoR, labelR, accentR,
                        t0 + i / FPS * speed)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--crf", type=int, default=0)
    ap.add_argument("--preset", default="ultrafast")
    args = ap.parse_args()

    backend = r3.gl_backend()
    print(f"make_video: GL backend {backend}")

    sink = FFmpegSink(args.out, FPS, args.crf, args.preset)

    # 1. title
    sink.fade_to(card(
        "LQR cart-pole control tuning",
        sub="an agent designs Q, R - the judge decides pass or fail",
        foot="cookbook/control-tuning  \u00b7  seed 20260101  \u00b7  "
             "trajectories rendered by MuJoCo from the judge's own traces"))
    sink.hold(sink.last, 3.0)

    # 2-3. S1 good replay (hero camera, cart barely moves)
    sink.fade_to(card("scenario 1 - recover from a 0.15 rad lean",
                      sub="good controller - judged trace replayed in MuJoCo",
                      accent=c.BLUE))
    sink.hold(sink.last, 0.7)
    rep, info = r3.make("good", 1, camera="hero34")
    for f in replay(rep, info, 0.0, 4.8, label="good"):
        sink.write(f)
    rep.close()

    # 4-5. S2 good replay (tracking camera)
    sink.fade_to(card("scenario 2 - return from a 1 m displacement",
                      sub="good controller - judged trace replayed in MuJoCo",
                      accent=c.BLUE))
    sink.hold(sink.last, 0.5)
    rep, info = r3.make("good", 2, camera="track")
    for f in replay(rep, info, 0.0, 8.4, label="good"):
        sink.write(f)
    rep.close()

    # 6-7. side-by-side: too-aggressive breaches the torque limit (S2).
    # The demand spike is a single trace row at t = 0, so the first
    # side-by-side frame is held 0.9 s to keep the LIMIT BREACHED flash
    # readable before the replay starts moving.
    sink.fade_to(card("side by side - too-aggressive vs good",
                      sub="scenario 2 - the torque gate kills it: "
                          "peak |\u03c4| = 2.52 N\u00b7m > 1 N\u00b7m",
                      accent=c.ORANGE))
    sink.hold(sink.last, 0.7)
    repL, infoL = r3.make("too-aggressive", 2, camera="track",
                          width=960)
    repR, infoR = r3.make("good", 2, camera="track", width=960)
    sink.hold(sbs_frame(repL, infoL, "too-aggressive", c.ORANGE,
                        repR, infoR, "good", c.BLUE, 0.0), 0.9)
    for f in side_by_side(repL, infoL, "too-aggressive", c.ORANGE,
                          repR, infoR, "good", c.BLUE, 0.0, 7.5):
        sink.write(f)
    repL.close()
    repR.close()

    # 8-9. side-by-side: too-sluggish never settles (S2), 1.7x speed
    sink.fade_to(card("side by side - too-sluggish vs good",
                      sub="scenario 2 at 1.7x - x never enters the "
                          "\u00b10.02 m band (10.00 s > 7 s)",
                      accent=c.ORANGE))
    sink.hold(sink.last, 0.7)
    repL, infoL = r3.make("too-sluggish", 2, camera="track", width=960)
    repR, infoR = r3.make("good", 2, camera="track", width=960)
    for f in side_by_side(repL, infoL, "too-sluggish", c.ORANGE,
                          repR, infoR, "good", c.BLUE, 0.0, 10.0,
                          speed=1.7):
        sink.write(f)
    repL.close()
    repR.close()

    # 10-11. proof: the figures as frames
    sink.fade_to(figure_hold(
        "result.png", "media/result.png - hero frame from the same replay, "
                      "gate table, Monte-Carlo panel"))
    sink.hold(sink.last, 6.0)
    sink.fade_to(figure_hold(
        "loop.png", "media/loop.png - mutant \u00d7 gate matrix, killer "
                    "traces, selftest kill rate"))
    sink.hold(sink.last, 6.5)

    # 12. closing
    sink.fade_to(card(
        "every number is a judge measurement",
        sub="traces: grade.sh --trace  \u00b7  verdicts: grade.sh --json  "
            "\u00b7  renders: MuJoCo kinematic replay",
        foot="judge/judge_lib.py is the oracle - nothing here re-simulates "
             "the plant"))
    sink.hold(sink.last, 5.0)

    sink.close()
    print(f"make_video: wrote {sink.n} frames to {args.out}")


if __name__ == "__main__":
    main()
