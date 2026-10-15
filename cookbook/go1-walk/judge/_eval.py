"""Go1 walking judge: runs ON the GPU lease. Never trusts the artifact.

Usage (on the lease, cwd = the shipped job dir):

    python3 _eval.py --policy policy.npz --json verdict.json \
        [--seeds 101,202,303] [--episodes 64] [--steps 500]
        [--mass-scale 1.0] [--cmd 1.0,0.0,0.0]

The artifact under test is policy.npz (actor weights + metadata) plus any
training config the agent wrote; both are treated as data only. Every gated
number below is measured here by simulating the shipped model with
mujoco-warp; nothing is read back from files the artifact controls.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

EXPECTED_STACK = {"warp": "1.13.0", "mujoco": "3.8.1",
                  "mujoco_warp": "3.8.1", "numpy": "1.26.4",
                  "torch": "2.10.0+cu128"}

# Gate thresholds (see SPEC.md). Measured reference values are in RECEIPT.md.
G1_MIN_FORWARD_MPS = 0.5      # >= 50% of the commanded 1.0 m/s
G2_MAX_FALL_RATE = 0.05       # <= 5% of episodes may ever fall
G3_MAX_SAT_FRAC = 0.15        # <= 15% of actuator samples saturated
G4_MIN_MARGIN_MPS = 0.30      # must beat the better baseline by 0.3 m/s
G4_BASELINES = ("zero", "random")
NORM4 = 4                     # verdict floats are rounded to 4 decimals


def check_stack():
    got, bad = {}, []
    for name, want in EXPECTED_STACK.items():
        try:
            mod = __import__(name)
            v = getattr(mod, "__version__", "?")
        except Exception:
            v = "missing"
        got[name] = v
        if v != want:
            bad.append(f"{name} {v} != {want}")
    return got, bad


def load_policy(path, hidden, device):
    """Rebuild the actor from the artifact's raw weights (allow_pickle off)."""
    import numpy as np
    import torch
    z = np.load(path, allow_pickle=False)
    n_layers = sum(1 for k in z.files if k.startswith("w"))
    if n_layers < 1:
        raise ValueError("policy.npz has no weight arrays")
    w = [torch.tensor(np.asarray(z[f"w{i}"]), dtype=torch.float32,
                      device=device) for i in range(n_layers)]
    b = [torch.tensor(np.asarray(z[f"b{i}"]), dtype=torch.float32,
                      device=device) for i in range(n_layers)]
    shapes = [tuple(x.shape) for x in w]

    def policy(obs):
        x = obs
        for i in range(n_layers):
            x = x @ w[i].T + b[i]
            if i < n_layers - 1:
                x = torch.nn.functional.elu(x)
        return torch.clamp(x, -1.0, 1.0)
    return policy, shapes


def evaluate(env, policy, steps, cmd, torch):
    """Rollout with a fixed command; fallen envs keep simulating and are
    marked dead. Returns per-run metrics (all floats rounded)."""
    import env as E
    dev = env.qpos.device
    env.reset_all()
    env.auto_reset = False
    env.cmd[:] = torch.tensor(cmd, device=dev)
    start_xy = env.qpos[:, :2].clone()
    alive = torch.ones(env.n, dtype=torch.bool, device=dev)
    sat = torch.zeros(env.n, dtype=torch.long, device=dev)
    for _ in range(steps):
        with torch.no_grad():
            act = policy(env.obs())
        env.step(act)
        quat = env.qpos[:, 3:7]
        grav = env._rot_inv(quat, torch.tensor(
            [0.0, 0.0, -1.0], device=dev).expand(env.n, 3))
        fell = (env.qpos[:, 2] < E.MIN_TRUNK_Z) | (grav[:, 2] > E.FALL_GZ)
        alive &= ~fell
        sat += (env.qfrc.abs() >= 0.99 * env.frange).sum(-1)
    d = env.qpos[:, :2] - start_xy
    T = steps * 0.02
    fwd = d[:, 0] / T  # initial heading is +x for every env (identity quat)
    return {"forward_mps": round(float(fwd.mean()), NORM4),
            "min_forward_mps": round(float(fwd.min()), NORM4),
            "fall_rate": round(float((~alive).float().mean()), NORM4),
            "sat_frac": round(float(sat.float().mean() / steps), NORM4)}


def zero_policy(obs):
    import torch
    return torch.zeros(obs.shape[0], 12, device=obs.device)


