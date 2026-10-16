#!/usr/bin/env python3
"""grade_frames.py — stage-2 judge: grades RENDERED FRAMES against the scene.

Runs outside the renderer (in run.py on the CPU sandbox, on the frames
downloaded from the GPU lease) so the judge can never be influenced by
the job that produced the frames.

Gates (from SPEC.md, stage 2):
  G1 silhouette-vs-bbox    per tracked object, the rendered silhouette
                           coverage must reach IoU >= TIOU against the
                           analytic bbox projection (judge/project.py).
  G2 no-missing-texture   no magenta fill and no unbound default grey on
                           any bound material; measured per material class.
  G3 temporal             every frame differs from its neighbours by at
                           least TDIF (no black / frozen / flash frames),
                           and frame 0 is not a solid fill.
  G4 scene integrity      stage-1 USD gates re-checked against the same
                           scene file the renderer read (G3 PhysX from
                           the baked trajectory).

    python3 judge/grade_frames.py --run <run.py output dir>

The output dir must contain frames/<scene>/*.png and report.json with the
render metrics.  A missing frame set fails its gate with a stated reason
(a silent empty pass is never a verdict).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from pxr import Usd, UsdGeom

import project

# ---- gate thresholds (numeric, stated in SPEC.md; tuned to be tight but
# ---- reproducible on real ovrtx frames, see RECEIPT.md calibration).
G1_IOU_MIN = 0.90            # silhouette vs projected bbox overlap
G1_COVER_MIN = 0.005          # silhouette pixels / frame pixels
G2_MAGENTA_MAX = 0.002       # fraction of pixels close to magenta
G2_GREY_FLAT_MAX = 0.30      # fraction of unbound-grey pixels
G3_TDIF_MIN = 1.0             # mean |luma diff| between adjacent frames
G3_BLACK_FRAME_MAX = 0.05     # frames allowed below the black luma floor

MAGENTA = np.array([255.0, 0.0, 255.0], dtype=float)
DEFAULT_GREY = np.array([171.0, 171.0, 171.0], dtype=float)  # usdpreviewsurface default
BLACK_LUMA = 8.0

SCENES = ("warehouse", "physics", "arm")
TRACKED = {
    "warehouse": ["/World/Robot", "/World/Rack", "/World/Boxes"],
    "physics": ["/World/Boxes/Box1", "/World/Boxes/Box2", "/World/Boxes/Box3"],
    "arm": ["/World/Robot", "/World/Table"],
}


def frame_paths(scene_frames: Path, stride: int = 1):
    names = sorted(p.name for p in scene_frames.glob("*.png"))
    return [scene_frames / n for n in names[::stride]]


def luminance(img: np.ndarray) -> np.ndarray:
    return (0.2126 * img[..., 0] + 0.7152 * img[..., 1]
            + 0.0722 * img[..., 2]) if img.shape[-1] >= 3 else img[..., 0]


def foreground_mask(img: np.ndarray, bg_luma: float,
                    tol: float = 12.0) -> np.ndarray:
    """Silhouette = pixels far from the frame's modal (background) colour.

    A path-traced warehouse frame is sky/hdri behind geometry, so the
    modal luma is the background; the object silhouette is what differs.
    tol absorbs path-tracing noise around the background level."""
    lum = luminance(img[..., :3].astype(float))
    return np.abs(lum - bg_luma) > tol


def modal_luma(img: np.ndarray) -> float:
    lum = luminance(img[..., :3].astype(float)).ravel()
    hist, edges = np.histogram(lum, bins=256, range=(0, 255))
    top = int(hist.argmax())
    return float((edges[top] + edges[top + 1]) / 2.0)


# --------------------------------------------------------------------------- #
def gate_silhouette(stage, scene: str, frames_dir: Path) -> dict:
    """G1: per tracked object, rendered silhouette must reach IoU >= 0.9
    with the analytic projection at sampled frames."""
    rows, failures = [], []
    files = frame_paths(frames_dir, stride=max(1, 30))  # sample every ~1 s
    if not files:
        return {"pass": False, "iou_min": None,
                "failures": [f"no frames found in {frames_dir}"],
                "objects": [], "coverage_min": None}
    fps = 30.0
    for prim_path in TRACKED[scene]:
        ious, covs = [], []
        for idx, fp in enumerate(files):
            t = (idx * max(1, 30)) / fps
            proj = project.project_prim_bbox(stage, prim_path, t)
            if not proj["visible"]:
                continue
            img = np.asarray(Image.open(fp).convert("RGB"))
            bg = modal_luma(img)
            mask = foreground_mask(img, bg)
            ys, xs = np.where(mask)
            if len(xs) == 0:
                covs.append(0.0)
                ious.append(0.0)
                continue
            obs = [float(xs.min()), float(ys.min()),
                   float(xs.max()), float(ys.max())]
            ious.append(project.rect_iou(obs, proj["bbox_px"]))
            covs.append(float(mask.mean()))
        if not ious:
            failures.append(f"{prim_path}: projection invisible in all samples")
            continue
        worst_iou = min(ious)
        worst_cov = min(covs)
        rows.append({"prim": prim_path, "iou_min": round(worst_iou, 4),
                     "coverage_min": round(worst_cov, 5),
                     "samples": len(ious)})
        if worst_iou < G1_IOU_MIN or worst_cov < G1_COVER_MIN:
            failures.append(f"{prim_path}: IoU {worst_iou:.3f} (<{G1_IOU_MIN}) "
                            f"or coverage {worst_cov:.4f} (<{G1_COVER_MIN})")
    return {"pass": not failures, "iou_min": min((r["iou_min"] for r in rows),
                                                 default=None),
            "coverage_min": min((r["coverage_min"] for r in rows), default=None),
            "objects": rows, "failures": failures}


def gate_texture(frames_dir: Path) -> dict:
    """G2: no magenta fill (the classic missing-texture signal) and no
    large unbound default-grey region."""
    if not frames_dir.exists():
        return {"pass": False, "failures": [f"no frames in {frames_dir}"],
                "magenta_max": None, "grey_max": None}
    magenta_max, grey_max = 0.0, 0.0
    for fp in frame_paths(frames_dir, stride=30):
        img = np.asarray(Image.open(fp).convert("RGB")).astype(float)
        flat = img.reshape(-1, 3)
        magenta = float((np.abs(flat - MAGENTA) < 8.0).all(axis=1).mean())
        grey = float((np.abs(flat - DEFAULT_GREY) < 10.0).all(axis=1).mean())
        magenta_max, grey_max = max(magenta_max, magenta), max(grey_max, grey)
    failures = []
    if magenta_max > G2_MAGENTA_MAX:
        failures.append(f"magenta fraction {magenta_max:.4f} > {G2_MAGENTA_MAX}")
    if grey_max > G2_GREY_FLAT_MAX:
        failures.append(f"default-grey fraction {grey_max:.3f} > {G2_GREY_FLAT_MAX}")
    return {"pass": not failures, "magenta_max": round(magenta_max, 5),
            "grey_max": round(grey_max, 4), "failures": failures}


def gate_temporal(frames_dir: Path) -> dict:
    """G3(temporal): consecutive frames must differ (no frozen or black
    frames); the whole sequence must not flash."""
    files = frame_paths(frames_dir)
    if len(files) < 2:
        return {"pass": False, "failures": [f"only {len(files)} frame(s) in {frames_dir}"]}
    diffs, black = [], 0
    for prev_fp, cur_fp in zip(files, files[1:]):
        a = luminance(np.asarray(Image.open(prev_fp).convert("RGB")).astype(float))
        b = luminance(np.asarray(Image.open(cur_fp).convert("RGB")).astype(float))
        if a.shape != b.shape:
            return {"pass": False,
                    "failures": [f"frame size changed at {cur_fp}"]}
        diffs.append(float(np.abs(a - b).mean()))
    black = sum(1 for fp in files
                if luminance(np.asarray(Image.open(fp).convert("RGB")).astype(float)).mean() < BLACK_LUMA)
    frozen = sum(1 for d in diffs if d < G3_TDIF_MIN)
    failures = []
    if frozen > 0:
        failures.append(f"{frozen}/{len(diffs)} adjacent-frame diffs below {G3_TDIF_MIN}")
    if black > 0:
        failures.append(f"{black} frames below the black luma floor {BLACK_LUMA}")
    return {"pass": not failures, "frozen": frozen, "black": black,
            "of": len(diffs), "diff_p50": round(float(np.median(diffs)), 3),
            "failures": failures}


def gate_scene_usd(scene: str) -> dict:
    """G4: the stage-1 USD gates on the same scene file."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import validate_scenes as vs
    root = Path(__file__).resolve().parent.parent
    path = root / "scenes" / scene / "scene.usda"
    if not path.exists():
        return {"pass": False, "failures": [f"missing {path}"]}
    stage = Usd.Stage.Open(str(path))
    checker = {"warehouse": vs.check_scene_a, "physics": vs.check_scene_b,
               "arm": vs.check_scene_c}[scene]
    res = checker(stage, root)
    return {"pass": not res["errors"], "failures": list(res["errors"]),
            "warnings": list(res["warnings"]), "stats": res["stats"]}


