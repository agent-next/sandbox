#!/usr/bin/env python3
"""Render the recorded casts in media/clips/ to the motion clips in media/clips/.

A clip is a window of a real recording, replayed at a chosen speed through
media/term.py's pyte+Pillow player and encoded by ffmpeg.  The windows and
speeds are the storyboard's slots (media/STORYBOARD.md); each window is
chosen so the footage it names is actually on screen for the whole slot.

`crop` is the storyboard's close-ups and pushes: the rectangle of the 100x34
terminal the camera shows.  A push is a crop of the recording, never a
synthetic zoom on a still.

Every window below was measured against the casts with a pyte replay (see
media/STORYBOARD.md for the measured start times), so the content named in
each slot is on screen when the slot runs.

Usage:
    clips.py [--out DIR]
"""

import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CLIPS = os.path.join(HERE, "clips")
FPS = 30
WIDTH = 1920
HEIGHT = 1080

# slot -> (name, cast, start_s, speed, duration_s, crop_or_None)
#
# The start times below were measured by replaying each cast through pyte
# (media/STORYBOARD.md records how), so the footage each slot names is on
# screen for the whole slot.  `crop` is the X,Y,W,H rectangle of the 120x50
# terminal the camera frames -- a close-up of the real recording, never a
# zoom on a still.  Each rectangle holds the rows that window actually
# writes (measured), and its aspect is ~16:9 (a 120-col window needs ~40
# rows at the terminal's 0.60 glyph ratio), so the clip fills the
# 1920x1080 frame without letterboxing.
SLOTS = [
    # 0-2 s  the launch line and the boot banner landing.
    # banner at 0.50 s; window 0.45-2.45 at 8x keeps it on screen the whole
    # slot.  The window writes 2 rows; the frame is still 16:9 so the
    # composition's camera has room to push.
    ("boot-hero",  "boot.cast", 0.45, 8.0, 2.0, "0,0,120,40"),
    # 2-7 s  the scripted shell: HELP..ECHO, then the first CRC answers.
    # HELP 5.40s, ECHO 7.35s, first CRC 11.20s; window 4.20-9.20 at 8x.
    # maxrow 17 -> crop rows 0-17; the composition zooms in on it.
    ("boot-shell", "boot.cast", 4.20, 8.0, 5.0, "0,0,120,40"),
    # 7-10 s the real toolchain build and its memory map.
    # make clean 0.10s, six objects to 1.40s, the map at 1.50s.
    # maxrow 22 -> rows 0-22.
    ("build",      "build.cast", 0.10, 1.0, 2.8, "0,0,120,40"),
    # 10-15 s the judge's verdict line and its JSON verdict.
    # grade.sh prints the gate table at 8.0s and the JSON at 8.6s.
    ("grade",      "grade.cast", 7.90, 1.0, 4.6, "0,0,120,40"),
    # 15-21 s the mutant table at 12x -- the sped-up agent run.
    # MUTANT header at 146.6s, build-broken 155.6s, crc-init 175.8s.
    ("selftest",   "selftest.cast", 146.00, 12.0, 5.0, "0,0,120,40"),
    # 21-27 s the ring-buffer push/pop tail at 16x -- the fast clip.
    # RB push 010203... at 26.2s; window 24-40 at 16x.
    ("boot-crc",   "boot.cast", 24.00, 16.0, 6.0, "0,0,120,40"),
    # 27-31.5 s the judge's verdict JSON landing on screen, real bytes.
    ("verdict",    "grade.cast", 7.90, 1.0, 4.5, "0,0,120,40"),
]


def build(out_dir, only=None):
    os.makedirs(out_dir, exist_ok=True)
    for name, cast, start, speed, dur, crop in SLOTS:
        if only and name != only:
            continue
        out = os.path.join(out_dir, "%s.mp4" % name)
        argv = [sys.executable, "-I", os.path.join(HERE, "term.py"), "play",
                os.path.join(CLIPS, cast), out,
                "--fps", str(FPS), "--speed", str(speed),
                "--start", "%.3f" % start, "--stop", "%.3f" % (start + dur),
                "--width", str(WIDTH), "--height", str(HEIGHT)]
        if crop:
            argv += ["--crop", crop]
        print("clips: %-12s %s start=%.2f speed=%g dur=%.1fs"
              % (name, cast, start, speed, dur))
        subprocess.check_call(argv)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=CLIPS)
    ap.add_argument("--only", default=None)
    args = ap.parse_args()
    if not os.path.isdir(CLIPS):
        sys.exit("clips.py: %s missing -- run media/record.py first" % CLIPS)
    build(args.out, args.only)
    return 0


if __name__ == "__main__":
    sys.exit(main())
