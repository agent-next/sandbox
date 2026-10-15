#!/usr/bin/env python3
"""Generate known-bad artifacts for the self-test by single edits of the good one.

Each mutant is the good counter with exactly one scripted edit; the
self-test expects every mutant to fail at least one gate (SPEC.md). The
edits are the realistic ways a people counter goes wrong: the tripwire
in the wrong place, a size filter that admits trolleys, directions
swapped, a threshold that loses pedestrians, presence mistaken for
crossing, a missing clip, a pasted-in answer table, a wrong frame rate
and unsorted output.
"""

import os
import sys

# (name, must-exist-anchor, replacement)
EDIT = [
    ("line_shifted",
     'line_x = vid["width_px"] * spec["tripwire"]["x_fraction"]',
     'line_x = vid["width_px"] * (spec["tripwire"]["x_fraction"]\n'
     '                              + 30.0 / vid["width_px"])'),
    ("width_filter_off",
     'MIN_W, MAX_W = 8, 30     # pedestrian blob width window (px); wider = trolley',
     'MIN_W, MAX_W = 8, 60     # pedestrian blob width window (px); wider = trolley'),
    ("direction_flip",
     '                    d_east = 1 if tr.x > tr.px else 0',
     '                    d_east = 0 if tr.x > tr.px else 1'),
    ("threshold_high",
     'THR = 25                 # foreground threshold after mean normalisation',
     'THR = 130                # foreground threshold after mean normalisation'),
    ("presence_counting",
     '''                if abs(tr.x - line_x) >= RECROSS_HYST_PX:
                    tr.armed = True
                if (tr.armed and tr.age >= MIN_TRACK_FRAMES
                        and tr.px is not None
                        and (tr.px - line_x) * (tr.x - line_x) <= 0
                        and tr.px != tr.x):''',
     '''                if (tr.age == MIN_TRACK_FRAMES
                        and abs(tr.x - line_x) < 30):'''),
    ("missing_clip",
     '    cap = cv2.VideoCapture(vid["file"])',
     '    cap = cv2.VideoCapture(vid["file"] + ".missing")'),
    ("hardcoded_truth",
     '    events.sort()',
     '    events = [(6.097, 1, 0), (7.645, 1, 0), (9.800, 1, 0),\n'
     '              (12.595, 1, 0), (14.045, 1, 0), (15.800, 0, 1),\n'
     '              (18.961, 1, 0), (20.510, 1, 0), (22.017, 1, 0),\n'
     '              (23.752, 1, 0), (25.211, 1, 0), (28.610, 1, 0),\n'
     '              (31.297, 0, 1), (33.846, 0, 1), (35.296, 0, 1),\n'
     '              (36.746, 0, 1), (38.196, 0, 1), (40.650, 0, 1),\n'
     '              (44.571, 0, 1), (46.682, 0, 1)]\n'
     '    events.sort()'),
    ("fps_wrong",
     '    fps = vid["fps"]',
     '    fps = vid["fps"] * 1.5'),
    ("reverse_order",
     '    events.sort()',
     '    events.reverse()'),
]


def main():
    src_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "examples", "good")
    with open(os.path.join(src_dir, "counter.py")) as fh:
        good = fh.read()
    out_dir = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "mutants")
    os.makedirs(out_dir, exist_ok=True)
    names = []
    for name, old, new in EDIT:
        if old not in good:
            raise SystemExit(f"mutant {name}: edit anchor not found in good counter")
        mutant = good.replace(old, new, 1)
        if mutant == good:
            raise SystemExit(f"mutant {name}: edit produced no change")
        with open(os.path.join(out_dir, name + ".py"), "w") as fh:
            fh.write(mutant)
        names.append(name)
    print("\n".join(names))


if __name__ == "__main__":
    main()
