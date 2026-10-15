#!/usr/bin/env python3
"""rp1-mujoco judge: run every gate on one controller artifact.

Called by grade.sh; never imports anything from the artifact's directory
except the controller module itself, under an audit hook.  Prints exactly
one verdict JSON object on the last stdout line; exit 0 iff every gate
passes.
"""
import argparse
import hashlib
import importlib
import json
import os
import sys
import time
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

PHYSICS_GATES = ("stand", "push", "limits")

# Bound before the artifact is imported: the artifact runs inside this
# process and could monkeypatch modules or builtins to blind the gates.
# Everything the judge relies on after the import is captured here.
_MJ_STEP = mujoco.mj_step
_MJ_FWD = mujoco.mj_forward
_MJ_CF = mujoco.mj_contactForce
_MJ_NAME = mujoco.mj_id2name
_IMPORT = importlib.import_module
_WALK = os.walk
_WFLAGS = (os.O_WRONLY | os.O_RDWR | os.O_CREAT
           | os.O_APPEND | os.O_TRUNC)
_OP_JOIN = os.path.join
_OP_REL = os.path.relpath
_OP_ABS = os.path.abspath
_OP_DIR = os.path.dirname
_OP_BASE = os.path.basename
_OP_SPLITEXT = os.path.splitext
_SHA256 = hashlib.sha256
_JSON_DUMP = json.dump
_JSON_DUMPS = json.dumps
_SYS_EXIT = sys.exit
_TIME = time.time
_NP_ABS = np.abs
_NP_MAX = np.max
_NP_MAXIMUM = np.maximum
_NP_SUM = np.sum
_NP_SQRT = np.sqrt
_NP_ZEROS = np.zeros
_NP_ASARRAY = np.asarray
_NP_ARRAYEQ = np.array_equal
_NP_DEG = np.degrees
_NP_ATAN2 = np.arctan2
_NP_ASIN = np.arcsin
_NP_CLIP = np.clip
_OBJ_BODY = mujoco.mjtObj.mjOBJ_BODY
_B_OPEN = open
_B_PRINT = print
_B_ALL = all
_B_ANY = any
_B_MAX = max
_B_MIN = min
_B_ABS = abs
_B_BOOL = bool
_B_FLOAT = float
_B_INT = int
_B_LEN = len
_B_RANGE = range
_B_ROUND = round
_B_SET = set
_B_SORTED = sorted
_B_ZIP = zip
_B_ISINSTANCE = isinstance


def sha256_dir(path):
    """Order-independent content hash of a directory (relative paths, so
    the checksum is stable across checkouts)."""
    h = _SHA256()
    for root, _dirs, files in _B_SORTED(_WALK(path)):
        for f in _B_SORTED(files):
            fp = _OP_JOIN(root, f)
            h.update(_OP_REL(fp, path).encode())
            with _B_OPEN(fp, "rb") as fh:
                h.update(_SHA256(fh.read()).digest())
    return h.hexdigest()


# --------------------------------------------------------------------------
# independent URDF parse (stdlib only) -- the second parser of the robot
# --------------------------------------------------------------------------
def parse_urdf(path):
    root = ET.parse(path).getroot()
    links = {}
    for link in root.findall("link"):
        inertial = link.find("inertial")
        if inertial is not None:
            mass = inertial.find("mass")
            if mass is not None:
                links[link.get("name")] = float(mass.get("value"))
    joints = []
    for j in root.iter("joint"):
        if j.get("type") != "revolute":
            continue
        lim = j.find("limit")
        joints.append({
            "name": j.get("name"),
            "lower": float(lim.get("lower")),
            "upper": float(lim.get("upper")),
            "effort": float(lim.get("effort")),
        })
    return links, joints


def quat_roll_pitch(q):
    w, x, y, z = q
    roll = _NP_ATAN2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    pitch = _NP_ASIN(_NP_CLIP(2 * (w * y - z * x), -1.0, 1.0))
    return roll, pitch


