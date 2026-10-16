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
    # 0-2 s  the hook: the firmware answering the seeded CRC burst at full
    # width.  Window starts at 30.90 s, where the screen is already full of
    # the session's history (rows 0-28) and the long-hex CRC commands land
    # one every ~0.26 s of clip time -- frame 0 is dense, bright text, and
    # the burst never stops moving.
    ("boot-hero",  "boot.cast", 30.90, 8.0, 2.0, "0,0,120,40"),
    # 2-7 s  the scripted shell from HELP: HELP 5.20s, ECHO 6.79s, the
    # short CRC answers 10.8-16.4s, the RB section from 16.6s.  Window
    # 4.0-44.0 at 8x -- new lines land every ~0.3 s of clip time, so the
    # screen scrolls the whole slot.
    ("boot-shell", "boot.cast", 4.00, 8.0, 5.0, "0,0,120,40"),
    # 7-10 s the real toolchain build and its memory map.
    # make clean 0.05s, six objects 0.43-0.96s, the memory map at 0.99s.
    # A 3.0 s window at 1x holds the whole build, then it rests on the map.
    ("build",      "build.cast", 0.00, 1.0, 3.0, "0,0,120,40"),
    # 10-15 s the judge's verdict: the gate table at 7.54s and the JSON at
    # 7.57s.  Start just before the verdict lands so the table visibly
    # arrives on screen; the JSON holds for the rest of the window.
    ("grade",      "grade.cast", 7.40, 1.0, 4.6, "0,0,120,40"),
    # 15-21 s the mutant table at 12x -- the sped-up agent run.
    # MUTANT header 132.5s, build-broken 140.4s, crc-init 156.3s,
    # crc-poly 184.2s, ring-count-drift 235.1s: 12x covers 72 s of cast =
    # six mutant rows landing, one every ~1.2 s of clip time.
    ("selftest",   "selftest.cast", 132.00, 12.0, 5.0, "0,0,120,40"),
    # selftest's cast writes once per mutant build (~10-40 s of cast); the
    # idle gaps are real, so this clip moves only when a mutant row lands.
    # The composition carries the slot's motion: a strong camera push and
    # the counter/badge animation.
    # 21-27 s the CRC burst at 16x -- the fast clip.  Window 25.6-52.0 s:
    # the ring pushes (25.6-28 s), the wrap dumps (27.9-30.0s) and the
    # long-hex burst at 16x -- a line lands every ~0.4 s of clip time.
    ("boot-crc",   "boot.cast", 25.60, 16.0, 1.65, "0,0,120,40"),
    # 27-31.5 s the judge's verdict JSON landing on screen, real bytes.
    # same window as `grade`; the composition pans down the JSON as the
    # proof HUD holds its numbers.
    ("verdict",    "grade.cast", 7.40, 1.0, 4.5, "0,0,120,40"),
]


def build(out_dir, only=None):
    os.makedirs(out_dir, exist_ok=True)
    for name, cast, start, speed, dur, crop in SLOTS:
        if only and name != only:
            continue
        out = os.path.join(out_dir, "%s.mp4" % name)
        # term.py play's --start/--stop are real output seconds (cast
        # position = start * speed), so a window named in cast seconds --
        # as the storyboard's slots are -- must be divided by the speed.
        argv = [sys.executable, "-I", os.path.join(HERE, "term.py"), "play",
                os.path.join(CLIPS, cast), out,
                "--fps", str(FPS), "--speed", str(speed),
                "--start", "%.4f" % (start / speed),
                "--stop", "%.4f" % (start / speed + dur),
                "--width", str(WIDTH), "--height", str(HEIGHT)]
        if crop:
            argv += ["--crop", crop]
        print("clips: %-12s %s start=%.2f speed=%g dur=%.1fs"
              % (name, cast, start, speed, dur))
        subprocess.check_call(argv)
        # The composition shows this exact frame behind its <video>, so the
        # rendered video's frame 0 is real footage even before the browser
        # paints the first decoded frame (render-frame-0 was blank once;
        # the poster is what the gate's first-frame checks measure).
        poster = os.path.join(out_dir, "%s-poster.png" % name)
        subprocess.check_call(["ffmpeg", "-y", "-loglevel", "error",
                               "-i", out, "-frames:v", "1", poster])


def poster_dir(out_dir=None):
    """Where the posters were written (the composition mounts them)."""
    return out_dir or CLIPS


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
