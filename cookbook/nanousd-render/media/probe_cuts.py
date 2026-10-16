#!/usr/bin/env python3
"""Render only the slot-boundary frames and measure the real ffmpeg scene
score across each cut, so a cut the gate will not count costs a handful of
renders instead of a full 32 s re-render.

The probe NEVER materialises a whole slot: it takes the last two frames of
one slot and the first two of the next, so the PIL render cache never holds
more than a few full-frame images.

Usage: PREFIX/venv/bin/python probe_cuts.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np                                   # noqa: E402
from PIL import Image                                # noqa: E402

import build_video as bv                             # noqa: E402

T, FPS = bv.T, bv.FPS
W, H = bv.W, bv.H


def pick(gen, n, first=2, last=2):
    """First `first` and last `last` frames of a generator, without ever
    holding the whole slot in memory."""
    head, tail = [], []
    i = 0
    for img in gen:
        if i < first:
            head.append(img)
        tail.append(img)
        if len(tail) > last:
            tail.pop(0)
        i += 1
        if i >= n:
            break
    return head, tail


def main() -> int:
    verdict = json.load(open(os.path.join(bv.BUILD, "verdict.json")))
    selftest = json.load(open(os.path.join(bv.BUILD, "selftest.json")))
    meshes, cam, cam_attribs = bv.load_scene_dump()
    scene_text = open(bv.SCENE, encoding="utf-8").read()
    setup_lines = [ln.rstrip() for ln in open(
        os.path.join(HERE, "setup_progress.txt"), encoding="utf-8")
        if ln.strip()]
    selftest_lines = [
        "[selftest] grading known-bad mutants",
        * [f'[selftest]   {m["name"]:<20} {m["verdict"]:<8} (failed gates: '
           f'{m["gates_failed"]})' for m in selftest["mutants"]],
        f'[selftest] mutants killed      : {selftest["mutants_killed"]} / '
        f'{selftest["mutants_total"]}',
        f'[selftest] kill rate           : {selftest["kill_rate"]}',
        "[selftest] selftest: PASS",
    ]
    setup_wall_s = float(os.environ.get("DEMO_SETUP_WALL_S", "853"))
    speed_label = f"~{round(setup_wall_s / (T['proof'] - T['term']))}x speed"
    fr = lambda a, b: int(round((b - a) * FPS))

    specs = [
        ("hook", fr(T["hook"], T["input"]),
         lambda: bv.shot_hook(meshes, cam, cam_attribs,
                              fr(T["hook"], T["input"]), verdict)),
        ("input", fr(T["input"], T["orbit"]),
         lambda: bv.shot_input(meshes, cam, cam_attribs,
                               fr(T["input"], T["orbit"]), verdict,
                               scene_text)),
        ("orbit", fr(T["orbit"], T["rects"]),
         lambda: bv.shot_orbit(meshes, cam_attribs, 0,
                               fr(T["orbit"], T["rects"]), with_rects=False,
                               light_to_dark=False)),
        ("rects", fr(T["rects"], T["term"]),
         lambda: bv.shot_orbit(meshes, cam_attribs, fr(T["orbit"], T["rects"]),
                               fr(T["rects"], T["term"]), with_rects=True,
                               light_to_dark=False)),
        ("terminal", fr(T["term"], T["proof"]),
         lambda: bv.shot_terminal(fr(T["term"], T["proof"]), setup_lines,
                                  selftest_lines, speed_label)),
        ("proof", fr(T["proof"], T["end"]),
         lambda: bv.shot_proof(fr(T["proof"], T["end"]), verdict, selftest,
                               meshes, cam_attribs)),
        ("end", fr(T["end"], T["stop"]),
         lambda: bv.shot_end(fr(T["end"], T["stop"]),
                             "python3 cookbook/nanousd-render/run.py")),
    ]

    frames = []
    for name, n, make in specs:
        head, tail = pick(make(), n)
        print(f"[probe] {name}: {n} frames, boundary frames "
              f"{len(head)} head / {len(tail)} tail", flush=True)
        frames.append((name, head, tail))

    # boundary clip: tail of slot i, then head of slot i+1
    tmpdir = tempfile.mkdtemp(prefix="probe-cuts-")
    raw = os.path.join(tmpdir, "b.raw")
    with open(raw, "wb") as fh:
        for idx, (name, head, tail) in enumerate(frames):
            for img in tail:
                if img.size != (W, H):
                    img = img.resize((W, H), Image.LANCZOS)
                fh.write(img.tobytes())
            if idx + 1 < len(frames):
                for img in frames[idx + 1][1]:
                    if img.size != (W, H):
                        img = img.resize((W, H), Image.LANCZOS)
                    fh.write(img.tobytes())

    mp4 = os.path.join(tmpdir, "b.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo",
                    "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", "30",
                    "-i", raw, "-c:v", "libx264", "-crf", "0", "-preset",
                    "veryfast", "-pix_fmt", "yuv420p", mp4], check=True)

    p = subprocess.run(["ffmpeg", "-v", "info", "-i", mp4,
                        "-vf", "select='gt(scene,0.0001)',showinfo",
                        "-f", "null", "-"], capture_output=True, text=True)
    text = p.stdout + p.stderr
    scores = {int(m.group(1)): float(m.group(2))
              for m in re.finditer(r"n:\s*(\d+).*?scene_score:([\d.]+)", text)}
    pos = 0
    ok = 0
    for idx in range(len(frames) - 1):
        cut = pos + 2            # (tail[1] of slot i) -> (head[0] of slot i+1)
        s = scores.get(cut)
        hit = s is not None and s > 0.3
        ok += hit
        print(f"  {frames[idx][0]:9s} -> {frames[idx+1][0]:9s}  "
              f"cut at clip frame {cut}: score={s} "
              f"{'CUT' if hit else 'no cut'}", flush=True)
        pos += 2 + 2
    print(f"[probe] {ok}/{len(frames) - 1} cuts register above 0.3 "
          f"(need the real cut rate >= 0.8/10s over the full video)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
