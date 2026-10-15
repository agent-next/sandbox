#!/usr/bin/env python3
"""Deterministic synthetic pedestrian scene for the people-counter-cv demo.

Judge-internal: the artifact under test never sees this file. Renders a
grayscale overhead clip of a walkway (static textured floor, slow global
illumination drift) with scripted pedestrians, decoys that turn back,
people that walk in and stand around, and two wide trolleys that must not
be counted. Because every trajectory is piecewise linear, the ground-truth
tripwire crossings are known analytically - that is the demo's acceptance
oracle, not any measurement of the pixels.

Usage (regenerate a clip + truth for inspection):
    python3 gen_scene.py <spec.json> <out_video.avi> <truth.json> [--seed N]
"""

import argparse
import json
import math
import random
import sys

import cv2
import numpy as np

MARGIN_PX = 30          # actors spawn/exit this far outside the frame
MIN_EVENT_GAP_S = 1.4   # truth events are pairwise at least this far apart
LANE_YS = [62, 102, 142, 182, 222, 262, 302, 342]   # lanes 0-4: crossers
SPECIAL_LANES = {"double": 5, "decoy_w": 6, "decoy_e": 7}
VEHICLE_Y = 28          # above lane 0, clear of every pedestrian extent


def _visible_window(actor, width, dur=None):
    """(enter, leave) times when the body enters/exits the frame."""
    ext = actor["body_w"] / 2 + 2
    t0, x0, v = actor["segments"][0]
    if v == 0:
        t_in = t0
    elif v > 0:
        t_in = t0 + (-ext - x0) / v
    else:
        t_in = t0 + (width + ext - x0) / v
    t1, x1, v1 = actor["segments"][-1]
    if v1 == 0:
        # a stopped actor never leaves: the window runs to the clip end
        t_out = dur if dur is not None else t1
    elif v1 > 0:
        t_out = t1 + (width + ext - x1) / v1
    else:
        t_out = t1 + (-ext - x1) / v1
    return t_in, t_out


def _x_at(actor, t):
    segs = actor["segments"]
    if t < segs[0][0]:
        return segs[0][1] + segs[0][2] * (t - segs[0][0])
    for (t0, x0, v), (t1, _, _) in zip(segs, segs[1:]):
        if t0 <= t < t1:
            return x0 + v * (t - t0)
    t0, x0, v = segs[-1]
    return x0 + v * (t - t0)


def _truth_events(actor, line_x, width):
    """Analytic tripwire crossings of one actor: [(t, +1|-1), ...].

    Each segment is linear, so a crossing exists exactly where the sign of
    x(t) - line_x differs between the segment's start and its end (for the
    open final segment, the end is wherever the actor leaves the frame).
    """
    events = []
    segs = actor["segments"]
    ext = actor["body_w"] / 2 + 2
    for i, (t0, x0, v) in enumerate(segs):
        if v == 0:
            continue
        if i + 1 < len(segs):
            x1 = segs[i + 1][1]
        else:
            x1 = width + ext if v > 0 else -ext
        if (x0 - line_x) * (x1 - line_x) < 0:
            t = t0 + (line_x - x0) / v
            if t > 0:
                events.append((t, 1 if v > 0 else -1))
    return events


def _ped(rng, aid, lane_y, segments, intensity=None):
    return {
        "kind": "pedestrian", "id": aid, "lane_y": lane_y,
        "body_w": rng.randint(*PEDESTRIAN_BODY_W),
        "body_h": rng.randint(*PEDESTRIAN_BODY_H),
        "head_r": rng.randint(*PEDESTRIAN_HEAD_R),
        "intensity": intensity if intensity is not None
        else rng.randint(*PEDESTRIAN_INTENSITY),
        "segments": segments,
    }