def make_random_policy(seed, device):
    import torch
    g = torch.Generator(device=device)
    g.manual_seed(seed ^ 0x5EED)

    def policy(obs):
        return torch.rand(obs.shape[0], 12, generator=g,
                          device=obs.device) * 2.0 - 1.0
    return policy


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", required=True)
    ap.add_argument("--json", default="verdict.json")
    ap.add_argument("--seeds", default="101,202,303")
    ap.add_argument("--episodes", type=int, default=64)
    ap.add_argument("--steps", type=int, default=500)
    ap.add_argument("--mass-scale", type=float, default=1.0)
    ap.add_argument("--cmd", default="1.0,0.0,0.0")
    a = ap.parse_args()
    t0 = time.time()

    verdict = {"artifact": os.path.basename(a.policy),
               "policy_sha256": hashlib.sha256(
                   open(a.policy, "rb").read()).hexdigest(),
               "eval": {"seeds": [int(s) for s in a.seeds.split(",")],
                        "episodes_per_seed": a.episodes,
                        "steps": a.steps, "cmd": a.cmd,
                        "mass_scale": a.mass_scale},
               "gates": {}, "timing": {"wall_s": 0.0}}

    stack, bad = check_stack()
    verdict["stack"] = stack
    if bad:
        verdict["error"] = "lease stack mismatch: " + "; ".join(bad)
        _emit(verdict, a.json)
        sys.exit(2)

    import torch  # noqa: F401 - policy backend on the lease
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import env as E

    cmd = tuple(float(x) for x in a.cmd.split(","))
    try:
        policy, shapes = load_policy(a.policy, None, "cuda")
    except Exception as exc:
        verdict["error"] = f"artifact unreadable: {exc}"
        _emit(verdict, a.json)
        sys.exit(2)
    verdict["policy_shapes"] = shapes
    if tuple(shapes[0][1:]) and shapes[0][-1] != E.OBS_DIM:
        pass  # first layer fan-in is checked by running it below

    seeds = [int(s) for s in a.seeds.split(",")]
    try:
        run_fwd, run_fall, run_sat = [], [], []
        for si, seed in enumerate(seeds):
            env = E.Go1Batch(a.episodes, seed=seed,
                             mass_scale=a.mass_scale,
                             episode_steps=a.steps + 8)
            r = evaluate(env, policy, a.steps, cmd, env.torch)
            run_fwd.append(r["forward_mps"])
            run_fall.append(r["fall_rate"])
            run_sat.append(r["sat_frac"])
            verdict.setdefault("runs", []).append(
                {"seed": seed, "policy": "under_test", **r})
            if si == 0:
                env2 = E.Go1Batch(a.episodes, seed=seed,
                                  mass_scale=a.mass_scale,
                                  episode_steps=a.steps + 8)
                r2 = evaluate(env2, policy, a.steps, cmd, env2.torch)
                verdict["determinism"] = {"seed": seed, "a": r, "b": r2,
                                          "identical": r == r2}
            del env
        for name in G4_BASELINES:
            env = E.Go1Batch(a.episodes, seed=seeds[0],
                             mass_scale=a.mass_scale,
                             episode_steps=a.steps + 8)
            pol = zero_policy if name == "zero" else \
                make_random_policy(seeds[0], env.qpos.device)
            r = evaluate(env, pol, a.steps, cmd, env.torch)
            verdict["runs"].append({"seed": seeds[0], "policy": name, **r})
            verdict.setdefault("baselines", {})[name] = r
            del env
    except Exception as exc:
        verdict["error"] = f"evaluation failed: {exc}"
        _emit(verdict, a.json)
        sys.exit(2)

    fwd = round(sum(run_fwd) / len(run_fwd), NORM4)
    fall = round(sum(run_fall) / len(run_fall), NORM4)
    sat = round(max(run_sat), NORM4)
    best_base = max(b["forward_mps"]
                    for b in verdict["baselines"].values())
    verdict["measured"] = {"mean_forward_mps": fwd, "fall_rate": fall,
                           "max_sat_frac": sat,
                           "best_baseline_forward_mps": best_base}
    verdict["gates"] = {
        "g1_forward_speed": {
            "pass": fwd >= G1_MIN_FORWARD_MPS,
            "rule": f"mean forward m/s >= {G1_MIN_FORWARD_MPS}",
            "value": fwd},
        "g2_fall_rate": {
            "pass": fall <= G2_MAX_FALL_RATE,
            "rule": f"fall rate <= {G2_MAX_FALL_RATE}",
            "value": fall},
        "g3_torque_saturation": {
            "pass": sat <= G3_MAX_SAT_FRAC,
            "rule": f"actuator saturation fraction <= {G3_MAX_SAT_FRAC}",
            "value": sat},
        "g4_beats_baseline": {
            "pass": fwd - best_base >= G4_MIN_MARGIN_MPS,
            "rule": f"forward m/s beats best of {G4_BASELINES} "
                    f"by >= {G4_MIN_MARGIN_MPS}",
            "value": round(fwd - best_base, NORM4)},
        "g5_determinism": {
            "pass": verdict["determinism"]["identical"],
            "rule": "same seed graded twice gives identical metrics",
            "value": verdict["determinism"]["identical"]},
    }
    verdict["ok"] = all(g["pass"] for g in verdict["gates"].values())
    verdict["timing"] = {"wall_s": round(time.time() - t0, 1)}
    _emit(verdict, a.json)
    sys.exit(0 if verdict["ok"] else 1)


def _emit(verdict, path):
    with open(path, "w") as fh:
        json.dump(verdict, fh, indent=1, sort_keys=True)
    print(json.dumps(verdict, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
