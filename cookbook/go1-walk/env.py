"""Batched MuJoCo-Warp Go1 walking environment (self-contained; no mujoco-playground).

Model: Unitree Go1 from MuJoCo Menagerie
(https://github.com/google-deepmind/mujoco_menagerie @
d7b481bac63d3d600ab404ee74f7474c5efe8a67, BSD 3-Clause, see model/LICENSE).
Visual meshes and cameras are stripped; every collision geom in that model
is a primitive and every body has an explicit <inertial>. Only the four
foot spheres collide (upstream trains foot-only: a fallen trunk passes
through the floor, which keeps the per-world constraint arena small).

Physics dt 0.002 s, control dt 0.02 s (10 substeps). The 12 <position
kp=100 forcerange=+/-23.7/35.55> actuators of the Menagerie model are the
PD controllers: action a in [-1, 1] -> target q_home + 0.5 * a, clipped to
ctrlrange.
"""

from __future__ import annotations

import os

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_XML = os.path.join(HERE, "model", "go1_meshless.xml")

SIM_DT = 0.002
DECIM = 10
CTRL_DT = SIM_DT * DECIM  # 0.02 s
ACT_SCALE = 0.5
N_JOINTS = 12
OBS_DIM = 45
# termination: trunk below 0.10 m or body-frame gravity z > -0.55
# (tilted more than ~57 deg from upright)
MIN_TRUNK_Z = 0.10
FALL_GZ = -0.55

# reward defaults; train_config.json overrides via `reward` dict
REWARD_DEFAULTS = {
    "track_lin": 2.0,    # weight, exp(-lin_err^2 / sigma)
    "track_ang": 0.5,    # weight, exp(-ang_err^2 / 0.25)
    "sigma": 0.5,
    "lin_vel_z": -1.0,   # * vz^2
    "ang_vel_xy": -0.05,  # * (wx^2 + wy^2)
    "orientation": -0.5,  # * (gx^2 + gy^2)
    "torques": -1e-4,    # * sum(tau^2)
    "action_rate": -0.01,  # * sum(da^2)
    "alive": 0.15,
    "fall": -1.0,
}


def make_mjmodel(mass_scale: float = 1.0, xml_path: str = MODEL_XML):
    import mujoco

    m = mujoco.MjModel.from_xml_path(xml_path)
    if mass_scale != 1.0:
        m.body_mass[1:] *= mass_scale
        m.body_inertia[1:] *= mass_scale
    return m