def build_scene(spec, seed):
    """-> (actors, truth) with analytic crossing events; deterministic."""
    global PEDESTRIAN_BODY_W, PEDESTRIAN_BODY_H, PEDESTRIAN_HEAD_R, \
        PEDESTRIAN_INTENSITY
    ped = spec["pedestrians"]
    PEDESTRIAN_BODY_W = ped["body_w_px"]
    PEDESTRIAN_BODY_H = ped["body_h_px"]
    PEDESTRIAN_HEAD_R = ped["head_radius_px"]
    PEDESTRIAN_INTENSITY = (55, 85)
    w = spec["video"]["width_px"]
    dur = spec["video"]["duration_s"]
    line_x = w * spec["tripwire"]["x_fraction"]
    rng = random.Random(seed * 100003 + 7)

    # -- the double-crosser first: its two crossings are fixed anchors the
    #    crosser schedule must steer around (crosses east, turns beyond
    #    the line, crosses back west on its own lane)
    t_in_d, t_e, t_w, turn_x = 3.0, 9.8, 15.8, 500.0
    v_d = (line_x + MARGIN_PX) / (t_e - t_in_d)
    v_back = -(turn_x - line_x) / (t_w - t_e - (turn_x - line_x) / v_d)
    t_turn = t_in_d + (turn_x + MARGIN_PX) / v_d
    anchors = [t_e, t_w]

    # -- scheduled crossers: 10 eastbound + 8 westbound, on a fixed slot
    #    grid that leaves every event (and every anchor) >= the gap apart
    slots = []
    t = 6.0
    while len(slots) < 18:
        if all(abs(t - a) >= MIN_EVENT_GAP_S + 0.2 for a in anchors):
            slots.append(t)
        t += MIN_EVENT_GAP_S + 0.2
    dirs = [1] * 10 + [-1] * 8
    times = [(s + rng.uniform(0, 0.3), d) for s, d in zip(slots, dirs)]
    if times[-1][0] > 52.0:
        raise RuntimeError("crosser schedule ran past the safe window")

    # -- lane assignment: 5 sequential lanes; each crosser enters once its
    #    lane's previous actor has fully exited, then is pushed forward
    #    until it is MIN_EVENT_GAP_S clear of every event already placed
    #    (anchors included). One deterministic pass, no retries.
    lane_free = [0.0] * 5
    actors, placed = [], list(anchors)
    aid = 0
    for t_cross, d in times:
        v = rng.uniform(*ped["speed_px_per_s"]) * d
        span_in = (line_x + MARGIN_PX) / abs(v)
        t_in = max(t_cross - span_in, min(lane_free) + 0.6)
        t_cross = t_in + span_in
        for _ in range(len(placed) + 2):
            nxt = t_cross
            for e in placed:
                if abs(nxt - e) < MIN_EVENT_GAP_S + 0.05:
                    nxt = max(nxt, e + MIN_EVENT_GAP_S + 0.05)
            if nxt == t_cross:
                break
            t_cross = nxt
        if t_cross > 52.0:
            raise RuntimeError("could not schedule all crossers in time")
        t_in = t_cross - span_in
        t_out = t_cross + (w - line_x + MARGIN_PX) / abs(v)
        for lane in range(5):
            if lane_free[lane] + 0.6 <= t_in:
                break
        else:
            raise RuntimeError("no lane free even after delaying")
        lane_free[lane] = t_out
        placed.append(t_cross)
        x0 = -MARGIN_PX if d > 0 else w + MARGIN_PX
        actors.append(_ped(rng, aid, LANE_YS[lane], [(t_in, x0, v)]))
        aid += 1

    actors.append(_ped(rng, aid, LANE_YS[SPECIAL_LANES["double"]], [
        (t_in_d, -MARGIN_PX, v_d), (t_turn, turn_x, v_back)]))
    aid += 1

    # -- decoys: walk toward the line, pause, turn back; never cross
    turn_a = line_x - rng.uniform(30, 60)
    va = rng.uniform(55, 75)
    t_in = 2.0
    t_turn = t_in + (turn_a + MARGIN_PX) / va
    actors.append(_ped(rng, aid, LANE_YS[SPECIAL_LANES["decoy_w"]], [
        (t_in, -MARGIN_PX, va), (t_turn, turn_a, -va)]))
    aid += 1
    turn_b = line_x + rng.uniform(30, 60)
    vb = -rng.uniform(55, 75)
    t_in = 6.0
    t_turn = t_in + (w + MARGIN_PX - turn_b) / abs(vb)
    actors.append(_ped(rng, aid, LANE_YS[SPECIAL_LANES["decoy_e"]], [
        (t_in, w + MARGIN_PX, vb), (t_turn, turn_b, -vb)]))
    aid += 1

    # -- standers: walk in after the decoys have left, then stand near (but
    #    never across) the line for the rest of the clip
    actors.append(_ped(rng, aid, LANE_YS[SPECIAL_LANES["decoy_w"]], [
        (20.0, -MARGIN_PX, 60.0),
        (20.0 + (line_x - 12 + MARGIN_PX) / 60.0, line_x - 12, 0.0)]))
    aid += 1
    actors.append(_ped(rng, aid, LANE_YS[SPECIAL_LANES["decoy_e"]], [
        (26.0, w + MARGIN_PX, -60.0),
        (26.0 + (w + MARGIN_PX - line_x - 12) / 60.0, line_x + 12, 0.0)]))
    aid += 1

    # -- trolleys: wider than the pedestrian body_w range; excluded from
    #    the truth - a counter that reports them is wrong
    for t_cross, v in ((14.0, 130.0), (33.0, -120.0)):
        t_in = t_cross - (line_x + MARGIN_PX) / abs(v)
        actors.append({"kind": "vehicle", "id": aid, "lane_y": VEHICLE_Y,
                       "body_w": 54, "body_h": 16, "head_r": 0,
                       "intensity": 125,
                       "segments": [(t_in, MARGIN_PX * (1 if v > 0 else -1),
                                     v)]})
        aid += 1

    actors.sort(key=lambda a: (a["kind"] != "pedestrian", a["id"]))

    # -- verify scheduling invariants the CV task depends on
    by_lane = {}
    for a in actors:
        if a["kind"] != "pedestrian":
            continue
        for other in by_lane.get(a["lane_y"], []):
            i0, i1 = _visible_window(a, w, dur)
            j0, j1 = _visible_window(other, w, dur)
            if i0 < j1 and j0 < i1:
                raise RuntimeError(
                    f"lane {a['lane_y']} overlap: actors "
                    f"{other['id']}/{a['id']} windows "
                    f"({j0:.1f},{j1:.1f}) vs ({i0:.1f},{i1:.1f})")
        by_lane.setdefault(a["lane_y"], []).append(a)

    events = []
    for a in actors:
        if a["kind"] == "pedestrian":
            events += _truth_events(a, line_x, w)
    events.sort()
    for (ta, _), (tb, _) in zip(events, events[1:]):
        if tb - ta < MIN_EVENT_GAP_S:
            raise RuntimeError(f"truth events too close: {ta:.2f} {tb:.2f}")
    if not all(0.5 < t < dur - 0.5 for t, _ in events):
        raise RuntimeError("truth event outside the safe window")
    truth = {
        "counts": {"east": sum(1 for _, d in events if d > 0),
                   "west": sum(1 for _, d in events if d < 0)},
        "events": [{"t": round(t, 4), "dir": "east" if d > 0 else "west"}
                   for t, d in events],
        "actors": [{"id": a["id"], "kind": a["kind"],
                    "lane_y": a["lane_y"],
                    "segments": [[round(t, 3), round(x, 2), round(v, 2)]
                                 for t, x, v in a["segments"]]}
                   for a in actors],
    }
    return actors, truth


