# go1-walk — SPEC

## Goal

Train a Unitree Go1 quadruped (MuJoCo Menagerie model) to track a forward
velocity command, using batched MuJoCo-Warp simulation + PPO on a single
4 GiB RTX 5090 VRAM-slice lease, in minutes. The agent produces a training
config and a policy checkpoint; a judge re-simulates the checkpoint on
held-out seeds and decides pass/fail.

## Non-goals

- No rendering/video in the graded path (media is a later round).
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

The judge runs its own rollouts on the lease: `N=64` episodes per held-out
seed, `T=500` control steps (10 s) each, fixed command `(1.0, 0.0, 0.0)`,
seeds `101,202,303` by default (`--seed` overrides). Training used seed 1
with commands sampled from vx in [0.4, 1.0]; the judge's seeds and the fixed
1.0 m/s command are the held-out conditions.

| gate | rule (all numbers measured by the judge's own sim) |
|---|---|
| G1 forward speed | mean forward m/s across all held-out episodes >= 0.5 (50% of the 1.0 m/s command) |
| G2 fall rate | fraction of episodes with >= 1 fall (trunk < 0.10 m or tilt > ~57 deg) <= 0.05 |
| G3 torque saturation | fraction of actuator samples at >= 99% of forcerange <= 0.15 (per-seed max) |
| G4 beats baseline | mean forward m/s - max(zero-action, random-policy baseline) >= 0.30 |
| G5 determinism | the first seed graded twice gives identical metrics |

The acceptance oracle is physics itself: a quadruped cannot net 0.5 m/s for
10 s upright under foot-only contacts unless it actually walks; standing
still scores ~0, and a falling robot terminates.

## Reproduction tolerances

Same seed on the same lease image is bit-identical (G5). Across runs the
verdict JSON must be identical except the `timing` key. Different seeds
give different numbers but a passing artifact stays passing (tolerance: all
G1-G4 margins are set >= 3x looser than the measured good-artifact values —
see RECEIPT.md).

## Lease stack (asserted at grade time)

warp-lang 1.13.0, mujoco 3.8.1, mujoco-warp 3.8.1, torch 2.10.0+cu128,
numpy 1.26.4, Python 3.13 on an RTX 5090 slice. The judge fails closed if
any version differs.
