# Go1 quadruped walking — batched MuJoCo-Warp PPO on a GPU slice

An agent works on a real robot-learning problem on a disposable agent-next
GPU lease: train a **Unitree Go1 quadruped to walk** (track a forward
velocity command) with batched MuJoCo-Warp simulation and PPO, on a single
4 GiB RTX 5090 VRAM slice, in minutes. The artifact the agent produces is
a training config plus a small MLP policy checkpoint (`policy.npz`). A
judge it cannot fool then *re-simulates* that checkpoint itself on
held-out seeds and held-out command conditions the training never saw —
every gated number (forward speed, fall rate, torque saturation, margin
over a zero/random baseline, determinism) is measured by the judge's own
MuJoCo-Warp rollouts; nothing is read back from the artifact.

A GPU-slice lease helps because robot RL needs a real GPU but not a real
workstation: the lease is a 4 GiB VRAM slice of an RTX 5090 with a fixed,
pre-installed physics stack (warp-lang 1.13.0, mujoco 3.8.1, mujoco-warp
3.8.1, torch 2.10.0+cu128), no network, files shipped in through the exec
payload — including the Go1 model itself — and it is destroyed afterwards.
The judge asserts the stack versions on the lease before simulating and
fails closed on any drift, so the result does not depend on what happens
to be installed locally.

## One-command run

From this repository's root, with Python 3.10+ (standard library only)
and `SBX_API_KEY` exported:

```bash
python3 cookbook/go1-walk/run.py
```

`run.py` creates a 4 GiB VRAM-slice lease over the agent-next REST API
(`POST /sandboxes {"accel":{"vram_gb":4,"reserve":"exec"}}`, then
`POST /sandboxes/{id}/exec` for each job, `DELETE` + `GET`→404 in a
`finally`), ships `env.py`/`train.py`/`judge/_eval.py`/the Go1 model as a
base64 payload (the lease has no network), trains PPO, downloads the
checkpoint to `cookbook/go1-walk/out/`, and grades the fresh policy on
held-out seeds `101,202,303` — 64 episodes per seed, 500 control steps
(10 s) each, fixed `vx = 1.0 m/s` command. It prints wall time per step
and the gate-by-gate verdict, then destroys the lease and confirms it is
gone.

Measured on this key (see RECEIPT.md for the pasted runs): lease create
~8 s, first warp-kernel compile ~45 s inside the first job, training
__TRAIN_WALL__ (__ITERS__ PPO iterations, __ENV_STEPS__ env steps,
__STEPS_PER_S__ env-steps/s), held-out grading __EVAL_WALL__, end-to-end
__TOTAL__. The trained policy walks at __FWD__ m/s mean forward speed on
the held-out seeds (command 1.0 m/s), __FALL__ fall rate, verdict PASS.

Useful flags: `--vram N` (slice size), `--iters N` (cap PPO iterations),
`--skip-train DIR` (grade an existing artifact directory instead of
training), `--selftest` (also grade `examples/good` plus all mutants on
the same lease and print the kill rate), `--keep` (leave the lease up and
print its id), `--seeds` (override the held-out seeds).

To run just the judge against the committed known-good artifact:

```bash
bash cookbook/go1-walk/judge/setup.sh      # pinned numpy venv for mutants.py
bash cookbook/go1-walk/judge/grade.sh cookbook/go1-walk/examples/good
bash cookbook/go1-walk/judge/selftest.sh   # good passes twice identically;
                                           # 8/8 mutants die (measured)
```

## Ask your agent

With the sandbox plugin installed, paste this prompt. The agent creates
the GPU lease, ships the job, iterates on the training config, and reads
the judge verdict itself — that loop is the demo:

> Create a GPU lease (`POST https://api.sbx.agent-next.com/sandboxes`
> `{"accel":{"vram_gb":4,"reserve":"exec"}}` with header
> `X-API-Key: $SBX_API_KEY`; run Python with
> `POST /sandboxes/{id}/exec {"code": ..., "timeout_s": N}`; whatever the
> code puts in a dict named `report` comes back as `result.report`; files
> under `~` persist across execs; always `DELETE` the lease in a finally
> and confirm `GET` returns 404). The lease has no network: ship
> `cookbook/go1-walk/env.py`, `train.py`, `judge/_eval.py` and
> `model/go1_meshless.xml` base64-encoded in the exec payload. Read
> `cookbook/go1-walk/SPEC.md`: train a PPO policy for the batched Go1
> environment (you may tune `examples/good/train_config.json` — seeds,
> reward weights, PPO hyperparameters, iteration count) until the policy
> passes all five gates when the judge re-simulates it on held-out seeds
> (`python3 _eval.py --policy out/policy.npz --json verdict.json --seeds
> 101,202,303` on the lease). The judge ignores every number your files
> claim; only what it measures in its own simulation counts. When every
> gate passes, report the verdict JSON and the training wall time /
> env-steps-per-second, then delete the lease and confirm it is gone. If
> you cannot pass a gate, say which one and what you tried, and stop.

## What the judge checks (short form)

`judge/_eval.py` runs on the lease: N=64 episodes per held-out seed
(default `101,202,303`), T=500 control steps at 50 Hz, fixed command
`(1.0, 0.0, 0.0)` m/s.

| gate | rule (all measured by the judge's own simulation) |
|---|---|
| G1 forward speed | mean forward m/s over all held-out episodes >= 0.5 |
| G2 fall rate | fraction of episodes with >= 1 fall <= 0.05 |
| G3 torque saturation | fraction of actuator samples at >= 99% of forcerange <= 0.15 |
| G4 beats baseline | forward m/s beats the better of zero/random policy by >= 0.30 |
| G5 determinism | the first seed graded twice gives identical metrics |

The acceptance oracle is physics itself: a quadruped cannot average
0.5 m/s for 10 s upright under foot-only contacts unless it actually
walks; standing still scores ~0 and a fallen robot is marked dead.

## Limits, stated plainly

- The policy is a plain 3-hidden-layer MLP (45 obs -> 512-256-128 -> 12
  PD position targets); it is a walking demo, not a deployable controller.
- Training is PPO-from-scratch and seed-sensitive: some seeds stall at
  "stand still". The shipped config walked on the measured run; the
  trainer early-stops once two consecutive 64-episode checks exceed
  0.8 m/s. Your run may land a different-but-passing policy.
- The judge evaluates the shipped `policy.npz` only; it does not re-run
  training. Retraining gives a different checkpoint (PPO is stochastic)
  that still must pass the same gates.
- Determinism (G5) holds bit-exact on the same lease image; it is not
  guaranteed across a different GPU/driver/stack, which is why the judge
  pins the stack versions.
- Training fits the 4 GiB slice with headroom (measured peak well under
  the cap; see RECEIPT.md). Larger `num_envs` may need `--vram 8`.
- Media (`media/`) is a later round; the data it needs is in
  `examples/good/loop.json` and the verdict JSONs.

See `SPEC.md` for the full contract and `RECEIPT.md` for real pasted
output of every command above.