class Go1Batch:
    """N parallel Go1 worlds stepped on the GPU with mujoco-warp.

    Observations (45): gravity in body frame (3), gyro (3), command
    (vx, vy, wz) (3), joint pos rel. home (12), joint vel (12), last
    action (12). All state lives on the GPU; torch views onto the warp
    arrays make each control step allocation-free.
    """

    def __init__(self, n_envs: int, seed: int = 0, mass_scale: float = 1.0,
                 episode_steps: int = 500, xml_path: str = MODEL_XML,
                 reward: dict | None = None, cmd_vx=(0.4, 1.0),
                 auto_reset: bool = True):
        import mujoco
        import mujoco_warp as mjw
        import torch
        import warp as wp

        self.mjw, self.torch = mjw, torch
        self.n, self.episode_steps = n_envs, episode_steps
        self.rw = {**REWARD_DEFAULTS, **(reward or {})}
        self.cmd_vlo, self.cmd_vhi = cmd_vx
        mjm = make_mjmodel(mass_scale, xml_path)
        mjd = mujoco.MjData(mjm)
        mujoco.mj_resetDataKeyframe(mjm, mjd, 0)  # "home" keyframe
        mujoco.mj_forward(mjm, mjd)
        self.mjm = mjm
        self.m = mjw.put_model(mjm)
        self.d = mjw.put_data(mjm, mjd, nworld=n_envs, njmax=128)
        # live torch views of the warp sim state
        self.qpos = wp.to_torch(self.d.qpos)            # (n, 19)
        self.qvel = wp.to_torch(self.d.qvel)            # (n, 18)
        self.ctrl = wp.to_torch(self.d.ctrl)            # (n, 12)
        self.qfrc = wp.to_torch(self.d.actuator_force)  # (n, 12)

        dev = self.qpos.device
        self.gen = torch.Generator(device=dev)
        self.gen.manual_seed(seed)
        self.home_q = torch.tensor(mjd.qpos[7:19], dtype=torch.float32,
                                   device=dev)
        self.home_ctrl = torch.tensor(mjd.ctrl, dtype=torch.float32,
                                      device=dev)
        self.ctrl_lo = torch.tensor(mjm.actuator_ctrlrange[:, 0],
                                    dtype=torch.float32, device=dev)
        self.ctrl_hi = torch.tensor(mjm.actuator_ctrlrange[:, 1],
                                    dtype=torch.float32, device=dev)
        self.frange = torch.tensor(
            np.abs(mjm.actuator_forcerange).max(axis=1), dtype=torch.float32,
            device=dev)
        self.last_act = torch.zeros(n_envs, N_JOINTS, device=dev)
        self.cmd = torch.zeros(n_envs, 3, device=dev)
        self.ep_step = torch.zeros(n_envs, dtype=torch.long, device=dev)
        self.auto_reset = auto_reset

    # ------------------------------------------------------------- helpers

    def _rand(self, *shape):
        return torch.rand(*shape, generator=self.gen, device=self.qpos.device)

    def _randn(self, *shape):
        return torch.randn(*shape, generator=self.gen, device=self.qpos.device)

    @staticmethod
    def _rot_inv(quat, v):
        """R(q)^T v batched: world-frame v into body frame. quat (n,4) wxyz."""
        w, x, y, z = quat.unbind(-1)
        vx, vy, vz = v.unbind(-1)
        return torch.stack((
            (1 - 2 * (y * y + z * z)) * vx + 2 * (x * y + w * z) * vy
            + 2 * (x * z - w * y) * vz,
            2 * (x * y - w * z) * vx + (1 - 2 * (x * x + z * z)) * vy
            + 2 * (y * z + w * x) * vz,
            2 * (x * z + w * y) * vx + 2 * (y * z - w * x) * vy
            + (1 - 2 * (x * x + y * y)) * vz), -1)

    def _reset_idx(self, idx):
        if idx.numel() == 0:
            return
        qpos = self.qpos[idx]
        qpos[:, :2] = 0.0
        qpos[:, 2] = 0.27
        qpos[:, 3] = 1.0
        qpos[:, 4:7] = 0.0
        qpos[:, 7:19] = self.home_q + 0.05 * self._randn(idx.numel(), 12)
        self.qvel[idx] = 0.02 * self._randn(idx.numel(), 18)
        self.ctrl[idx] = self.home_ctrl
        self.last_act[idx] = 0.0
        self.ep_step[idx] = 0
        self.cmd[idx, 0] = self.cmd_vlo + (self.cmd_vhi - self.cmd_vlo) \
            * self._rand(idx.numel())
        self.cmd[idx, 1] = 0.0
        self.cmd[idx, 2] = -0.3 + 0.6 * self._rand(idx.numel())

    def reset_all(self):
        self._reset_idx(torch.arange(self.n, device=self.qpos.device))

    # --------------------------------------------------------------- step

    def obs(self):
        quat = self.qpos[:, 3:7]
        grav = self._rot_inv(quat, torch.tensor(
            [0.0, 0.0, -1.0], device=quat.device).expand(quat.shape[0], 3))
        return torch.cat((
            grav,                       # 3
            self.qvel[:, 3:6],          # gyro (body frame) 3
            self.cmd,                   # 3
            self.qpos[:, 7:19] - self.home_q,   # 12
            self.qvel[:, 6:18],         # 12
            self.last_act,              # 12
        ), -1)

    def step(self, act):
        """One control step: PD target update + 10 physics steps.
        Returns (obs, reward, done); finished envs are reset in place."""
        rate = (act - self.last_act).pow(2).sum(-1)
        self.last_act = act.clone()
        target = self.home_ctrl + ACT_SCALE * act
        self.ctrl[:] = torch.clamp(target, self.ctrl_lo, self.ctrl_hi)
        for _ in range(DECIM):
            self.mjw.step(self.m, self.d)
        self.ep_step += 1

        quat = self.qpos[:, 3:7]
        grav = self._rot_inv(quat, torch.tensor(
            [0.0, 0.0, -1.0], device=quat.device).expand(quat.shape[0], 3))
        vw = self.qvel[:, 0:3]                      # trunk linvel, world
        vb = self._rot_inv(quat, vw)                # body-frame linvel
        wz = self.qvel[:, 5]                        # yaw rate (body z)

        rw = self.rw
        lin_err = ((vb[:, 0] - self.cmd[:, 0]) ** 2
                   + (vb[:, 1] - self.cmd[:, 1]) ** 2)
        ang_err = (wz - self.cmd[:, 2]) ** 2
        rew = (
            rw["track_lin"] * torch.exp(-lin_err / rw["sigma"])
            + rw["track_ang"] * torch.exp(-ang_err / 0.25)
            + rw["lin_vel_z"] * vw[:, 2] ** 2
            + rw["ang_vel_xy"] * (self.qvel[:, 3] ** 2 + self.qvel[:, 4] ** 2)
            + rw["orientation"] * (grav[:, 0] ** 2 + grav[:, 1] ** 2)
            + rw["torques"] * (self.qfrc ** 2).sum(-1)
            + rw["action_rate"] * rate
            + rw["alive"]
        )
        fell = (self.qpos[:, 2] < MIN_TRUNK_Z) | (grav[:, 2] > FALL_GZ)
        done = fell | (self.ep_step >= self.episode_steps)
        rew = rew + rw["fall"] * fell.float()
        obs = self.obs()
        if self.auto_reset:
            idx = torch.nonzero(done).squeeze(-1)
            self._reset_idx(idx)
        return obs, rew, done
