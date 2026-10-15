#!/usr/bin/env python3
"""Count pedestrians crossing a tripwire in a grayscale surveillance clip.

Reads spec.json from the current directory for the sensor description
(resolution, fps, tripwire position, pedestrian size range) and the clip
at spec["video"]["file"], then writes crossings.csv: one row per crossing,
columns t_cross_s,east,west (east/west are 0/1, exactly one is 1).

Method: mean-normalised background subtraction (a global illumination
drift must not read as motion), morphological cleanup, connected
components filtered to pedestrian size, nearest-neighbour centroid
tracking, and a tripwire edge trigger (a crossing is the sign change of
x - line between consecutive frames of one track, not proximity to the
line - people that stop at the line or turn back are not counted).
"""

import csv
import json

import cv2
import numpy as np

THR = 25                 # foreground threshold after mean normalisation
MIN_W, MAX_W = 8, 30     # pedestrian blob width window (px); wider = trolley
MIN_H, MAX_H = 12, 34    # pedestrian blob height window (px)
MATCH_RADIUS_PX = 14     # max centroid move between frames
MIN_TRACK_FRAMES = 3     # a track counts only after it has lived this long
MISS_TOLERANCE = 5       # frames a track survives without a detection
RECROSS_HYST_PX = 15     # distance from the line at which a track re-arms
                         # after a crossing (the genuine double-crosser turns
                         # far beyond the line; sub-pixel centroid jitter at
                         # the line must not read as a second crossing)


def detect_blobs(gray, bg, width, height):
    """Mean-normalised difference against the static reference frame."""
    norm = gray.astype(np.float32) - gray.mean()
    diff = np.abs(norm - bg).astype(np.uint8)
    mask = (diff > THR).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, _, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if not (MIN_W <= w <= MAX_W and MIN_H <= h <= MAX_H):
            continue
        if area < 0.3 * MIN_W * MIN_H:
            continue
        out.append((float(cents[i][0]), float(cents[i][1])))
    return out


class Track:
    __slots__ = ("x", "y", "age", "missed", "px", "armed")

    def __init__(self, x, y):
        self.x, self.y, self.age, self.missed = x, y, 0, 0
        self.px = None
        self.armed = True


def main():
    with open("spec.json") as fh:
        spec = json.load(fh)
    vid = spec["video"]
    fps = vid["fps"]
    line_x = vid["width_px"] * spec["tripwire"]["x_fraction"]

    cap = cv2.VideoCapture(vid["file"])
    if not cap.isOpened():
        raise SystemExit(f"counter: cannot open {vid['file']}")
    ok, first = cap.read()
    if not ok:
        raise SystemExit("counter: empty clip")
    if first.ndim == 3:
        first = cv2.cvtColor(first, cv2.COLOR_BGR2GRAY)
    bg = first.astype(np.float32) - first.mean()   # clip starts empty

    tracks, gone, events = [], [], []
    k = 0
    while True:
        if k:   # frame 0 already read; it is the background reference
            ok, frame = cap.read()
            if not ok:
                break
        else:
            frame = first
        gray = frame if frame.ndim == 2 else cv2.cvtColor(frame,
                                                          cv2.COLOR_BGR2GRAY)
        blobs = detect_blobs(gray, bg, vid["width_px"], vid["height_px"])
        used = set()
        for tr in tracks:
            best, bd = None, MATCH_RADIUS_PX
            for j, (x, y) in enumerate(blobs):
                if j in used:
                    continue
                d = ((x - tr.x) ** 2 + (y - tr.y) ** 2) ** 0.5
                if d < bd:
                    best, bd = j, d
            if best is not None:
                used.add(best)
                tr.px, tr.x, tr.y = tr.x, blobs[best][0], blobs[best][1]
                tr.age += 1
                tr.missed = 0
                if abs(tr.x - line_x) >= RECROSS_HYST_PX:
                    tr.armed = True
                if (tr.armed and tr.age >= MIN_TRACK_FRAMES
                        and tr.px is not None
                        and (tr.px - line_x) * (tr.x - line_x) <= 0
                        and tr.px != tr.x):
                    f = (line_x - tr.px) / (tr.x - tr.px)
                    t = (k - 1 + f) / fps
                    d_east = 1 if tr.x > tr.px else 0
                    tr.armed = False
                    events.append((t, d_east, 1 - d_east))
            else:
                tr.missed += 1
        tracks = [t for t in tracks if t.missed <= MISS_TOLERANCE]
        for j, (x, y) in enumerate(blobs):
            if j not in used:
                tracks.append(Track(x, y))
        k += 1
    cap.release()

    events.sort()
    with open(spec["artifact"]["output"], "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(spec["artifact"]["columns"])
        for t, east, west in events:
            w.writerow([f"{t:.3f}", east, west])
    print(f"counter: {len(events)} crossings "
          f"({sum(e for _, e, _ in events)} east / "
          f"{sum(w for _, _, w in events)} west) -> "
          f"{spec['artifact']['output']}")


if __name__ == "__main__":
    main()
