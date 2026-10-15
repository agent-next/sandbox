#!/usr/bin/env python3
"""The shot plan for media/demo.mp4 -- one table, two consumers.

media/write_storyboard.py renders media/STORYBOARD.md from it (before the
video is cut) and media/make_video.py renders exactly these shots for
exactly these durations, so the storyboard and the cut cannot drift
apart.  Every "fills the frame" entry names the media/data/ file the shot
is drawn from; make_video.py fails if one is missing.
"""

FPS = 30

# key, scene function in make_video.py, frames, slot, fills, source, caption
SCENES = [
    dict(key="hook", frames=75, slot="hook",
         fills="the finished result fills the frame: the five-cell matrix "
               "table with the real interpreter stamps, the 3.9 cell in red "
               "(FAIL: match SyntaxError), a PASS stamp and a highlight band "
               "sweeping the rows",
         source="media/data/verdict-good.json -> metrics.cells",
         caption="5 CPython cells, 7 tests each -- the judge fails exactly "
                 "the 3.9 cell"),
    dict(key="yaml", frames=105, slot="input -> output",
         fills="examples/good/matrix.yaml (the real artifact) scrolling in "
               "a code panel, beside the four keys the judge parses lighting "
               "up as the file passes them",
         source="examples/good/matrix.yaml",
         caption="the whole artifact: one matrix.yaml + one run_matrix.py"),
    dict(key="build", frames=120, slot="input -> output",
         fills="the five cells appear one per beat with their measured "
               "interpreter stamp and pass/fail fill; a progress bar runs "
               "under the table the whole shot",
         source="media/data/verdict-good.json -> metrics.cells",
         caption="each cell: its own uv interpreter -- 3.9.25 ... 3.13.15"),
    dict(key="selftest", frames=195, slot="escalate",
         fills="a terminal panel running the real judge/selftest.sh "
               "transcript: the known-good PASS, then nine "
               "'killed by gate:' lines, while the KILLED counter climbs "
               "0 -> 9/9",
         source="media/data/selftest.log (judge/selftest.sh, real output)",
         caption="judge selftest, real output -- {selftest_speed}"),
    dict(key="verdict", frames=135, slot="escalate",
         fills="a terminal panel streaming grade.sh's verdict JSON, the "
               "eight gate badges flipping to PASS down the right rail and "
               "the PASS verdict landing",
         source="media/data/grade-good.txt (grade.sh stdout)",
         caption="grade.sh prints one verdict -- {grade_speed}"),
    dict(key="replay", frames=180, slot="escalate",
         fills="the fixing loop, replayed: three grade verdicts as cards, "
               "gate badges counting 1/8 -> 7/8 -> 8/8 with the failing "
               "gates named, labelled a replay -- not a live agent trace",
         source="media/data/loop.json + media/data/verdict-*.json",
         caption="bad -> partly fixed -> good -- a replay of real grade "
                 "verdicts"),
    dict(key="killmatrix", frames=180, slot="escalate",
         fills="the kill matrix: examples/good plus nine single-edit "
               "mutants against the eight gates, one row per beat, red "
               "cells carrying the judge's own measured detail, the "
               "kill-rate bar filling to 9/9",
         source="media/data/verdict-<mutant>.json (9 files)",
         caption="every single-edit mutant killed -- 9/9, floor 90 %"),
    dict(key="proof", frames=96, slot="proof",
         fills="the judge's mask bars fill from the JSON (toggle ON fails "
               "exactly 3.9, toggle OFF all pass) while the PASS verdict, "
               "exit codes and the five interpreter stamps ride on top as a "
               "HUD",
         source="media/data/verdict-good.json -> metrics.mask_on, mask_off, "
                "exit_codes, cells",
         caption="verdict PASS -- the mask matches the CPython-3.10 oracle"),
    dict(key="endcard", frames=90, slot="end card (static)",
         fills="a still frame: the one-line launch and the ask-your-agent "
               "pointer -- the only static shot",
         source="-",
         caption="run it: python3 cookbook/ci-test-matrix/run.py"),
]


def total_frames():
    return sum(s["frames"] for s in SCENES)


def spans():
    """[(scene, start_frame, end_frame_exclusive)] plus the total."""
    out, t = [], 0
    for s in SCENES:
        out.append((s, t, t + s["frames"]))
        t += s["frames"]
    return out, t


def fmt(start_frame, end_frame):
    return "%.1f-%.1f s" % (start_frame / FPS, end_frame / FPS)


def cuts_per_10s():
    """Scene cuts per 10 s (the video gate's floor is 0.8)."""
    return (len(SCENES) - 1) / (total_frames() / FPS) * 10.0