def render(spec, actors, out_path, truth_overlay=None):
    """Write the MJPG clip; deterministic for a fixed (spec, actors)."""
    vid = spec["video"]
    w, h, fps, dur = (vid["width_px"], vid["height_px"], vid["fps"],
                      vid["duration_s"])
    bg_cfg = spec["background"]
    seed_floor = 99 * 100003 + 7           # floor texture, fixed forever
    floor = np.full((h, w), bg_cfg["intensity"], np.float32)
    floor += np.random.RandomState(seed_floor).uniform(-8, 8,
                                                       (h, w)).astype(np.float32)
    amp = bg_cfg["brightness_ramp_amplitude"]
    # per-frame sensor noise: a fixed pool of 64 frames from one seeded
    # stream, cycled - same marginal statistics as fresh draws per frame
    # at a fraction of the generation cost, and still reproducible
    # frame-for-frame
    pool = np.random.RandomState(seed_floor + 13).normal(
        0, bg_cfg["noise_sigma"], (64, h, w)).astype(np.float32)

    writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"MJPG"),
                             fps, (w, h), True)
    if not writer.isOpened():
        raise RuntimeError(f"cannot open {out_path} for writing")
    n = int(round(dur * fps))
    for k in range(n):
        t = k / fps
        frame = floor + amp * math.sin(2 * math.pi * t / 20.0) + pool[k % 64]
        frame = np.clip(frame, 0, 255).astype(np.uint8)
        for a in actors:
            x = _x_at(a, t)
            ext = a["body_w"] / 2 + 2
            if not -ext <= x <= w + ext:
                continue
            y, bw, bh = a["lane_y"], a["body_w"], a["body_h"]
            if a["kind"] == "vehicle":
                cv2.rectangle(frame, (int(x - bw / 2), int(y - bh / 2)),
                              (int(x + bw / 2), int(y + bh / 2)),
                              a["intensity"], -1)
            else:
                cv2.ellipse(frame, (int(x), int(y)), (bw // 2, bh // 2),
                            0, 0, 360, a["intensity"], -1)
                cv2.circle(frame, (int(x), int(y - bh // 2 - a["head_r"] - 1)),
                           a["head_r"], a["intensity"], -1)
        bgr = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
        writer.write(bgr)
    writer.release()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("out_video")
    ap.add_argument("out_truth")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()
    with open(args.spec) as fh:
        spec = json.load(fh)
    seed = args.seed if args.seed is not None else spec["seed"]
    actors, truth = build_scene(spec, seed)
    render(spec, actors, args.out_video)
    with open(args.out_truth, "w") as fh:
        json.dump(truth, fh, indent=2)
    print(f"gen_scene: seed {seed}: {truth['counts']['east']} east + "
          f"{truth['counts']['west']} west crossings, "
          f"{len(truth['actors'])} actors -> {args.out_video}")


if __name__ == "__main__":
    sys.exit(main())
