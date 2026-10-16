#!/usr/bin/env python3
"""mutate_frames.py — generate known-bad RENDERED FRAME sets for the stage-2
judge selftest.

The stage-2 judge (grade_frames.py) grades 1920x1080 PNG frames.  It must
kill at least 5 distinct renderer failures.  This module synthesises a
plausible "good" hero frame for each tracked scene from the analytic
projection (judge/project.py) and then applies one single renderer defect
per mutant, so the only thing the judge can blame for the failure is the
mutant's defect.

Mutants (each kills >= 1 gate; see the table in RECEIPT.md):
  1. missing_texture  — magenta fill over the tracked object's bbox
  2. untextured_grey  — usdpreviewsurface default grey over the object
  3. black_frame      — a single all-black frame mid-sequence (temporal)
  4. frozen_bounce    — the same frame repeated (temporal, G3 frozen)
  5. camera_off       — object drawn far off its projected bbox (G1)
  6. underexposed     — dropped light: whole frame near black (G3 black)
  7. wrong_units      — object rendered at 0.01x scale (G1 coverage)

Usage:
  python3 judge/mutate_frames.py --out <dir>           # writes good/ + mutants/
  python3 judge/mutate_frames.py --selftest            # runs grade_frames on
                                                       #   good and each mutant
Every mutant is a SINGLE edit of the good frames so the judge's per-gate
report names the defect.  Standard library + numpy/PIL/pxr.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from pxr import Usd

import project

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SCENES = ("warehouse", "physics", "arm")
TRACKED = {
    "warehouse": ["/World/Robot", "/World/Rack", "/World/Boxes"],
    "physics": ["/World/Boxes/Box1", "/World/Boxes/Box2", "/World/Boxes/Box3"],
    "arm": ["/World/Robot", "/World/Table"],
}
W, H = 1920, 1080

# palette: sky, a warm floor, the object's plastic blue
SKY = (150, 170, 200)
FLOOR = (120, 95, 80)
OBJECT = (60, 90, 160)
MAGENTA = (255, 0, 255)
DEFAULT_GREY = (171, 171, 171)


def projected_boxes(stage: Usd.Stage, scene: str, t: float) -> dict:
    """{prim_path: [x0, y0, x1, y1]} for tracked prims at time t (s)."""
    out = {}
    for prim in TRACKED[scene]:
        pr = project.project_prim_bbox(stage, prim, t)
        if pr["visible"]:
            out[prim] = pr["bbox_px"]
    return out


def fill_box(img: np.ndarray, box, color, margin: int = 0) -> np.ndarray:
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    x0 -= margin; y0 -= margin; x1 += margin; y1 += margin
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)
    img[y0:y1, x0:x1] = color
    return img


def good_frames(stage: Usd.Stage, scene: str, n: int = 8) -> np.ndarray:
    """Synthesise a plausible Good frame for the scene at n evenly spaced
    times: sky + floor + a shaded object blob at its projected bbox."""
    img = np.zeros((H, W, 3), dtype=np.uint8)
    img[...] = SKY
    img[int(H * 0.6):H, :] = FLOOR
    boxes = projected_boxes(stage, scene, 0.0)
    for prim, box in boxes.items():
        # the object: a shaded blob (top-lit brighter than bottom) bounded to
        # the frame so the gradient never exceeds the slice height
        x0, y0 = max(0, int(box[0])), max(0, int(box[1]))
        x1, y1 = min(W, int(box[2])), min(H, int(box[3]))
        if y1 <= y0 or x1 <= x0:
            continue
        grad = np.linspace(1.0, 0.5, y1 - y0)[:, None]
        for c in range(3):
            img[y0:y1, x0:x1, c] = (OBJECT[c] * grad).astype(np.uint8)
    return img


def write_frames(img: np.ndarray, scene: str, n: int, outdir: Path,
                 suffix: str = "") -> None:
    d = outdir / "frames" / f"{scene}{suffix}"
    d.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        Image.fromarray(img).save(d / f"{i:04d}.png")


def gen_mutants(base: Path) -> dict:
    """Write good/ + mutants/<name>/ frame sets.  Returns {name: gate_killed}."""
    results = {}
    cached = {}
    good_cells = None
    for scene in SCENES:
        stage = Usd.Stage.Open(str(ROOT / "scenes" / scene / "scene.usda"))
        cached[scene] = stage
        img = good_frames(stage, scene, n=8)
        write_frames(img, scene, 8, base / "good")
        good_cells = img

    scene_box = {}
    for scene in SCENES:
        stage = Usd.Stage.Open(str(ROOT / "scenes" / scene / "scene.usda"))
        b = projected_boxes(stage, scene, 0.0)
        scene_box[scene] = b

    # 1. magenta fill over every tracked object
    for scene in SCENES:
        d = base / "mutants" / "missing_texture" / "frames" / scene
        d.mkdir(parents=True, exist_ok=True)
        img = good_frames(cached[scene], scene, 8)
        for box in scene_box[scene].values():
            fill_box(img, box, MAGENTA)
        for i in range(8):
            Image.fromarray(img).save(d / f"{i:04d}.png")

    # 2. default unbound grey over the object
    for scene in SCENES:
        d = base / "mutants" / "untextured_grey" / "frames" / scene
        d.mkdir(parents=True, exist_ok=True)
        img = good_frames(cached[scene], scene, 8)
        for box in scene_box[scene].values():
            fill_box(img, box, DEFAULT_GREY)
        for i in range(8):
            Image.fromarray(img).save(d / f"{i:04d}.png")

    # 3. one mid-sequence all-black frame
    for scene in SCENES:
        d = base / "mutants" / "black_frame" / "frames" / scene
        d.mkdir(parents=True, exist_ok=True)
        img = good_frames(cached[scene], scene, 8)
        for i in range(8):
            frame = img if i != 4 else np.zeros((H, W, 3), dtype=np.uint8)
            Image.fromarray(frame).save(d / f"{i:04d}.png")

    # 4. frozen: frames 4..7 identical to frame 3
    for scene in SCENES:
        d = base / "mutants" / "frozen" / "frames" / scene
        d.mkdir(parents=True, exist_ok=True)
        img = good_frames(cached[scene], scene, 8)
        for i in range(8):
            frame = img if i < 4 else np.asarray(good_cells[3])
            Image.fromarray(frame).save(d / f"{i:04d}.png")

    # 5. object drawn off-target (shifted 300 px right) -> G1 IoU crash
    for scene in SCENES:
        d = base / "mutants" / "camera_off" / "frames" / scene
        d.mkdir(parents=True, exist_ok=True)
        img = good_frames(cached[scene], scene, 8)
        for box in scene_box[scene].values():
            shifted = [box[0] + 300, box[1], box[2] + 300, box[3]]
            fill_box(img, box, SKY)          # erase old
            fill_box(img, shifted, OBJECT)   # draw off-target
        for i in range(8):
            Image.fromarray(img).save(d / f"{i:04d}.png")

    # 6. underexposed: everything near-black (dropped light)
    for scene in SCENES:
        d = base / "mutants" / "underexposed" / "frames" / scene
        d.mkdir(parents=True, exist_ok=True)
        img = (good_frames(cached[scene], scene, 8) * 0.05).astype(np.uint8)
        for i in range(8):
            Image.fromarray(img).save(d / f"{i:04d}.png")

    # 7. wrong_units: object at 1% scale (tiny blob) -> G1 coverage < 0.5%
    for scene in SCENES:
        d = base / "mutants" / "wrong_units" / "frames" / scene
        d.mkdir(parents=True, exist_ok=True)
        img = good_frames(cached[scene], scene, 8)
        img[int(H * 0.6):H, :] = FLOOR
        for box in scene_box[scene].values():
            cx = (box[0]+box[2])/2; cy = (box[1]+box[3])/2
            s = 0.01 * (box[2]-box[0])
            fill_box(img, [cx-s, cy-s, cx+s, cy+s], OBJECT)
        for i in range(8):
            Image.fromarray(img).save(d / f"{i:04d}.png")

    results = {
        "missing_texture": "G2", "untextured_grey": "G2",
        "black_frame": "G3", "frozen": "G3", "camera_off": "G1",
        "underexposed": "G3", "wrong_units": "G1",
    }
    return results


def grade(run_dir: Path) -> dict:
    from grade_frames import grade
    return grade(run_dir)


def run_selftest(base: Path) -> int:
    """Run grade_frames on good/ and every mutant; print a kill table."""
    good = base / "good"
    verdict = grade(good)
    print(f"good frames: {'PASS' if verdict['pass'] else 'FAIL'} "
          f"(must be PASS)", flush=True)
    good_pass = verdict["pass"]

    killed = {}
    for mutant_dir in sorted((base / "mutants").iterdir()) if (base / "mutants").exists() else []:
        if not mutant_dir.is_dir():
            continue
        v = grade(mutant_dir)
        killed[mutant_dir.name] = not v["pass"]
        gate = "?"
        reasons = {}
        for sc in SCENES:
            for gname, g in v["scenes"][sc]["gates"].items():
                if not g["pass"]:
                    reasons.setdefault(gname, 0)
                    reasons[gname] += 1
        gate = ",".join(sorted(reasons))
        print(f"  {mutant_dir.name}: {'KILLED' if not v['pass'] else 'SURVIVED'} "
              f"({gate})", flush=True)
    n_killed = sum(1 for k in killed.values() if k)
    n_total = len(killed)
    print(f"mutants killed: {n_killed}/{n_total}", flush=True)
    return 0 if (good_pass and n_killed >= 5 and n_killed == n_total) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "frames_mutants"))
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    base = Path(args.out).resolve()
    if not args.selftest:
        if base.exists():
            shutil.rmtree(base)
        gen_mutants(base)
        print(f"wrote mutants under {base}", flush=True)
        return 0
    if not base.exists():
        gen_mutants(base)
    return run_selftest(base)


if __name__ == "__main__":
    sys.exit(main())