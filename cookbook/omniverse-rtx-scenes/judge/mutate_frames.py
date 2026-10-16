#!/usr/bin/env python3
"""mutate_frames.py — known-bad RENDERED FRAME sets for the stage-2 selftest.

The stage-2 judge (grade_frames.py) grades 1920x1080 PNG frames rendered
by the GPU lease.  Its selftest takes the REAL frames a run downloaded
and injects exactly one renderer defect per mutant, so the only thing the
judge can blame for a failure is that defect.  Nothing is synthesised
from scratch: the good set is the run's own output.

Mutants (single edits of the good frames; see the kill table in RECEIPT.md):
  1. missing_texture  — magenta fill over each tracked object's projected
                        bbox (the classic unresolved-texture signal)
  2. untextured_grey  — USD default grey over the same bboxes
  3. black_frame      — one all-black frame mid-sequence
  4. frozen           — the sequence stops at its midpoint (frozen physics)
  5. camera_off       — the whole plate rolls 25 % sideways, so every
                        tracked object leaves its projected bbox
  6. underexposed     — every pixel x0.05 (the key light dropped)
  7. wrong_units      — the object region collapses to 1 % of its bbox
                        (the scene was authored in the wrong unit)

Usage:
  python3 judge/mutate_frames.py --frames <run frames dir> [--out DIR]
  python3 judge/mutate_frames.py --selftest --frames <run frames dir>

Standard library + numpy/PIL/pxr.  Output dirs are gitignored.
"""

from __future__ import annotations

import argparse
import json
import shutil
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
MAGENTA = (255, 0, 255)
DEFAULT_GREY = (171, 171, 171)
N_KEEP = 8          # frames per scene in each frame set


def projected_boxes(stage: Usd.Stage, scene: str, t: float) -> dict:
    """{prim_path: [x0, y0, x1, y1]} for tracked prims at time t (s)."""
    out = {}
    for prim in TRACKED[scene]:
        pr = project.project_prim_bbox(stage, prim, t)
        if pr["visible"]:
            out[prim] = pr["bbox_px"]
    return out


def pick_frames(frames_dir: Path, n: int = N_KEEP) -> list[Path]:
    """A consecutive run (the temporal gate needs adjacent frames),
    falling back to an evenly spaced sample when only strided frames
    were downloaded."""
    files = sorted(frames_dir.glob("*.png"))
    if not files:
        return []
    consecutive = []
    for a, b in zip(files, files[1:]):
        if consecutive and int(b.stem) == int(consecutive[-1].stem) + 1:
            consecutive.append(b)
        elif not consecutive:
            consecutive = [a, b] if int(b.stem) == int(a.stem) + 1 else [a]
        if len(consecutive) >= n:
            return consecutive[:n]
    if len(consecutive) >= n:
        return consecutive[:n]
    step = max(1, len(files) // n)
    return files[::step][:n]


def load_set(frames: list[Path]) -> list[np.ndarray]:
    return [np.asarray(Image.open(fp).convert("RGB")).copy() for fp in frames]


def gen(frames_root: Path, base: Path, stages: dict) -> dict:
    """Write good/ + mutants/<name>/ frame sets from the run's frames."""
    if base.exists():
        shutil.rmtree(base)
    picked, times = {}, {}
    for scene in SCENES:
        sdir = frames_root / scene
        files = pick_frames(sdir) if sdir.exists() else []
        if not files:
            print(f"  [mutate] {scene}: no frames in {sdir}; skipped", flush=True)
            continue
        picked[scene] = files
        times[scene] = [int(f.stem) / 30.0 for f in files]

    for scene, files in picked.items():
        imgs = load_set(files)
        good_dir = base / "good" / "frames" / scene
        good_dir.mkdir(parents=True, exist_ok=True)
        for fp, img in zip(files, imgs):
            Image.fromarray(img).save(good_dir / fp.name)
        boxes = [projected_boxes(stages[scene], scene, t) for t in times[scene]]

        def out_dir(mutant: str) -> Path:
            d = base / "mutants" / mutant / "frames" / scene
            d.mkdir(parents=True, exist_ok=True)
            return d

        def save(mutant: str, seq: list[np.ndarray]) -> None:
            d = out_dir(mutant)
            for fp, img in zip(files, seq):
                Image.fromarray(img).save(d / fp.name)

        # 1. missing texture: magenta over each tracked object's bbox
        seq = []
        for img, bxs in zip(imgs, boxes):
            m = img.copy()
            for box in bxs.values():
                _fill(m, box, MAGENTA)
            seq.append(m)
        save("missing_texture", seq)

        # 2. unbound default grey over the same bboxes
        seq = []
        for img, bxs in zip(imgs, boxes):
            m = img.copy()
            for box in bxs.values():
                _fill(m, box, DEFAULT_GREY)
            seq.append(m)
        save("untextured_grey", seq)

        # 3. one mid-sequence all-black frame
        mid = len(imgs) // 2
        seq = [np.zeros_like(img) if i == mid else img for i, img in enumerate(imgs)]
        save("black_frame", seq)

        # 4. frozen: everything after the midpoint is the midpoint
        seq = [img if i <= mid else imgs[mid] for i, img in enumerate(imgs)]
        save("frozen", seq)

        # 5. camera off target: the plate rolls a quarter width sideways
        shift = W // 4
        seq = [np.roll(img, shift, axis=1) for img in imgs]
        save("camera_off", seq)

        # 6. dropped key light: the whole plate is underexposed
        seq = [(img.astype(np.float32) * 0.05).astype(np.uint8) for img in imgs]
        save("underexposed", seq)

        # 7. wrong units: each object collapses to 1 % of its bbox area
        seq = []
        for img, bxs in zip(imgs, boxes):
            m = img.copy()
            for box in bxs.values():
                _shrink(m, box, 0.01)
            seq.append(m)
        save("wrong_units", seq)

    return {"scenes": sorted(picked),
            "frames_per_scene": {s: len(v) for s, v in picked.items()}}


def _fill(img: np.ndarray, box, color) -> None:
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)
    if x1 > x0 and y1 > y0:
        img[y0:y1, x0:x1] = color