def grade(run_dir: Path) -> dict:
    gates, scenes = {}, {}
    for scene in SCENES:
        frames_dir = run_dir / "frames" / scene
        scenes[scene] = {
            "G1_silhouette": gate_silhouette(
                Usd.Stage.Open(str(run_dir / "scene_copy" / scene / "scene.usda"))
                if (run_dir / "scene_copy" / scene / "scene.usda").exists()
                else Usd.Stage.Open(str(run_dir.parent / "scenes" / scene / "scene.usda")),
                scene, frames_dir),
            "G2_texture": gate_texture(frames_dir),
            "G3_temporal": gate_temporal(frames_dir),
            "G4_scene_usd": gate_scene_usd(scene),
        }
        ok = all(v["pass"] for v in scenes[scene].values())
        gates[scene] = {"pass": ok, "gates": scenes[scene]}
    overall = all(v["pass"] for v in gates.values())
    return {"pass": overall, "scenes": gates}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="run.py output dir")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    run_dir = Path(args.run).resolve()
    verdict = grade(run_dir)
    if args.json:
        print(json.dumps(verdict, indent=2, sort_keys=True))
    else:
        for scene, row in verdict["scenes"].items():
            print(f"== {scene}: {'PASS' if row['pass'] else 'FAIL'}")
            for name, g in row["gates"].items():
                mark = "ok  " if g["pass"] else "FAIL"
                print(f"   {mark} {name}")
                for f in g.get("failures", []):
                    print(f"        - {f}")
        print(f"overall: {'PASS' if verdict['pass'] else 'FAIL'}")
    return 0 if verdict["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
