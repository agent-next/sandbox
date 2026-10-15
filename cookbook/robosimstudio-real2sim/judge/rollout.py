# SPDX-License-Identifier: Apache-2.0
"""Drive a RoboSimStudio towel scene with a given parameter set and record it.

This is the only file that imports robosimstudio. It runs *inside* the sandbox
that has the pinned RSS installed, once per (params, track) pair, and prints one
JSON object on stdout: the per-frame particle positions and the health checks
G5 needs. The task measures (G4) are recomputed from those positions by
`judge/grade.py`, using RSS's own definitions.

The scene is the upstream `01_cloth/00_towel.py` towel (bench_0728, a 0.35 m
terry sheet, `TERRY_TOWELLING`) with the material replaced by the artifact's
parameters. The arm track is written straight into `control.joint_target_q`, one
row per control step — no IK, no viser, no browser, so the rollout is
deterministic.

    python3 rollout.py --params params.json --track tracks/train.json \
        --out rollout.npz [--device cuda:0]
"""

import argparse
import json
import os
import time

os.environ.setdefault("ROBOSIMSTUDIO_RENDERER", "tiled")
os.environ.setdefault("MUJOCO_GL", "disabled")

import numpy as np  # noqa: E402

# The scene, copied from examples/01_cloth/00_towel.py.
CELL = "bench_0728"
SIZE = 0.35
CELLS = 30
EDGE = -0.20
# The right arm's joints [rad] from 00_towel.py: tool centre over the near edge.
OVER_EDGE = (0.274, 2.114, 2.003, -1.459, 0.0, 0.274)


def build_scene(rss, params, size=SIZE, cells=CELLS):
    """The towel scene with the artifact's material and scene constraints.

    `constraint` carries the scene's own explicit entries, the ones the paper's
    Sec. 3 calls out: the coupler and the contact model. They are choices, not
    numbers, and the paper's Sec. 4.3 argument is about exactly this kind of
    entry -- a constraint that is fixed in simulation but free in reality. On
    this towel, `full_surface_contact: false` is that constraint: the pads can
    push the sheet but not pinch it, which is the upstream example's own
    documented default, and the fold does not happen.
    """
    from robosimstudio.robots.registry import get_embodiment

    changes = {}
    for group in ("cloth", "contact"):
        for key, value in (params.get(group) or {}).items():
            changes[key] = float(value)
    if params.get("shell"):
        changes["shell"] = params["shell"]
    material = rss.replace(rss.materials.TERRY_TOWELLING, **changes)

    constraint = params.get("constraint") or {}
    coupling = str(constraint.get("coupling", "one_way"))
    full_surface = bool(constraint.get("full_surface_contact", True))
    physics = rss.replace(
        rss.GENERIC,
        coupling=rss.coupler(coupling),
        collision=rss.CollisionSpec(full_surface_contact=full_surface),
    )
    yam = get_embodiment("yam_bimanual")
    left, right = yam.arms
    yam = rss.replace(yam, arms=(left, rss.replace(right, home_q=OVER_EDGE)))

    scene = rss.Scene(cell=CELL, physics=physics, name="cloth")
    scene.add(rss.robot(yam))
    scene.add(
        rss.sheet(
            name="towel",
            size=(size, size),
            cells=(cells, cells),
            at=(-size / 2, EDGE, 0.02),
            material=material,
        )
    )
    return scene


def run(params_path, track_path, out_path, device, record_dir=""):
    import robosimstudio as rss
    from robosimstudio.sim.scene import Scene

    with open(params_path) as fh:
        params = json.load(fh)
    with open(track_path) as fh:
        track = json.load(fh)
    rows = np.asarray(track["joint_targets"], dtype=np.float32)
    settle = int(track.get("settle_steps", 40))
    sample_every = max(1, int(track.get("sample_every", 1)))
    size = float(track.get("size", SIZE))
    cells = int(track.get("cells", CELLS))

    original_build = Scene.build

    def build(self, **kwargs):
        kwargs["device"] = device
        kwargs["use_cuda_graph"] = False
        return original_build(self, **kwargs)

    Scene.build = build
    rss.view = lambda sim, **kw: None  # the studio is the only GUI element

    report = {"params": params_path, "track": track_path, "device": device}
    t0 = time.monotonic()
    sim = build_scene(rss, params, size=size, cells=cells).build(control_mode="joint_position")
    report["build_s"] = round(time.monotonic() - t0, 3)

    ctrl = sim.pipeline.control
    width = int(np.asarray(ctrl.joint_target_q.numpy()).shape[0])
    if rows.shape[1] != width:
        raise SystemExit(f"track has {rows.shape[1]} joints, scene has {width}")

    # Settle the sheet first; its positions are the "settled" reference the fold
    # measures are ratios against, exactly as `cloth_fold` defines them.
    sim.run(settle)
    settled = np.asarray(sim["towel"].particle_q, dtype=np.float64)

    frames, health = [], []
    t0 = time.monotonic()
    for i, row in enumerate(rows):
        ctrl.joint_target_q.assign(row)
        sim.run(1)
        if i % sample_every:
            continue
        q = np.asarray(sim["towel"].particle_q, dtype=np.float64)
        frames.append(q)
        health.append({"finite": bool(np.isfinite(q).all()), "max_radius": float(np.abs(q).max())})
    report["step_s"] = round(time.monotonic() - t0, 3)
    report["steps"] = int(rows.shape[0])
    report["steps_per_s"] = round(rows.shape[0] / max(report["step_s"], 1e-9), 3)

    q = np.asarray(frames, dtype=np.float32)
    np.savez_compressed(out_path, q=q, settled=settled.astype(np.float32))

    report["frames"] = int(q.shape[0])
    report["particles"] = int(q.shape[1])
    report["health"] = {
        "finite": all(h["finite"] for h in health),
        "max_radius": max(h["max_radius"] for h in health),
        "min_radius": min(h["max_radius"] for h in health),
    }

    if record_dir:
        try:
            os.makedirs(record_dir, exist_ok=True)
            sim.record(record_dir, 1, every=1)
            report["recorded"] = sorted(os.listdir(record_dir))
        except Exception as exc:
            report["record_error"] = f"{type(exc).__name__}: {exc}"

    print("ROLLOUT " + json.dumps(report))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--params", required=True)
    ap.add_argument("--track", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--record", default="")
    args = ap.parse_args()
    run(args.params, args.track, args.out, args.device, args.record)


if __name__ == "__main__":
    main()
