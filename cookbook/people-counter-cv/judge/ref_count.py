#!/usr/bin/env python3
"""Judge-internal reference people counter (agreement gate).

An independent implementation of the counting task using a different
method from the artifact under test: adaptive background modelling
(MOG2) instead of a static reference frame, plus contour filtering and a
simple nearest-neighbour tracker. The good artifact and this reference
must agree on per-direction counts and crossing times within tight
tolerances (SPEC.md, agreement gate) - two methods, one answer.

Judge-internal: the artifact under test never sees this file.
"""

import csv
import json

import cv2
import numpy as np

VAR_THRESHOLD = 50.0    # MOG2 foreground decision threshold
MIN_W, MAX_W = 8, 30
MIN_H, MAX_H = 12, 34
MATCH_RADIUS_PX = 16
MIN_TRACK_FRAMES = 3
MISS_TOLERANCE = 5
RECROSS_HYST_PX = 15


def main():
    with open("spec.json") as fh:
        spec = json.load(fh)
    vid = spec["video"]
    fps = vid["fps"]
    line_x = vid["width_px"] * spec["tripwire"]["x_fraction"]

    cap = cv2.VideoCapture(vid["file"])
    if not cap.isOpened():
        raise SystemExit(f"ref_count: cannot open {vid['file']}")
    mog = cv2.createBackgroundSubtractorMOG2(
        history=200, varThreshold=VAR_THRESHOLD, detectShadows=False)

    tracks, events = [], []
    k = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        gray = frame if frame.ndim == 2 else cv2.cvtColor(frame,
                                                          cv2.COLOR_BGR2GRAY)
        fg = mog.apply(gray)
        fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
        n, _, stats, cents = cv2.connectedComponentsWithStats(fg, 8)
        blobs = []
        for i in range(1, n):
            x, y, w, h, area = stats[i]
            if MIN_W <= w <= MAX_W and MIN_H <= h <= MAX_H \
                    and area >= 0.3 * MIN_W * MIN_H:
                blobs.append((float(cents[i][0]), float(cents[i][1])))

        taken = set()
        for tr in tracks:
            best, bd = None, MATCH_RADIUS_PX
            for j, (x, y) in enumerate(blobs):
                if j in taken:
                    continue
                d = ((x - tr["x"]) ** 2 + (y - tr["y"]) ** 2) ** 0.5
                if d < bd:
                    best, bd = j, d
            if best is None:
                tr["missed"] += 1
                continue
            taken.add(best)
            px, tr["x"], tr["y"] = tr["x"], blobs[best][0], blobs[best][1]
            tr["age"] += 1
            tr["missed"] = 0
            if abs(tr["x"] - line_x) >= RECROSS_HYST_PX:
                tr["armed"] = True
            if (tr["armed"] and tr["age"] >= MIN_TRACK_FRAMES
                    and (px - line_x) * (tr["x"] - line_x) <= 0
                    and px != tr["x"]):
                f = (line_x - px) / (tr["x"] - px)
                events.append(((k - 1 + f) / fps,
                               1 if tr["x"] > px else 0))
                tr["armed"] = False
        tracks = [t for t in tracks if t["missed"] <= MISS_TOLERANCE]
        for j, (x, y) in enumerate(blobs):
            if j not in taken:
                tracks.append({"x": x, "y": y, "age": 0, "missed": 0,
                               "armed": True})
        k += 1
    cap.release()

    events.sort()
    with open("crossings.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(spec["artifact"]["columns"])
        for t, east in events:
            w.writerow([f"{t:.3f}", east, 1 - east])
    print(f"ref_count: {len(events)} crossings "
          f"({sum(e for _, e in events)} east)")


if __name__ == "__main__":
    main()
