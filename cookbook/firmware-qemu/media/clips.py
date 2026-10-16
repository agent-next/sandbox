#!/usr/bin/env python3
"""Render the recorded casts in media/clips/ to the motion clips in media/clips/.

A clip is a window of a real recording, replayed at a chosen speed through
media/term.py's pyte+Pillow player and encoded by ffmpeg.  The windows and
speeds are the storyboard's slots (media/STORYBOARD.md); each window is
chosen so the footage it names is actually on screen for the whole slot.

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

# slot -> (cast, start_s in cast time, speed, duration_s of clip, crop cells)
# crop is the active region of the 100x34 terminal the camera shows: the
# storyboard's close-ups and pushes are this rectangle, never a synthetic
# zoom on a still.
SLOTS = [
    # 0-2 s  banner and first exchanges, real boot
    ("boot-hero",   "boot.cast", 0.60, 8.0, 2.0, None),
    # 2-7 s  the command script: HELP..ECHO, 46 responses
    ("boot-shell",  "boot.cast", 5.00, 8.0, 5.0, None),
    # 7-10 s real toolchain build and linker map
    ("build",       "build.cast", 0.20, 1.0, 2.8, None),
    # 10-15 s real judge grade: the gate table scrolling into the frame
    ("grade",       "grade.cast", 9.90, 1.0, 5.0, None),
    # 15-21 s real mutant self-test at 12x: 14 mutants and the summary
    ("selftest",    "selftest.cast", 300.0, 12.0, 6.0, None),
    # 21-27 s CRC and ring-buffer tail at 16x
    ("boot-crc",    "boot.cast", 45.0, 16.0, 6.0, None),
    # 27-31.5 s verdict JSON, camera push via the composition
    ("verdict",     "grade.cast", 10.72, 1.0, 4.5, None),
]


def build(out_dir, only=None):
    for name, cast, start, speed, dur, crop in SLOTS:
        if only and name != only:
            continue
        out = os.path.join(out_dir, "%s.mp4" % name)
        argv = [sys.executable, "-I", os.path.join(HERE, "term.py"), "play",
                os.path.join(CLIPS, cast), out,
                "--fps", str(FPS), "--speed", str(speed),
                "--start", "%.3f" % start, "--stop", "%.3f" % (start + dur)]
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
