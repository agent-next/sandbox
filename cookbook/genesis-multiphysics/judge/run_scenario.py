#!/usr/bin/env python3
"""Judge runner: build the scenario's scene, simulate it, write samples.

Usage:
    run_scenario.py <scenario.py> --out <sample_prefix.npz> --seed N \
        [--save-frames DIR]

The scenario file defines one dict named SCENARIO (see SPEC.md). This
runner builds the corresponding Genesis scene on the CPU backend, with
gravity initially zero; gravity from the spec is switched on just before
the first frame so the column starts in pure free fall from rest.

Outputs a .npz with:
    pos            (n_samples, n_particles, 3)  sampled positions
    vel            (n_samples, n_particles, 3)  sampled velocities
    sample_frames  (n_samples,)                 frame index of each sample
    n_particles0   scalar int, particle count right after build
    meta           JSON string with wall seconds and spec echo
"""

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np


def load_scenario(path: Path) -> dict:
    spec = importlib.util.spec_from_file_location("artifact_scenario", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "SCENARIO"):
        raise SystemExit(f"{path}: module must define a SCENARIO dict")
    s = mod.SCENARIO
    if not isinstance(s, dict):
        raise SystemExit(f"{path}: SCENARIO must be a dict")
    required = [
        "gravity", "dt", "substeps", "steps", "seed",
        "particle_size", "grid_density", "domain_lower", "domain_upper",
        "column_size", "column_pos", "E", "nu", "rho", "yield_stress",
        "obstacle_size", "obstacle_pos", "friction",
    ]
    missing = [k for k in required if k not in s]
    if missing:
        raise SystemExit(f"{path}: SCENARIO missing keys: {missing}")
    return s


def validate_spec(s: dict) -> None:
    gp = f"sanity: "
    g = float(s["gravity"])
    dt = float(s["dt"]); sub = int(s["substeps"])
    if not (5e-4 <= dt <= 2e-3):
        raise SystemExit(f"{gp}dt {dt} outside [5e-4, 2e-3]")
    if not (1 <= sub <= 10):
        raise SystemExit(f"{gp}substeps {sub} outside [1, 10]")
    if not (dt / sub) <= 5e-4:
        raise SystemExit(f"{gp}dt/substeps = {dt/sub:.3g} > 5e-4 (MPM unstable)")
    steps = int(s["steps"])
    if not (600 <= steps <= 4000):
        raise SystemExit(f"{gp}steps {steps} outside [600, 4000]")
    if steps * dt > 4.0:
        raise SystemExit(f"{gp}steps*dt = {steps*dt:.3g} s > 4 s budget")
    ps = float(s["particle_size"])
    if not (0.008 <= ps <= 0.03):
        raise SystemExit(f"{gp}particle_size {ps} outside [0.008, 0.03]")
    gd = int(s["grid_density"])
    if not (32 <= gd <= 64):
        raise SystemExit(f"{gp}grid_density {gd} outside [32, 64]")
    E = float(s["E"]); nu = float(s["nu"]); rho = float(s["rho"])
    ys = float(s["yield_stress"]); fr = float(s["friction"])
    if not (1e4 <= E <= 1e8):
        raise SystemExit(f"{gp}E {E} outside [1e4, 1e8]")
    if not (0.0 <= nu <= 0.49):
        raise SystemExit(f"{gp}nu {nu} outside [0, 0.49]")
    if not (500 <= rho <= 3000):
        raise SystemExit(f"{gp}rho {rho} outside [500, 3000]")
    if not (100 <= ys <= 1e6):
        raise SystemExit(f"{gp}yield_stress {ys} outside [100, 1e6]")
    if not (0.0 <= fr <= 1.5):
        raise SystemExit(f"{gp}friction {fr} outside [0, 1.5]")
    cs = [float(x) for x in s["column_size"]]
    if not all(0.06 <= x <= 0.5 for x in cs):
        raise SystemExit(f"{gp}column_size {cs} outside [0.06, 0.5]")
    cpos = np.array([float(x) for x in s["column_pos"]])
    osz = np.array([float(x) for x in s["obstacle_size"]], float)
    opos = np.array([float(x) for x in s["obstacle_pos"]], float)
    if not all(0.01 <= x <= 0.6 for x in osz):
        raise SystemExit(f"{gp}obstacle_size {list(osz)} outside [0.01, 0.6]")
    # column bottom must start clear of the obstacle top
    col_bot = cpos[2]
    obs_top = opos[2] + osz[2] / 2
    if col_bot - obs_top < 0.05:
        raise SystemExit(f"{gp}column bottom ({col_bot:.3f}) must start >= 0.05 m "
                         f"above obstacle top ({obs_top:.3f}) so a free-fall window exists")
    # domain must contain column + obstacle + headroom
    lo = np.array([float(x) for x in s["domain_lower"]])
    up = np.array([float(x) for x in s["domain_upper"]])
    for p, sz in ((cpos, np.array(cs)), (opos, osz)):
        x0 = p - sz / 2 - ps; x1 = p + sz / 2 + ps
        if not (np.all(x0 > lo) and np.all(x1 < up)):
            raise SystemExit(f"{gp}domain must fully contain every entity")
    if up[2] < cpos[2] + cs[2] / 2 + cs[2]:
        raise SystemExit(f"{gp}domain top must leave at least one column height of headroom")


