"""PPO trainer for the Go1 walking task. Produces the artifact the judge
grades: policy.npz (actor weights + metadata) driven by train_config.json.

    python train.py --config train_config.json --out outdir \
        [--resume outdir/state.pt] [--max-wall-s S] [--progress FILE]

The lease exec endpoint caps a single call at ~600 s, so training runs in
chunks: each invocation trains until the iteration target or --max-wall-s
is exhausted, saves full resumable state (nets + optimizer + RNG + curve)
to <out>/state.pt and a one-line status to --progress, then exits 0.
The caller (run.py) repeats until status.finished. stdlib + torch only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time

import numpy as np

import env as E


def build_nets(obs_dim=E.OBS_DIM, n_act=E.N_JOINTS, hidden=(512, 256, 128),
               seed=0, device="cuda"):
    import torch
    import torch.nn as nn

    def mlp(dims, out):
        layers, prev = [], dims
        for h in hidden:
            layers += [nn.Linear(prev, h), nn.ELU()]
            prev = h
        layers.append(nn.Linear(prev, out))
        return nn.Sequential(*layers)

    torch.manual_seed(seed)
    actor = mlp(obs_dim, n_act).to(device)
    critic = mlp(obs_dim, 1).to(device)
    log_std = torch.nn.Parameter(torch.zeros(n_act, device=device))
    return actor, critic, log_std


def save_policy(actor, path, meta):
    sd = actor.state_dict()
    ws = [v.detach().cpu().numpy() for v in sd.values() if v.ndim == 2]
    bs = [v.detach().cpu().numpy() for v in sd.values() if v.ndim == 1]
    arrays = {f"w{i}": v for i, v in enumerate(ws)}
    arrays.update({f"b{i}": v for i, v in enumerate(bs)})
    arrays["__meta__"] = np.frombuffer(json.dumps(meta).encode(),
                                       dtype=np.uint8)
    np.savez(path, **arrays)


def load_policy(path, device="cuda"):
    """-> (callable obs->act torch tensor, meta dict)."""
    import torch
    z = np.load(path)
    meta = json.loads(z["__meta__"].tobytes())
    n_layers = sum(1 for k in z.files if k.startswith("w"))
    w = [torch.tensor(z[f"w{i}"], device=device) for i in range(n_layers)]
    b = [torch.tensor(z[f"b{i}"], device=device) for i in range(n_layers)]

    def policy(obs):
        x = obs
        for i in range(n_layers):
            x = x @ w[i].T + b[i]
            if i < n_layers - 1:
                x = torch.nn.functional.elu(x)
        return x
    return policy, meta


class PPO:
    def __init__(self, cfg, device="cuda"):
        import torch
        self.torch = torch
        self.device = device
        p = cfg["ppo"]
        self.actor, self.critic, self.log_std = build_nets(
            hidden=tuple(p["hidden"]), seed=cfg["seed"], device=device)
        self.opt = torch.optim.Adam(
            list(self.actor.parameters()) + list(self.critic.parameters())
            + [self.log_std], lr=p["lr"])
        self.gamma, self.lam = p["gamma"], p["lam"]
        self.clip, self.ent, self.vf = p["clip"], p["entropy"], p["vf"]
        self.epochs, self.minibatches = p["epochs"], p["minibatches"]

    def act_dist(self, obs):
        mu = self.actor(obs)
        std = self.log_std.exp().expand_as(mu)
        return self.torch.distributions.Normal(mu, std)

    def rollout(self, env):
        """Collect cfg['steps_per_iter'] control steps from the env."""
        torch = self.torch
        obs = env.obs()
        buf = {k: [] for k in ("obs", "act", "logp", "rew", "val", "done")}
        for _ in range(env.rollout_steps):
            with torch.no_grad():
                d = self.act_dist(obs)
                a = d.sample()
                v = self.critic(obs).squeeze(-1)
            obs2, rew, done = env.step(a)
            for k, x in (("obs", obs), ("act", a),
                         ("logp", d.log_prob(a).sum(-1)), ("rew", rew),
                         ("val", v), ("done", done.float())):
                buf[k].append(x)
            obs = obs2
        with torch.no_grad():
            last_val = self.critic(obs).squeeze(-1)
        return {k: torch.stack(v) for k, v in buf.items()}, last_val

    def update(self, buf, last_val):
        torch = self.torch
        T, N = buf["rew"].shape
        adv = torch.zeros_like(buf["rew"])
        gae = torch.zeros(N, device=buf["rew"].device)
        not_done = 1.0 - buf["done"]
        for t in reversed(range(T)):
            nv = last_val if t == T - 1 else buf["val"][t + 1]
            delta = buf["rew"][t] + self.gamma * nv * not_done[t] \
                - buf["val"][t]
            gae = delta + self.gamma * self.lam * not_done[t] * gae
            adv[t] = gae
        ret = adv + buf["val"]
        flat = {k: v.reshape(-1, *v.shape[2:]) for k, v in buf.items()}
        adv, ret = adv.reshape(-1), ret.reshape(-1)
        adv = (adv - adv.mean()) / (adv.std() + 1e-8)
        n = flat["obs"].shape[0]
        mbs = n // self.minibatches
        for _ in range(self.epochs):
            perm = torch.randperm(n, device=flat["obs"].device)
            for i in range(0, n, mbs):
                mb = perm[i:i + mbs]
                d = self.act_dist(flat["obs"][mb])
                logp = d.log_prob(flat["act"][mb]).sum(-1)
                ratio = (logp - flat["logp"][mb]).exp()
                s1 = ratio * adv[mb]
                s2 = torch.clamp(ratio, 1 - self.clip, 1 + self.clip) * adv[mb]
                pg = -torch.min(s1, s2).mean()
                v = self.critic(flat["obs"][mb]).squeeze(-1)
                vloss = 0.5 * (v - ret[mb]).pow(2).mean()
                ent = d.entropy().sum(-1).mean()
                loss = pg + self.vf * vloss - self.ent * ent
                self.opt.zero_grad()
                loss.backward()
                self.torch.nn.utils.clip_grad_norm_(
                    list(self.actor.parameters())
                    + list(self.critic.parameters())
                    + [self.log_std], 1.0)
                self.opt.step()
        return float(buf["rew"].mean())


DEFAULT_CFG = {
    "seed": 1,
    "num_envs": 4096,
    "iters": 400,
    "rollout_steps": 24,
    "episode_steps": 500,
    "cmd_vx": [0.4, 1.0],
    "mass_scale": 1.0,
    "reward": {},          # overrides env.REWARD_DEFAULTS
    "ppo": {"hidden": [512, 256, 128], "lr": 3e-4, "gamma": 0.99,
            "lam": 0.95, "clip": 0.2, "entropy": 0.005, "vf": 1.0,
            "epochs": 5, "minibatches": 4},
    "eval_every": 50, "eval_start": 200,
    "walk_mps": 0.8,       # early-stop: two evals >= walk_mps
    "min_iters": 150,
}


def evaluate(env, policy, steps, cmd=(1.0, 0.0, 0.0)):
    """Held-out style rollout: fixed command, fallen envs keep simulating
    (marked not-alive). Returns mean forward m/s and upright fraction."""
    import torch
    torch = env.torch
    env.reset_all()
    env.auto_reset = False
    env.cmd[:] = torch.tensor(cmd, device=env.qpos.device)
    start_xy = env.qpos[:, :2].clone()
    q0 = env.qpos[:, 3:7].clone()
    w, x, y, z = q0.unbind(-1)
    yaw0 = torch.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    alive = torch.ones(env.n, dtype=torch.bool, device=env.qpos.device)
    for _ in range(steps):
        with torch.no_grad():
            act = torch.clamp(policy(env.obs()), -1.0, 1.0)
        env.step(act)
        quat = env.qpos[:, 3:7]
        grav = env._rot_inv(quat, torch.tensor(
            [0.0, 0.0, -1.0], device=quat.device).expand(quat.shape[0], 3))
        fell = (env.qpos[:, 2] < E.MIN_TRUNK_Z) | (grav[:, 2] > E.FALL_GZ)
        alive &= ~fell
        env.cmd[:] = torch.tensor(cmd, device=env.qpos.device)
    d = env.qpos[:, :2] - start_xy
    T = steps * E.CTRL_DT
    fwd = (d[:, 0] * torch.cos(yaw0) + d[:, 1] * torch.sin(yaw0)) / T
    env.auto_reset = True
    return {"forward_mps": round(float(fwd.mean()), 4),
            "upright": round(float(alive.float().mean()), 4)}


    def state_dict(self):
        import torch
        return {"actor": self.actor.state_dict(),
                "critic": self.critic.state_dict(),
                "log_std": self.log_std.detach().cpu(),
                "opt": self.opt.state_dict(),
                "torch_rng": torch.get_rng_state(),
                "cuda_rng": torch.cuda.get_rng_state_all()}

    def load_state(self, sd):
        import torch
        self.actor.load_state_dict(sd["actor"])
        self.critic.load_state_dict(sd["critic"])
        with torch.no_grad():
            self.log_std.copy_(sd["log_std"].to(self.log_std.device))
        self.opt.load_state_dict(sd["opt"])
        torch.set_rng_state(sd["torch_rng"].cpu())
        torch.cuda.set_rng_state_all(
            [t.cpu() for t in sd["cuda_rng"]])


def train(cfg, out, log=print, resume=None, max_wall_s=0.0,
          progress_file=None):
    import torch
    t0 = time.time()
    n_envs = cfg["num_envs"]
    env = E.Go1Batch(n_envs, seed=cfg["seed"], mass_scale=cfg["mass_scale"],
                     episode_steps=cfg["episode_steps"],
                     reward=cfg["reward"], cmd_vx=cfg["cmd_vx"])
    env.rollout_steps = cfg["rollout_steps"]
    env.reset_all()
    # stagger episode counters so resets decorrelate
    env.ep_step = torch.arange(n_envs, device=env.qpos.device) \
        % cfg["episode_steps"]
    ppo = PPO(cfg)
    eval_env = None
    curve, walk_evals, hits = [], [], 0
    t_train = time.time()
    done_it = 0
    if resume and os.path.exists(resume):
        sd = torch.load(resume, map_location="cuda", weights_only=False)
        ppo.load_state(sd["ppo"])
        done_it = sd["iter"]
        curve, walk_evals = sd["curve"], sd["walk_evals"]
        hits, t_train = sd["hits"], sd["train_wall_s"]
        env.gen.set_state(sd["env_gen"].cpu())
        log(f"resumed at iteration {done_it} "
            f"(+{time.time() - t0:.0f}s restore)")
    steps_per_it = n_envs * cfg["rollout_steps"]

    def save_state(finished):
        torch.save({"ppo": ppo.state_dict(), "iter": done_it,
                    "curve": curve, "walk_evals": walk_evals,
                    "hits": hits,
                    "train_wall_s": t_train + (time.time() - t_start),
                    "env_gen": env.gen.get_state()}, state_path)
        status = {"finished": finished, "it": done_it,
                  "env_steps": steps_per_it * done_it,
                  "train_wall_s": round(
                      t_train + (time.time() - t_start), 1),
                  "mean_reward": curve[-1]["mean_reward"] if curve
                  else None,
                  "walk_evals": walk_evals}
        with open(progress_file, "w") as fh:
            json.dump(status, fh)
        return status

    state_path = os.path.join(out, "state.pt")
    t_start = time.time()
    while done_it < cfg["iters"]:
        if max_wall_s and time.time() - t_start > max_wall_s:
            return save_state(False)
        buf, last_val = ppo.rollout(env)
        r = ppo.update(buf, last_val)
        done_it += 1
        curve.append({"it": done_it, "mean_reward": round(r, 4),
                      "wall_s": round(t_train + time.time() - t_start, 2)})
        if done_it % 10 == 0:
            log(f"it {done_it} reward {r:.3f} "
                f"({steps_per_it * done_it / (t_train + time.time() - t_start):.0f} "
                "env-steps/s)")
        if done_it >= cfg["eval_start"] and done_it % cfg["eval_every"] == 0:
            if eval_env is None:
                eval_env = E.Go1Batch(64, seed=4242,
                                      mass_scale=cfg["mass_scale"])
            ev = evaluate(eval_env, lambda o: ppo.actor(o), 500)
            walk_evals.append({"it": done_it, **ev})
            log(f"walk check it {done_it}: {ev}")
            hits = hits + 1 if ev["forward_mps"] >= cfg["walk_mps"] \
                and ev["upright"] >= 0.95 else 0
            if hits >= 2:
                break
    train_wall = t_train + time.time() - t_start
    status = save_state(True)
    meta = {"trained_iters": done_it,
            "trained_env_steps": steps_per_it * done_it,
            "seed": cfg["seed"],
            "obs_dim": E.OBS_DIM, "n_act": E.N_JOINTS,
            "hidden": cfg["ppo"]["hidden"],
            "config_sha256": hashlib.sha256(
                json.dumps(cfg, sort_keys=True).encode()).hexdigest()}
    save_policy(ppo.actor, os.path.join(out, "policy.npz"), meta)
    summary = {"iters": done_it, "env_steps": steps_per_it * done_it,
               "train_wall_s": round(train_wall, 1),
               "total_wall_s": round(time.time() - t0, 1),
               "steps_per_s": round(steps_per_it * done_it / train_wall),
               "walk_evals": walk_evals, "curve": curve,
               "reward_end": curve[-1]["mean_reward"]}
    with open(os.path.join(out, "curve.json"), "w") as fh:
        json.dump(summary, fh, indent=1)
    return {**summary, **status}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--resume", default=None,
                    help="state.pt from a previous chunk")
    ap.add_argument("--max-wall-s", type=float, default=0.0,
                    help="stop and save resumable state after S seconds "
                         "of training in this chunk")
    ap.add_argument("--progress", default=None,
                    help="write a one-line JSON status here after every "
                         "chunk")
    a = ap.parse_args()
    cfg = {**DEFAULT_CFG, **json.load(open(a.config))}
    cfg["ppo"] = {**DEFAULT_CFG["ppo"], **cfg.get("ppo", {})}
    os.makedirs(a.out, exist_ok=True)
    pf = a.progress or os.path.join(a.out, "progress.json")
    summary = train(cfg, a.out, resume=a.resume, max_wall_s=a.max_wall_s,
                    progress_file=pf)
    print(json.dumps({k: v for k, v in summary.items() if k != "curve"}))


if __name__ == "__main__":
    main()