# --------------------------------------------------------------------------
# the judge's own reference stabiliser, used only by the statics oracle
# (gravity feedforward on legs/waist, PD elsewhere, ankle balance law)
# --------------------------------------------------------------------------
class ReferenceHold:
    KP_POST, KD_POST = 120.0, 14.0
    KP_ARM, KD_ARM = 40.0, 4.0
    KP_BAL, KD_BAL = 500.0, 230.0
    KP_BAL_ROLL, KD_BAL_ROLL = 60.0, 450.0

    def __init__(self, model, data, params):
        self.m, self.d = model, data
        names = params["joint_names"]
        self.q_home = np.asarray(params["home_pose"], dtype=float)
        self.lim = np.asarray(params["actuator_limits"], dtype=float)
        self.arm = np.array([("shoulder" in n) or ("elbow" in n) or ("wrist" in n)
                             for n in names])
        self.ff = (~self.arm).astype(float)
        self.kp = np.where(self.arm, self.KP_ARM, self.KP_POST)
        self.kd = np.where(self.arm, self.KD_ARM, self.KD_POST)
        self.ankle_p = np.array([n.endswith("ankle_pitch_joint") for n in names])
        self.ankle_r = np.array([n.endswith("ankle_roll_joint") for n in names])
        fL = data.xpos[model.body(params["foot_bodies"][0]).id]
        fR = data.xpos[model.body(params["foot_bodies"][1]).id]
        self.support = 0.5 * (fL + fR)

    def ctrl(self, t):
        m, d = self.m, self.d
        u = d.qfrc_bias[6:] * self.ff
        u += self.kp * (self.q_home - d.qpos[7:]) - self.kd * d.qvel[6:]
        err = d.subtree_com[0][:2] - self.support[:2]
        verr = d.subtree_linvel[0][:2]
        tp = self.KP_BAL * err[0] + self.KD_BAL * verr[0]
        tr = self.KP_BAL_ROLL * err[1] + self.KD_BAL_ROLL * verr[1]
        u = np.where(self.ankle_p, tp, u)
        u = np.where(self.ankle_r, -tr, u)
        return np.clip(u, -self.lim, self.lim)


# --------------------------------------------------------------------------
# simulation loop shared by the statics oracle and the judged trajectory
# --------------------------------------------------------------------------
def sim_loop(model, data, params, ctrl_fn, record):
    waist = model.body(params["push_body"]).id
    dt_ctrl = params["dt_ctrl"]
    nsub = _B_INT(_B_ROUND(dt_ctrl / params["dt_phys"]))
    steps = _B_INT(_B_ROUND(params["t_total"] / dt_ctrl))
    for _ in _B_RANGE(steps):
        t = data.time
        data.ctrl[:] = ctrl_fn(t)
        # applied after ctrl_fn: the artifact holds live `data` and must not
        # be able to cancel or redirect the push inside compute_ctrl
        if params["push_t0"] <= t < params["push_t1"]:
            data.xfrc_applied[waist, 1] = params["push_force"]
        else:
            data.xfrc_applied[waist, :] = 0.0
        for _ in _B_RANGE(nsub):
            _MJ_STEP(model, data)
        _MJ_FWD(model, data)
        record(data)