def _shrink(img: np.ndarray, box, frac: float) -> None:
    """Collapse the object to `frac` of its on-screen size: the bbox
    content is replaced by its surrounding plate and a `frac`-scaled
    copy of the original content is pasted at the centre -- what a 100x
    metresPerUnit error looks like on screen."""
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    x0, y0 = max(1, x0), max(1, y0)
    x1, y1 = min(W - 1, x1), min(H - 1, y1)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return
    orig = img[y0:y1, x0:x1].copy()
    # backdrop: the mean colour of the 1-px ring around the box
    ring = np.concatenate([
        img[y0 - 1, x0 - 1:x1 + 1], img[y1, x0 - 1:x1 + 1],
        img[y0:y1, x0 - 1], img[y0:y1, x1]])
    img[y0:y1, x0:x1] = tuple(int(ring[:, c].mean()) for c in range(3))
    h, w = max(2, int((y1 - y0) * frac)), max(2, int((x1 - x0) * frac))
    cy, cx = (y0 + y1) // 2, (x0 + x1) // 2
    small = np.asarray(Image.fromarray(orig).resize((w, h), Image.LANCZOS))
    img[cy - h // 2:cy - h // 2 + h, cx - w // 2:cx - w // 2 + w] = small


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
    ap.add_argument("--frames", default=None,
                    help="run.py frames dir (frames/<scene>/*.png)")
    ap.add_argument("--out", default=str(HERE / "frames_mutants"))
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    base = Path(args.out).resolve()

    frames_root = Path(args.frames).resolve() if args.frames else None
    if frames_root is None or not frames_root.exists():
        print("mutate_frames: --frames <dir> with the run's downloaded "
              "frames is required (the mutants are single edits of REAL "
              "rendered frames; nothing is synthesised)", file=sys.stderr)
        return 2
    stages = {s: Usd.Stage.Open(str(ROOT / "scenes" / s / "scene.usda"))
              for s in SCENES}
    info = gen(frames_root, base, stages)
    print(f"wrote mutants under {base}: {json.dumps(info)}", flush=True)
    if not args.selftest:
        return 0
    return run_selftest(base)


if __name__ == "__main__":
    sys.exit(main())
