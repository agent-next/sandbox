# go1-walk — SPEC

## Goal

Train a Unitree Go1 quadruped (MuJoCo Menagerie model) to track a forward
velocity command, using batched MuJoCo-Warp simulation + PPO on a single
4 GiB RTX 5090 VRAM-slice lease, in minutes. The agent produces a training
config and a policy checkpoint; a judge re-simulates the checkpoint on
held-out seeds and decides pass/fail.

## Non-goals

- Rendering is not part of acceptance; media replays the judge's exact states.
- No sim-to-real, no terrain curriculum, no joystick yaw/lateral tracking
  beyond the sampled command ranges used in training.
- The judge does not re-run training; it grades the produced checkpoint.

## The artifact

A directory containing:

- `train_config.json` — the agent's training hyperparameters (informational;
  the judge ignores every claimed result in it).
- `policy.npz` — the trained actor, saved by `train.py` (`w0..wN`, `b0..bN`
  float32 arrays for an MLP `obs(45) -> hidden -> act(12)`, ELU between
  layers, actions clipped to [-1, 1]).

`policy.npz` is data, not code: it is loaded with `np.load(allow_pickle=False)`
and can only influence the verdict through the torques it produces in the
judge's own simulation.

## Environment

`env.py` (shipped by the demo, not by the artifact): MuJoCo-Warp batch sim of
the meshless Go1, dt 0.002 s, control dt 0.02 s, 12 PD position actuators
(kp=100, forcerange +/-23.7/35.55 N*m), 45-dim observation
(gravity-in-body 3, gyro 3, command 3, joint pos/vel 12+12, last action 12).
Only the four foot spheres collide with the floor.

## Gates

The judge runs single-threaded **CPU MuJoCo** rollouts on the lease, with
float64 state, independently of the batched Warp trainer: `N=64` episodes per held-out
seed, `T=500` control steps (10 s) each, fixed command `(1.0, 0.0, 0.0)`,
seeds `101,202,303` by default (`--seed` overrides). Training used seed 1
with commands sampled from vx in [0.4, 1.0] and yaw in [-0.3, 0.3].
Evaluation seeds never enter training, and evaluation fixes yaw at zero.
The 1.0 m/s command is the upper endpoint of training, not an unseen speed.
Each episode starts at the home pose with independent Gaussian joint
position (standard deviation 0.05 rad) and velocity (0.02) perturbations.
A fall freezes that episode at its first failed control step. Forward
displacement is always divided by the full 10 s, never by survival time.

| gate | rule (all numbers measured by the judge's own sim) |
|---|---|
| G1 forward speed | mean forward m/s across all held-out episodes >= 0.5 (50% of the 1.0 m/s command) |
| G2 fall rate | fraction of episodes with >= 1 fall (trunk < 0.10 m or tilt > ~57 deg) <= 0.05 |
| G3 torque saturation | fraction of live actuator samples at >= 99% of forcerange <= 0.15 (per-seed max); peak absolute torque / limit <= 1.000001 |
| G4 beats baseline | mean forward m/s - max(zero-action, random-policy baseline) >= 0.30 |
| G5 determinism | the first seed graded twice: identical metrics |

The acceptance oracle is a measured task specification, not a claim about
the reward or an analytic optimal gait: net forward displacement / 10 s,
uprightness throughout, physical torque limits, and superiority to two
independently simulated baselines. Torque is sampled at every 0.002 s
physics substep. A stationary policy cannot pass G1/G4; falls cannot
inflate the score by shortening the denominator. This does not prove
sim-to-real safety or biomechanical gait quality.

## Reproduction tolerances

The same checkpoint, model, seeds and pinned stack must produce
byte-identical verdict JSON after removing only `timing`. Self-test
enforces this across two complete grades, as well as G5's repeated seed.
Warp training is stochastic and can produce different checkpoints.
Two fresh retraining runs must each pass all five gates; their raw
numbers need not be identical. Independent checkpoint reproduction
requires exact gate values (six-decimal reporting).

## Media contract

`--trace` records all evaluated states, including the initial state, in
NPZ data controlled by the judge. `media/make_media.sh` grades both the
trained and real step-0 checkpoint, fetches these states, and replays
them with `mujoco.Renderer`. It never interpolates or re-simulates poses.
Every frame checks qpos within 1e-9 against that graded data. Render-only
materials, lights and textures cannot alter the model's physics.
The video is 1920x1080, 30 fps, 30 s, H.264 CRF 18 from a CRF 0 master,
under 8 MB. Hero stills and training/judge-loop graphics use Pillow.

## Lease stack (asserted at grade time)

warp-lang 1.13.0, mujoco 3.8.1, mujoco-warp 3.8.1, torch 2.10.0+cu128,
numpy 1.26.4, Python 3.13 on an RTX 5090 slice. The judge fails closed if
any version differs.