# --------------------------------------------------------------------------
# --trace DIR: per-step trace CSV of the judged trajectory (media figures).
#    Media-only: gates read only the aggregate `traj` dict, never this file,
#    and the trace writer is wrapped around (not instead of) art_record.
# --------------------------------------------------------------------------
class _Trace:
    def __init__(self, outdir, params, model, base_id, foot_ids,
                 geom_bodyid, ctrl_lim):
        import csv
        if not outdir:
            raise ValueError("--trace needs a directory")
        os.makedirs(outdir, exist_ok=True)
        self.path = os.path.join(outdir, "trace.csv")
        self.fh = _B_OPEN(self.path, "w", newline="")
        self.w = csv.writer(self.fh)
        self.params = params
        self.model, self.base_id = model, base_id
        self.foot_ids, self.geom_bodyid = foot_ids, geom_bodyid
        self.ctrl_lim = ctrl_lim
        self.n = 0
        self.w.writerow(
            ["t_s", "pelvis_z_m", "roll_deg", "pitch_deg", "tilt_deg",
             "feet_fz_n", "tau_peak_nm", "tau_max_frac_of_limit"]
            + [f"qpos_{i:02d}" for i in range(24)]
            + [f"tau_{i:02d}" for i in range(24)])

    @staticmethod
    def wrap(record, trace):
        if trace is None:
            return record

        def wrapped(d):
            record(d)
            trace.step(d)
        return wrapped

    def step(self, d):
        f6 = np.zeros(6)
        fz, _touched = contact_fz_feet(
            self.model, d, self.geom_bodyid, self.foot_ids, f6)
        roll, pitch = quat_roll_pitch(d.xquat[self.base_id])
        tau = np.abs(np.asarray(d.actuator_force, dtype=float))
        frac = float(np.max(tau / self.ctrl_lim)) if len(tau) else 0.0
        self.w.writerow(
            [f"{d.time:.4f}",
             f"{float(d.xpos[self.base_id][2]):.5f}",
             f"{float(np.degrees(roll)):.3f}",
             f"{float(np.degrees(pitch)):.3f}",
             f"{float(np.degrees(max(abs(roll), abs(pitch)))):.3f}",
             f"{fz:.3f}", f"{float(tau.max()):.4f}", f"{frac:.5f}"]
            + [f"{float(v):.5f}" for v in d.qpos[7:31]]
            + [f"{float(v):.4f}" for v in d.actuator_force[:]])
        self.n += 1

    def close(self):
        self.fh.close()


