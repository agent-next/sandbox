"""Independent, deterministic MuJoCo evaluation, executed on the GPU lease.

Training uses batched MuJoCo-Warp. The judge uses single-threaded CPU MuJoCo
with float64 state, not the trainer's environment or reported metrics.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import sys
import time

os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

EXPECTED_STACK = {"warp-lang": "1.13.0", "mujoco": "3.8.1",
                  "mujoco-warp": "3.8.1", "numpy": "1.26.4",
                  "torch": "2.10.0"}
SIM_DT = 0.002
DECIM = 10
CTRL_DT = SIM_DT * DECIM
MIN_TRUNK_Z = 0.10
FALL_GZ = -0.55
MODEL = os.path.join(os.path.dirname(__file__), "model", "go1_meshless.xml")


def check_stack():
    import torch
    got = {k: importlib.metadata.version(k) for k in EXPECTED_STACK}
    bad = [f"{k} {got[k]} != {v}" for k, v in EXPECTED_STACK.items()
           if got[k] != v]
    got["torch_runtime"] = torch.__version__
    if torch.__version__ != "2.10.0+cu128":
        bad.append(f"torch runtime {torch.__version__} != 2.10.0+cu128")
    if sys.version_info[:2] != (3, 13):
        bad.append("lease requires Python 3.13")
    return got, bad


def load_policy(path):
    import numpy as np
    import torch

    with np.load(path, allow_pickle=False) as z:
        n = sum(k.startswith("w") for k in z.files)
        if not 1 <= n <= 8:
            raise ValueError("expected 1..8 MLP layers")
        weights, biases, shapes = [], [], []
        prev = 45
        for i in range(n):
            w, b = np.asarray(z[f"w{i}"]), np.asarray(z[f"b{i}"])
            if (w.ndim != 2 or w.shape[1] != prev or
                    not 1 <= w.shape[0] <= 1024 or b.shape != (w.shape[0],)):
                raise ValueError(f"invalid layer {i} shape")
            if not np.isfinite(w).all() or not np.isfinite(b).all():
                raise ValueError(f"non-finite layer {i}")
            weights.append(torch.tensor(w, dtype=torch.float32))
            biases.append(torch.tensor(b, dtype=torch.float32))
            shapes.append(list(w.shape))
            prev = w.shape[0]
        if prev != 12:
            raise ValueError("expected 12 actions")

    def policy(obs):
        with torch.no_grad():
            x = torch.tensor(obs, dtype=torch.float32)
            for i, (w, b) in enumerate(zip(weights, biases)):
                x = x @ w.T + b
                if i + 1 < n:
                    x = torch.nn.functional.elu(x)
            return x.clamp(-1.0, 1.0).numpy()
    return policy, shapes


def gravity(quat):
    import numpy as np
    w, x, y, z = quat.T
    return np.column_stack((2 * (w * y - x * z),
                            -2 * (y * z + w * x),
                            -(1 - 2 * (x * x + y * y))))


def evaluate(policy, seed, episodes, steps, mass_scale=1.0, trace=None):
    import mujoco
    import numpy as np

    model = mujoco.MjModel.from_xml_path(MODEL)
    model.opt.timestep = SIM_DT
    model.body_mass[1:] *= mass_scale
    model.body_inertia[1:] *= mass_scale
    home = model.key_qpos[0, 7:].copy()
    force_limit = np.abs(model.actuator_forcerange).max(axis=1)
    rng = np.random.default_rng(seed)
    qpos = np.tile(model.key_qpos[0], (episodes, 1))
    qpos[:, 7:] += 0.05 * rng.standard_normal((episodes, 12))
    qvel = 0.02 * rng.standard_normal((episodes, 18))
    worlds = [mujoco.MjData(model) for _ in range(episodes)]
    for i, d in enumerate(worlds):
        d.qpos[:] = qpos[i]
        d.qvel[:] = qvel[i]
        d.ctrl[:] = home
        mujoco.mj_forward(model, d)
    start_x = qpos[:, 0].copy()
    alive = np.ones(episodes, dtype=bool)
    last = np.zeros((episodes, 12))
    command = np.tile([1.0, 0.0, 0.0], (episodes, 1))
    saturated, samples, peak_ratio = 0, 0, 0.0
    recorded = {"qpos": [qpos.copy()], "qvel": [qvel.copy()],
                "alive": [alive.copy()]} if trace else None
    for _ in range(steps):
        obs = np.column_stack((gravity(qpos[:, 3:7]), qvel[:, 3:6],
                               command, qpos[:, 7:] - home,
                               qvel[:, 6:], last))
        action = policy(obs)
        if action.shape != (episodes, 12) or not np.isfinite(action).all():
            raise ValueError("non-finite or wrongly shaped actions")
        last = np.clip(action, -1, 1)
        targets = np.clip(home + 0.5 * last,
                          model.actuator_ctrlrange[:, 0],
                          model.actuator_ctrlrange[:, 1])
        for i, d in enumerate(worlds):
            if not alive[i]:
                continue
            d.ctrl[:] = targets[i]
            for _ in range(DECIM):
                mujoco.mj_step(model, d)
                ratio = np.abs(d.actuator_force) / force_limit
                saturated += int((ratio >= 0.99).sum())
                samples += 12
                peak_ratio = max(peak_ratio, float(ratio.max()))
            qpos[i], qvel[i] = d.qpos, d.qvel
        if not np.isfinite(qpos).all() or not np.isfinite(qvel).all():
            raise ValueError("non-finite simulation state")
        alive &= (qpos[:, 2] >= MIN_TRUNK_Z) & (
            gravity(qpos[:, 3:7])[:, 2] <= FALL_GZ)
        if recorded is not None:
            for key, value in (("qpos", qpos), ("qvel", qvel), ("alive", alive)):
                recorded[key].append(value.copy())
    forward = (qpos[:, 0] - start_x) / (steps * CTRL_DT)
    metrics = {"forward_mps": round(float(forward.mean()), 6),
               "min_forward_mps": round(float(forward.min()), 6),
               "fall_rate": round(float((~alive).mean()), 6),
               "sat_frac": round(saturated / max(samples, 1), 6),
               "peak_torque_ratio": round(peak_ratio, 6)}
    if recorded is not None:
        np.savez_compressed(trace, **{k: np.asarray(v) for k, v in recorded.items()},
                            seed=seed, sim_dt=SIM_DT, control_dt=CTRL_DT,
                            mass_scale=mass_scale,
                            model_sha256=sha256(MODEL),
                            metrics=json.dumps(metrics, sort_keys=True))
    return metrics


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def emit(verdict, path):
    verdict.setdefault("ok", False)
    with open(path, "w") as fh:
        json.dump(verdict, fh, indent=2, sort_keys=True, allow_nan=False)
    print(json.dumps(verdict, sort_keys=True, allow_nan=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", required=True)
    ap.add_argument("--json", default="verdict.json")
    ap.add_argument("--seeds", default="101,202,303")
    ap.add_argument("--episodes", type=int, default=64)
    ap.add_argument("--steps", type=int, default=500)
    ap.add_argument("--mass-scale", type=float, default=1.0)
    ap.add_argument("--trace-dir")
    a = ap.parse_args()
    t0 = time.monotonic()
    seeds = [int(s) for s in a.seeds.split(",")]
    if a.episodes < 1 or a.steps < 1 or not 0 < a.mass_scale < 10:
        ap.error("invalid rollout dimensions or mass")
    verdict = {"artifact": "policy.npz", "policy_sha256": sha256(a.policy),
               "model_sha256": sha256(MODEL), "backend": "mujoco-cpu-float64",
               "eval": {"seeds": seeds, "episodes_per_seed": a.episodes,
                        "steps": a.steps, "cmd": [1.0, 0.0, 0.0],
                        "mass_scale": a.mass_scale},
               "gates": {}, "runs": [], "timing": {}}
    try:
        stack, bad = check_stack()
        verdict["stack"] = stack
        if bad:
            raise ValueError("lease stack mismatch: " + "; ".join(bad))
        import numpy as np
        import torch
        torch.set_num_threads(1)
        policy, shapes = load_policy(a.policy)
        verdict["policy_shapes"] = shapes
        runs = []
        for seed in seeds:
            trace = None
            if a.trace_dir:
                os.makedirs(a.trace_dir, exist_ok=True)
                trace = os.path.join(a.trace_dir, f"seed-{seed}.npz")
            r = evaluate(policy, seed, a.episodes, a.steps, a.mass_scale, trace)
            runs.append(r)
            verdict["runs"].append({"seed": seed, "policy": "under_test", **r})
            if trace:
                verdict.setdefault("traces", {})[str(seed)] = sha256(trace)
        repeat = evaluate(policy, seeds[0], a.episodes, a.steps, a.mass_scale)
        verdict["determinism"] = {"seed": seeds[0], "a": runs[0], "b": repeat,
                                  "identical": runs[0] == repeat}
        baseline_rng = np.random.default_rng(seeds[0] ^ 0x5EED)
        baselines = {
            "zero": lambda obs: np.zeros((len(obs), 12)),
            "random": lambda obs: baseline_rng.uniform(-1, 1, (len(obs), 12))}
        verdict["baselines"] = {}
        for name, pol in baselines.items():
            r = evaluate(pol, seeds[0], a.episodes, a.steps, a.mass_scale)
            verdict["baselines"][name] = r
            verdict["runs"].append({"seed": seeds[0], "policy": name, **r})
        fwd = round(float(np.mean([r["forward_mps"] for r in runs])), 6)
        fall = round(float(np.mean([r["fall_rate"] for r in runs])), 6)
        sat = max(r["sat_frac"] for r in runs)
        peak = max(r["peak_torque_ratio"] for r in runs)
        best = max(r["forward_mps"] for r in verdict["baselines"].values())
        margin = round(fwd - best, 6)
        verdict["measured"] = {"mean_forward_mps": fwd, "fall_rate": fall,
                               "max_sat_frac": sat, "peak_torque_ratio": peak,
                               "best_baseline_forward_mps": best}
        verdict["gates"] = {
            "g1_forward_speed": {"pass": fwd >= 0.5, "value": fwd,
                                 "rule": "mean forward m/s >= 0.5"},
            "g2_fall_rate": {"pass": fall <= 0.05, "value": fall,
                             "rule": "fall rate <= 0.05"},
            "g3_torque_saturation": {"pass": sat <= 0.15 and peak <= 1.000001,
                                     "value": sat,
                                     "rule": "saturation <= 0.15; torque ratio <= 1.000001"},
            "g4_beats_baseline": {"pass": margin >= 0.30, "value": margin,
                                  "rule": "beats best zero/random baseline by >= 0.30 m/s"},
            "g5_determinism": {"pass": runs[0] == repeat,
                               "value": runs[0] == repeat,
                               "rule": "same seed gives identical metrics"}}
        verdict["ok"] = all(g["pass"] for g in verdict["gates"].values())
    except Exception as exc:
        verdict["error"] = f"{type(exc).__name__}: {exc}"
    verdict["timing"]["wall_s"] = round(time.monotonic() - t0, 3)
    emit(verdict, a.json)
    return 0 if verdict["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