def run(scenario_path: Path, out_prefix: Path, seed: int,
        save_frames: Path | None) -> dict:
    s = load_scenario(scenario_path)
    validate_spec(s)
    if seed is not None:
        s = dict(s, seed=seed)

    import genesis as gs  # deferred: import only when we really run

    gs.init(backend=gs.cpu, seed=int(s["seed"]), logging_level="error",
            use_deterministic_algorithms=True)

    dt = float(s["dt"]); sub = int(s["substeps"]); steps = int(s["steps"])

    scene = gs.Scene(
        sim_options=gs.options.SimOptions(
            dt=dt, substeps=sub, gravity=(0.0, 0.0, 0.0)),
        mpm_options=gs.options.MPMOptions(
            lower_bound=[float(x) for x in s["domain_lower"]],
            upper_bound=[float(x) for x in s["domain_upper"]],
            grid_density=int(s["grid_density"]),
            particle_size=float(s["particle_size"]),
        ),
        show_viewer=False,
    )

    scene.add_entity(gs.morphs.Plane())
    scene.add_entity(
        morph=gs.morphs.Box(pos=list(s["obstacle_pos"]),
                            size=list(s["obstacle_size"])),
        material=gs.materials.Rigid(friction=float(s["friction"])),
    )
    column = scene.add_entity(
        morph=gs.morphs.Box(pos=list(s["column_pos"]),
                            size=list(s["column_size"])),
        material=gs.materials.MPM.ElastoPlastic(
            E=float(s["E"]), nu=float(s["nu"]), rho=float(s["rho"]),
            von_mises_yield_stress=float(s["yield_stress"]),
        ),
    )

    if save_frames is not None:
        save_frames.mkdir(parents=True, exist_ok=True)
        cam = scene.add_camera(res=(960, 720), pos=(1.35, 1.35, 0.85),
                               lookat=(s["column_pos"][0], s["column_pos"][1],
                                       0.30), fov=35)
    else:
        cam = None

    t0 = time.monotonic()
    scene.build()
    build_s = time.monotonic() - t0
    n0 = int(column.n_particles)

    # Free-fall window from the spec geometry (same formula as gate 3):
    # sample EVERY frame until the column bottom reaches the obstacle top
    # so the ballistic fit has >= 20 samples, then coarsen to ~48 more.
    g_abs = abs(float(s["gravity"]))
    obs_top = float(s["obstacle_pos"][2]) + float(s["obstacle_size"][2]) / 2
    t_fall = (float("inf") if g_abs < 1e-12 else
              float(np.sqrt(2 * max(0.0, float(s["column_pos"][2]) - obs_top)
                            / g_abs)))
    late_every = max(1, steps // 48)
    pos_s, vel_s, fr_s = [], [], []
    t1 = time.monotonic()
    for f in range(steps):
        if f == 0:
            scene.sim.set_gravity(np.array([0.0, 0.0, float(s["gravity"])]))
        scene.step()
        if f * dt <= t_fall or f % late_every == 0 or f == steps - 1:
            pos_s.append(column.get_particles_pos().cpu().numpy().copy())
            vel_s.append(column.get_particles_vel().cpu().numpy().copy())
            fr_s.append(f)
        if cam is not None and f in (0, steps // 6, steps // 3, steps // 2,
                                     2 * steps // 3, steps - 1):
            try:
                rgba, *_ = cam.render()
                import matplotlib
                matplotlib.use("Agg")
                import matplotlib.pyplot as plt
                plt.imsave(str(save_frames / f"frame_{f:05d}.png"), rgba)
            except Exception as e:  # rendering is never a gate
                print(f"[run] frame render failed at {f}: {e}", file=sys.stderr)
    run_s = time.monotonic() - t1

    meta = {"wall_build_s": round(build_s, 3), "wall_run_s": round(run_s, 3),
            "late_sample_every": late_every, "dt": dt, "substeps": sub,
            "steps": steps, "seed": int(s["seed"]),
            "scenario": str(scenario_path)}
    out = Path(str(out_prefix))
    np.savez(out, pos=np.stack(pos_s), vel=np.stack(vel_s),
             sample_frames=np.array(fr_s), n_particles0=n0,
             meta=json.dumps(meta), spec=json.dumps({k: v for k, v in s.items()
                                                     if k != "seed"}))
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", type=Path)
    ap.add_argument("--out", type=Path, required=True,
                    help="output .npz path (print sample arrays)")
    ap.add_argument("--seed", type=int, default=None,
                    help="override SCENARIO['seed']")
    ap.add_argument("--save-frames", type=Path, default=None)
    args = ap.parse_args()
    meta = run(args.scenario, args.out, args.seed, args.save_frames)
    print(json.dumps(meta))


if __name__ == "__main__":
    main()