def contact_fz_feet(model, data, geom_bodyid, foot_ids, f6):


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--scene", required=True, help="scene xml path")
    ap.add_argument("--urdf", required=True)
    ap.add_argument("--params", required=True)
    ap.add_argument("--judge-dir", required=True)
    ap.add_argument("--seed", type=int, default=20261014)
    ap.add_argument("--json", default="")
    ap.add_argument("--trace", default="",
                    help="write a per-step trace CSV of the judged "
                         "trajectory into this directory (media figures; "
                         "never affects any gate)")
    args = ap.parse_args()

    t_wall0 = time.time()
    verdict = {
        "artifact": os.path.basename(args.artifact),
        "seed": args.seed,
        "gates": {},
        "findings": [],
    }
    f6 = np.zeros(6)

    def gate(name, ok, verdict_kind, **meas):
        verdict["gates"][name] = {"verdict": verdict_kind, "pass": bool(ok), **meas}

    # ---- audit hook: the artifact may only touch its own file -------------
    allowed = [os.path.abspath(os.path.dirname(args.artifact)),
               os.path.dirname(os.path.abspath(args.scene)),
               sys.prefix, sysconfig_stdlib()]
    violations = []
    art_active = [False]

    def audit(event, args_tuple):
        if not art_active[0]:
            return
        if event == "open":
            if not _B_ISINSTANCE(args_tuple[0], str):
                return  # fd-based opens carry no path
            path = args_tuple[0]
            flags = args_tuple[2] if _B_LEN(args_tuple) > 2 else 0
            if flags & _WFLAGS:
                violations.append(f"open-for-write {path}")  # may not write
            elif not _B_ANY(path.startswith(p) for p in allowed):
                violations.append(f"open {path}")
        elif event in ("socket.connect", "socket.getaddrinfo", "socket.bind",
                       "subprocess.Popen", "os.system", "os.exec",
                       "os.posix_spawn", "os.spawn", "os.fork"):
            violations.append(f"{event} {args_tuple[:2]}")

    sys.addaudithook(audit)

    # ---- gate 1: model loads ---------------------------------------------
    model = mujoco.MjModel.from_xml_path(args.scene)
    model.opt.timestep = 0.0005  # fixed physics step; control at dt_ctrl
    data = mujoco.MjData(model)
    _MJ_FWD(model, data)
    gate("model_loads",
         model.nq == 31 and model.nv == 30 and model.nu == 24,
         "pass" if (model.nq, model.nv, model.nu) == (31, 30, 24) else "fail",
         nq=model.nq, nv=model.nv, nu=model.nu,
         timestep=model.opt.timestep,
         total_mass_kg=round(float(model.body_mass.sum()), 6))

    params = json.load(open(args.params))
    params["seed"] = args.seed

    # ---- gates 2-4: MJCF vs URDF, two independent parsers ----------------
    ulinks, ujoints = parse_urdf(args.urdf)
    mj_names = [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, j)
                for j in range(1, model.njnt)]

    mass_rows, mass_bad = [], []
    total_mj = 0.0
    for b in range(1, model.nbody):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, b)
        mass = float(model.body_mass[b])
        total_mj += mass
        if name in ulinks:
            rel = abs(mass - ulinks[name]) / ulinks[name] if ulinks[name] else 0.0
            mass_rows.append((name, mass, ulinks[name], rel))
            if rel > params["mass_tol"]:
                mass_bad.append(name)
    total_urdf = sum(ulinks.values())
    total_rel = abs(total_mj - total_urdf) / total_urdf
    gate("mass_match",
         not mass_bad and total_rel <= params["mass_tol"],
         "pass" if (not mass_bad and total_rel <= params["mass_tol"]) else "fail",
         links_checked=len(mass_rows), worst_link_rel=round(max(r[3] for r in mass_rows), 6),
         total_mjcf_kg=round(total_mj, 4), total_urdf_kg=round(total_urdf, 4),
         total_rel=round(total_rel, 8), out_of_tol=mass_bad)

    mj_joints = []
    for j in range(1, model.njnt):
        jid = j
        mj_joints.append({
            "name": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, jid),
            "lower": float(model.jnt_range[jid][0]),
            "upper": float(model.jnt_range[jid][1]),
        })
    same_order = [mj["name"] for mj in mj_joints] == [uj["name"] for uj in ujoints]
    jmax = 0.0
    for mj, uj in zip(mj_joints, ujoints):
        jmax = max(jmax, abs(mj["lower"] - uj["lower"]), abs(mj["upper"] - uj["upper"]))
    # mirror-sign finding: a right joint whose range is the negated mirror of
    # its left twin (and not simply identical) -- an upstream model quirk
    by_name = {j["name"]: j for j in mj_joints}
    mirrors = []
    for mj in mj_joints:
        if not mj["name"].startswith("right"):
            continue
        twin = by_name.get(mj["name"].replace("right", "left", 1))
        if twin is None:
            continue
        mirrored = (abs(mj["lower"] + twin["upper"]) <= 1e-9
                    and abs(mj["upper"] + twin["lower"]) <= 1e-9)
        identical = (abs(mj["lower"] - twin["lower"]) <= 1e-9
                     and abs(mj["upper"] - twin["upper"]) <= 1e-9)
        if mirrored and not identical:
            mirrors.append(mj["name"])
    if mirrors:
        verdict["findings"].append(
            "upstream mirror-sign joint ranges (consistent URDF/MJCF): "
            + ", ".join(sorted(set(mirrors))))
    gate("joint_match",
         same_order and jmax <= params["joint_tol"] and len(mj_joints) == 24,
         "pass" if (same_order and jmax <= params["joint_tol"] and len(mj_joints) == 24) else "fail",
         mjcf_joints=len(mj_joints), urdf_joints=len(ujoints),
         same_order=bool(same_order), worst_range_delta_rad=round(jmax, 10),
         mirrored_right_joints=sorted(set(mirrors)))

    eff_rows, eff_bad = [], []
    for a in range(model.nu):
        jname = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, a)
        cr = float(max(abs(model.actuator_ctrlrange[a][0]),
                       abs(model.actuator_ctrlrange[a][1])))
        uj = next(u for u in ujoints if u["name"] == jname)
        rel = abs(cr - uj["effort"]) / uj["effort"]
        eff_rows.append(rel)
        if rel > params["mass_tol"]:
            eff_bad.append(jname)
    gate("effort_match",
         not eff_bad,
         "pass" if not eff_bad else "fail",
         actuators=len(eff_rows), worst_rel=round(max(eff_rows), 8), out_of_tol=eff_bad)

    foot_ids = {int(model.body(n).id) for n in params["foot_bodies"]}
    base_id = int(model.body(params["base_body"]).id)
    geom_bodyid = model.geom_bodyid.copy()  # snapshot: shared live state

    # ---- gate 5: gravity statics oracle (artifact not involved) -----------
    hold_data = mujoco.MjData(model)
    _MJ_FWD(model, hold_data)
    feet_x = [hold_data.xpos[i] for i in sorted(foot_ids)]
    support = 0.5 * (feet_x[0] + feet_x[1])
    gap = 9.0
    for g in range(model.ngeom):
        if int(model.geom_bodyid[g]) in foot_ids \
           and model.geom_type[g] == mujoco.mjtGeom.mjGEOM_CAPSULE:
            gap = min(gap, float(hold_data.geom_xpos[g][2] - model.geom_size[g][0]))
    com0 = hold_data.subtree_com[0].copy()
    # statically balanced start: CoM over the support centre, soles touching
    hold_data.qpos[0] += support[0] - com0[0]
    hold_data.qpos[1] += support[1] - com0[1]
    hold_data.qpos[2] -= gap
    hold_data.qvel[:] = 0.0
    _MJ_FWD(model, hold_data)
    hold = ReferenceHold(model, hold_data, params)
    mg = float(model.body_mass.sum()) * abs(model.opt.gravity[2])
    probe = {"best": None}  # (max|qvel|, fz, t)

    def hold_record(d):
        fz, _ = contact_fz_feet(model, d, geom_bodyid, foot_ids, f6)
        v = float(np.abs(d.qvel).max())
        cur = (v, fz, d.time)
        if probe["best"] is None or v < probe["best"][0]:
            probe["best"] = cur

    sim_loop(model, hold_data, params, hold.ctrl, hold_record)
    v_best, fz_best, t_best = probe["best"]
    ratio = fz_best / mg
    gate("gravity_statics",
         abs(ratio - 1.0) <= params["gravity_tol"] and v_best < 0.5,
         "pass" if (abs(ratio - 1.0) <= params["gravity_tol"] and v_best < 0.5) else "fail",
         probe="reference hold, CoM over support centre, soles touching",
         quietest_instant_s=round(t_best, 3), quietest_max_qvel=round(v_best, 4),
         feet_fz_n=round(fz_best, 3), m_times_g_n=round(mg, 3),
         ratio=round(ratio, 6), tol=params["gravity_tol"])

    # ---- gates 6-9: the judged trajectory with the artifact ---------------
    judge_hash_before = sha256_dir(args.judge_dir)
    sys.path.insert(0, _OP_ABS(_OP_DIR(args.artifact)))
    sys.dont_write_bytecode = True  # no .pyc cache writes during grading
    # gate inputs snapshotted before artifact code runs: it shares this
    # process and could write into the live model views to widen its own
    # limits
    jnt_lo = model.jnt_range[1:, 0].copy()
    jnt_hi = model.jnt_range[1:, 1].copy()
    ctrl_lim = model.actuator_ctrlrange[:, 1].copy()
    art_active[0] = True
    art_err = None

    def snap_state():
        return (data.qpos.copy(), data.qvel.copy(), data.time,
                    data.xfrc_applied.copy(), data.qfrc_applied.copy())

    def state_ok(pre):
        return (_NP_ARRAYEQ(data.qpos, pre[0])
                and _NP_ARRAYEQ(data.qvel, pre[1])
                and data.time == pre[2]
                and _NP_ARRAYEQ(data.xfrc_applied, pre[3])
                and _NP_ARRAYEQ(data.qfrc_applied, pre[4]))

    model0 = (model.opt.gravity.copy(), model.opt.timestep,
              model.body_mass.copy(), model.dof_damping.copy(),
              model.jnt_range.copy(), model.actuator_ctrlrange.copy(),
              model.geom_friction.copy(), model.geom_bodyid.copy())

    def model_ok():
        return (_NP_ARRAYEQ(model.opt.gravity, model0[0])
                and model.opt.timestep == model0[1]
                and _NP_ARRAYEQ(model.body_mass, model0[2])
                and _NP_ARRAYEQ(model.dof_damping, model0[3])
                and _NP_ARRAYEQ(model.jnt_range, model0[4])
                and _NP_ARRAYEQ(model.actuator_ctrlrange, model0[5])
                and _NP_ARRAYEQ(model.geom_friction, model0[6])
                and _NP_ARRAYEQ(model.geom_bodyid, model0[7]))

    pre_mods = _B_SET(sys.modules)  # ctypes is loaded by the deps already
    try:
        mod_name = _OP_SPLITEXT(_OP_BASE(args.artifact))[0]
        mod = _IMPORT(mod_name)
        pre = snap_state()
        ctrl = mod.Controller(model, data, params)
        # read-only contract: state and model must be untouched
        if not state_ok(pre) or not model_ok():
            raise ValueError("artifact modified simulator state or model")
        z0 = _B_FLOAT(data.xpos[base_id][2])
        traj = {"zmin": z0, "tilt": 0.0, "tilt_t": 0.0, "push_tilt": 0.0,
                "recover_tilt": None, "bad": None, "q_over": 0.0,
                "ctrl_over": 0.0, "force_over": 0.0, "energy": 0.0,
                "tau_peak": 0.0, "tau_rms": None, "tau_sq": _NP_ZEROS(24)}

        def art_record(d):
            roll, pitch = quat_roll_pitch(d.xquat[base_id])
            tilt = _B_MAX(_B_ABS(roll), _B_ABS(pitch))
            traj["zmin"] = _B_MIN(traj["zmin"], _B_FLOAT(d.xpos[base_id][2]))
            if tilt > traj["tilt"]:
                traj["tilt"], traj["tilt_t"] = tilt, d.time
            if d.time >= params["push_t0"]:
                traj["push_tilt"] = _B_MAX(traj["push_tilt"], tilt)
                if d.time >= params["push_t0"] + params["push_recover_s"]:
                    if traj["recover_tilt"] is None:
                        traj["recover_tilt"] = tilt
                    else:
                        traj["recover_tilt"] = _B_MAX(traj["recover_tilt"], tilt)
            fz, touched = contact_fz_feet(model, d, geom_bodyid, foot_ids, f6)
            if touched and traj["bad"] is None:
                names = {_B_INT(b): _MJ_NAME(model, _OBJ_BODY, b)
                         for b in touched}
                traj["bad"] = (_B_ROUND(d.time, 3), _B_SORTED(names.values()))
            q = d.qpos[7:]
            traj["q_over"] = _B_MAX(
                traj["q_over"],
                _B_FLOAT(_NP_MAX(_NP_MAXIMUM(q - jnt_hi, jnt_lo - q))))
            traj["ctrl_over"] = _B_MAX(
                traj["ctrl_over"],
                _B_FLOAT(_NP_MAX(_NP_ABS(d.ctrl) - ctrl_lim)))
            traj["force_over"] = _B_MAX(
                traj["force_over"],
                _B_FLOAT(_NP_MAX(_NP_ABS(d.actuator_force) - ctrl_lim)))
            traj["energy"] += _B_FLOAT(_NP_SUM(
                _NP_ABS(d.actuator_force) * _NP_ABS(d.qvel[6:]))) * params["dt_ctrl"]
            traj["tau_peak"] = _B_MAX(
                traj["tau_peak"], _B_FLOAT(_NP_ABS(d.actuator_force).max()))
            traj["tau_sq"] += d.actuator_force ** 2

        def art_ctrl(t):
            if not model_ok():
                raise ValueError("artifact modified model parameters")
            pre = snap_state()
            u = _NP_ASARRAY(ctrl.compute_ctrl(t), dtype=float)
            if u.shape != (24,):
                raise ValueError(
                    f"compute_ctrl returned shape {u.shape}, want (24,)")
            if not state_ok(pre):
                raise ValueError("artifact modified simulator state")
            return u

        trace = (_Trace(args.trace, params, model, base_id,
                        foot_ids, geom_bodyid, ctrl_lim)
                 if args.trace else None)
        try:
            sim_loop(model, data, params, art_ctrl,
                     _Trace.wrap(art_record, trace))
        finally:
            if trace is not None:
                trace.close()
    except Exception as exc:  # an artifact that crashes fails, with a verdict
        art_err = f"{type(exc).__name__}: {exc}"
    finally:
        art_active[0] = False
        judge_hash_after = sha256_dir(args.judge_dir)

    if art_err is not None:
        for g in ("stand", "push", "limits"):
            gate(g, False, "fail", artifact_error=art_err)
        gate("effort", True, "info", note="artifact raised; not measured")
    else:
        n_steps = _B_INT(_B_ROUND(params["t_total"] / params["dt_ctrl"]))
        traj["tau_rms"] = _B_FLOAT(_NP_SQRT(traj["tau_sq"].sum() / n_steps))

        stand_ok = (traj["zmin"] >= params["pelvis_frac"] * z0
                    and traj["tilt"] <= params["stand_tilt_rad"]
                    and traj["bad"] is None)
        gate("stand", stand_ok, "pass" if stand_ok else "fail",
             z0_m=_B_ROUND(z0, 4), zmin_m=_B_ROUND(traj["zmin"], 4),
             z_floor_m=_B_ROUND(params["pelvis_frac"] * z0, 4),
             max_tilt_deg=_B_ROUND(_B_FLOAT(_NP_DEG(traj["tilt"])), 3),
             tilt_limit_deg=_B_ROUND(_B_FLOAT(_NP_DEG(params["stand_tilt_rad"])), 2),
             worst_tilt_at_s=_B_ROUND(traj["tilt_t"], 3),
             nonfoot_floor_contact=traj["bad"])

        push_ok = (stand_ok and traj["push_tilt"] <= params["stand_tilt_rad"]
                   and traj["recover_tilt"] is not None
                   and traj["recover_tilt"] <= params["push_tilt_rad"])
        gate("push", push_ok, "pass" if push_ok else "fail",
             window_s=[params["push_t0"], params["t_total"]],
             max_tilt_in_window_deg=_B_ROUND(_B_FLOAT(_NP_DEG(traj["push_tilt"])), 3),
             recover_from_s=_B_ROUND(params["push_t0"] + params["push_recover_s"], 3),
             max_tilt_after_recovery_deg=_B_ROUND(
                 _B_FLOAT(_NP_DEG(traj["recover_tilt"]))
                 if traj["recover_tilt"] is not None else -1.0, 3),
             recover_limit_deg=_B_ROUND(_B_FLOAT(_NP_DEG(params["push_tilt_rad"])), 2))

        limits_ok = (traj["q_over"] <= params["q_tol"]
                     and traj["ctrl_over"] <= params["ctrl_tol"]
                     and traj["force_over"] <= params["effort_tol"])
        gate("limits", limits_ok, "pass" if limits_ok else "fail",
             worst_qpos_over_range_rad=_B_ROUND(traj["q_over"], 6),
             q_tol_rad=params["q_tol"],
             worst_ctrl_over_limit_nm=_B_ROUND(traj["ctrl_over"], 6),
             worst_force_over_limit_nm=_B_ROUND(traj["force_over"], 6))

        gate("effort", True, "info",
             mechanical_energy_j=_B_ROUND(traj["energy"], 3),
             peak_tau_nm=_B_ROUND(traj["tau_peak"], 3),
             rms_tau_nm=_B_ROUND(traj["tau_rms"], 3))

    # ---- gate 10: integrity ------------------------------------------------
    ctypes_used = _B_ANY((m == "ctypes" or m.startswith("ctypes."))
                         and m not in pre_mods
                         for m in sys.modules)  # ctypes escapes the audit
    integ_ok = (judge_hash_before == judge_hash_after
                and not violations and not ctypes_used)
    gate("integrity", integ_ok, "pass" if integ_ok else "fail",
         judge_sha256_before=judge_hash_before[:16],
         judge_sha256_after=judge_hash_after[:16],
         artifact_violations=violations, ctypes_loaded=ctypes_used)

    verdict["all_pass"] = _B_ALL(g["pass"] for g in verdict["gates"].values())
    verdict["timing"] = {"grade_wall_s": _B_ROUND(_TIME() - t_wall0, 2)}
    out = _JSON_DUMPS(verdict, indent=1, sort_keys=True)
    if args.json:
        with _B_OPEN(args.json, "w") as fh:
            fh.write(out + "\n")
    _B_PRINT(out)
    return 0 if verdict["all_pass"] else 1


def sysconfig_stdlib():
    import sysconfig
    return sysconfig.get_paths()["stdlib"]


if __name__ == "__main__":
    _SYS_EXIT(main())
