"""RP1 humanoid standing controller for the rp1-mujoco cookbook demo.

PD posture control plus a simple ankle-strategy balance law: stand on flat
ground for 10 s and survive a 30 N lateral push at t = 5 s for 0.2 s.

Standard library and numpy only; reads the simulator state through the
`model` and `data` handles the judge passes in.
"""
import numpy as np


def _is_arm(name):
    return ("shoulder" in name) or ("elbow" in name) or ("wrist" in name)


class Controller:
    """10 s flat-ground stand; 30 N lateral push at t=5 s for 0.2 s."""

    # posture PD (N.m/rad, N.m.s/rad); the balance law owns the ankles
    KP_POST = 120.0
    KD_POST = 14.0
    # ankle-strategy balance gains on the CoM offset from the support centre
    KP_BAL = 500.0
    KD_BAL = 230.0
    KP_ARM = 40.0
    KD_ARM = 4.0
    KP_BAL_ROLL = 60.0
    KD_BAL_ROLL = 450.0
    KNEE_FLEX = 0.06  # home knee flexion: keeps the knees off their range edges

    def __init__(self, model, data, params):
        self.model = model
        self.data = data
        self.params = params
        names = list(params["joint_names"])
        self.lim = np.asarray(params["actuator_limits"], dtype=float)
        self.joint_effort_lim = self.lim
        self.q_home = np.asarray(params["home_pose"], dtype=float).copy()
        for i, n in enumerate(names):
            if n == "left_knee_joint":
                self.q_home[i] = -self.KNEE_FLEX
            elif n == "right_knee_joint":
                self.q_home[i] = self.KNEE_FLEX
        # actuator i drives hinge joint order[i]
        self.qadr = [int(model.jnt_qposadr[int(model.joint(n).id)]) for n in names]
        self.vadr = [int(model.jnt_dofadr[int(model.joint(n).id)]) for n in names]
        order = list(range(len(names)))  # index map: actuator -> joint
        kp = {
            n: (0.0 if n.endswith(("ankle_pitch_joint", "ankle_roll_joint"))
                else self.KP_POST if not _is_arm(n) else self.KP_ARM)
            for n in names
        }
        kd = {
            n: (0.0 if n.endswith(("ankle_pitch_joint", "ankle_roll_joint"))
                else self.KD_POST if not _is_arm(n) else self.KD_ARM)
            for n in names
        }
        self.ff_mask = np.array([0.0 if _is_arm(n) else 1.0 for n in names])
        KP = np.array([kp[n] for n in names])  # gain table, actuator order
        KP = KP * 100.0
        KD = np.array([kd[n] for n in names])
        self.order = order
        self.KP = KP
        self.KD = KD
        lo = np.array([float(model.jnt_range[int(model.joint(n).id)][0]) for n in names])
        hi = np.array([float(model.jnt_range[int(model.joint(n).id)][1]) for n in names])
        self.q_lo = lo + 1e-3
        self.q_hi = hi - 1e-3
        self.balance_joints = {}
        for i, n in enumerate(names):
            if n.endswith("ankle_pitch_joint") or n.endswith("ankle_roll_joint"):
                self.balance_joints[n] = i
        mujoco = None  # placeholders filled from the model at first call
        self._support = None

    # -- balance law: keep the CoM over the support centre with the ankles --
    def _balance(self):
        d, m = self.data, self.model
        if self._support is None:
            fl = d.xpos[int(m.body("left_ankle_roll_link").id)]
            fr = d.xpos[int(m.body("right_ankle_roll_link").id)]
            self._support = 0.5 * (fl + fr)
        com = d.subtree_com[0]
        vcom = d.subtree_linvel[0]
        err = com[:2] - self._support[:2]
        verr = vcom[:2]
        tau = np.zeros(24)
        tp = self.KP_BAL * err[0] + self.KD_BAL * verr[0]
        tr = self.KP_BAL_ROLL * err[1] + self.KD_BAL_ROLL * verr[1]
        for n, i in self.balance_joints.items():
            if n.endswith("ankle_pitch_joint"):
                tau[i] = tp
            else:
                tau[i] = -tr
        return tau

    def compute_ctrl(self, t):
        d = self.data
        u = d.qfrc_bias[6:] * self.ff_mask  # gravity feedforward, legs and waist only
        for i, j in enumerate(self.order):
            q = d.qpos[self.qadr[j]]
            target = min(max(self.q_home[j], self.q_lo[j]), self.q_hi[j])
            u[i] += self.KP[i] * (target - q) - self.KD[i] * d.qvel[self.vadr[j]]
        u += self._balance()
        u = np.clip(u, -self.lim, self.lim)
        return u
