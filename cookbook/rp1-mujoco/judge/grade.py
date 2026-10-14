#!/usr/bin/env python3
"""rp1-mujoco judge: run every gate on one controller artifact.

Called by grade.sh; never imports anything from the artifact's directory
except the controller module itself, under an audit hook.  Prints exactly
one verdict JSON object on the last stdout line; exit 0 iff every gate
passes.
"""
import argparse
import hashlib
import json
import os
import sys
import time
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

PHYSICS_GATES = ("stand", "push", "limits")


def sha256_dir(path):
    h = hashlib.sha256()
    for root, _dirs, files in sorted(os.walk(path)):
        for f in sorted(files):
            fp = os.path.join(root, f)
            h.update(fp.encode())
            with open(fp, "rb") as fh:
                h.update(hashlib.sha256(fh.read()).digest())
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
    roll = np.arctan2(2 * (w * x + y * z), 1 - 2 * (x * x + y * y))
    pitch = np.arcsin(np.clip(2 * (w * y - z * x), -1.0, 1.0))
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
    nsub = int(round(dt_ctrl / model.opt.timestep))
    steps = int(round(params["t_total"] / dt_ctrl))
    for _ in range(steps):
        t = data.time
        if params["push_t0"] <= t < params["push_t1"]:
            data.xfrc_applied[waist, 1] = params["push_force"]
        else:
            data.xfrc_applied[waist, :] = 0.0
        data.ctrl[:] = ctrl_fn(t)
        for _ in range(nsub):
            mujoco.mj_step(model, data)
        mujoco.mj_forward(model, data)
        record(data)


def contact_fz_feet(model, data, foot_ids, f6):
    """Total vertical contact force on the feet; also floor-contact bodies."""
    fz = 0.0
    touched = set()
    for ci in range(data.ncon):
        con = data.contact[ci]
        b1, b2 = int(model.geom_bodyid[con.geom1]), int(model.geom_bodyid[con.geom2])
        if (b1 == 0) != (b2 == 0):
            other = b2 if b1 == 0 else b1
            mujoco.mj_contactForce(model, data, ci, f6)
            if other in foot_ids:
                fz += abs(f6[0] * con.frame[2])
            else:
                touched.add(other)
    return fz, touched


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--scene", required=True, help="scene xml path")
    ap.add_argument("--urdf", required=True)
    ap.add_argument("--params", required=True)
    ap.add_argument("--judge-dir", required=True)
    ap.add_argument("--seed", type=int, default=20261014)
    ap.add_argument("--json", default="")
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
            if not isinstance(args_tuple[0], str):
                return  # fd-based opens carry no path
            path = args_tuple[0]
            if not any(path.startswith(p) for p in allowed):
                violations.append(f"open {path}")
        elif event in ("socket.connect", "socket.getaddrinfo", "socket.bind",
                       "subprocess.Popen", "os.system"):
            violations.append(f"{event} {args_tuple[:2]}")

    sys.addaudithook(audit)

    # ---- gate 1: model loads ---------------------------------------------
    model = mujoco.MjModel.from_xml_path(args.scene)
    model.opt.timestep = 0.0005  # fixed physics step; control at dt_ctrl
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
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

    # ---- gate 5: gravity statics oracle (artifact not involved) -----------
    hold_data = mujoco.MjData(model)
    mujoco.mj_forward(model, hold_data)
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
    mujoco.mj_forward(model, hold_data)
    hold = ReferenceHold(model, hold_data, params)
    mg = float(model.body_mass.sum()) * abs(model.opt.gravity[2])
    probe = {"best": None}  # (max|qvel|, fz, t)

    def hold_record(d):
        fz, _ = contact_fz_feet(model, d, foot_ids, f6)
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
    sys.path.insert(0, os.path.abspath(os.path.dirname(args.artifact)))
    art_active[0] = True
    try:
        import importlib
        mod_name = os.path.splitext(os.path.basename(args.artifact))[0]
        mod = importlib.import_module(mod_name)
        ctrl = mod.Controller(model, data, params)
        z0 = float(data.xpos[base_id][2])
        traj = {"zmin": z0, "tilt": 0.0, "tilt_t": 0.0, "push_tilt": 0.0,
                "recover_tilt": None, "bad": None, "q_over": 0.0,
                "ctrl_over": 0.0, "force_over": 0.0, "energy": 0.0,
                "tau_peak": 0.0, "tau_rms": None, "tau_sq": np.zeros(24)}

        def art_record(d):
            roll, pitch = quat_roll_pitch(d.xquat[base_id])
            tilt = max(abs(roll), abs(pitch))
            traj["zmin"] = min(traj["zmin"], float(d.xpos[base_id][2]))
            if tilt > traj["tilt"]:
                traj["tilt"], traj["tilt_t"] = tilt, d.time
            if d.time >= params["push_t0"]:
                traj["push_tilt"] = max(traj["push_tilt"], tilt)
                if d.time >= params["push_t0"] + params["push_recover_s"]:
                    if traj["recover_tilt"] is None:
                        traj["recover_tilt"] = tilt
                    else:
                        traj["recover_tilt"] = max(traj["recover_tilt"], tilt)
            fz, touched = contact_fz_feet(model, d, foot_ids, f6)
            if touched and traj["bad"] is None:
                names = {int(b): mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, b)
                         for b in touched}
                traj["bad"] = (round(d.time, 3), sorted(names.values()))
            q = d.qpos[7:]
            lo, hi = model.jnt_range[1:, 0], model.jnt_range[1:, 1]
            traj["q_over"] = max(traj["q_over"],
                                 float(np.max(np.maximum(q - hi, lo - q))))
            lim = model.actuator_ctrlrange[:, 1]
            traj["ctrl_over"] = max(traj["ctrl_over"],
                                    float(np.max(np.abs(d.ctrl) - lim)))
            traj["force_over"] = max(
                traj["force_over"],
                float(np.max(np.abs(d.actuator_force) - lim)))
            traj["energy"] += float(np.sum(
                np.abs(d.actuator_force) * np.abs(d.qvel[6:]))) * params["dt_ctrl"]
            traj["tau_peak"] = max(traj["tau_peak"],
                                   float(np.abs(d.actuator_force).max()))
            traj["tau_sq"] += d.actuator_force ** 2

        def art_ctrl(t):
            u = np.asarray(ctrl.compute_ctrl(t), dtype=float)
            if u.shape != (24,):
                raise ValueError(f"compute_ctrl returned shape {u.shape}, want (24,)")
            return u

        sim_loop(model, data, params, art_ctrl, art_record)
    finally:
        art_active[0] = False
        judge_hash_after = sha256_dir(args.judge_dir)

    n_steps = int(round(params["t_total"] / params["dt_ctrl"]))
    traj["tau_rms"] = float(np.sqrt(traj["tau_sq"].sum() / n_steps))

    stand_ok = (traj["zmin"] >= params["pelvis_frac"] * z0
                and traj["tilt"] <= params["stand_tilt_rad"]
                and traj["bad"] is None)
    gate("stand", stand_ok, "pass" if stand_ok else "fail",
         z0_m=round(z0, 4), zmin_m=round(traj["zmin"], 4),
         z_floor_m=round(params["pelvis_frac"] * z0, 4),
         max_tilt_deg=round(float(np.degrees(traj["tilt"])), 3),
         tilt_limit_deg=round(float(np.degrees(params["stand_tilt_rad"])), 2),
         worst_tilt_at_s=round(traj["tilt_t"], 3),
         nonfoot_floor_contact=traj["bad"])

    push_ok = (stand_ok and traj["push_tilt"] <= params["stand_tilt_rad"]
               and traj["recover_tilt"] is not None
               and traj["recover_tilt"] <= params["push_tilt_rad"])
    gate("push", push_ok, "pass" if push_ok else "fail",
         window_s=[params["push_t0"], params["t_total"]],
         max_tilt_in_window_deg=round(float(np.degrees(traj["push_tilt"])), 3),
         recover_from_s=round(params["push_t0"] + params["push_recover_s"], 3),
         max_tilt_after_recovery_deg=round(
             float(np.degrees(traj["recover_tilt"]))
             if traj["recover_tilt"] is not None else -1.0, 3),
         recover_limit_deg=round(float(np.degrees(params["push_tilt_rad"])), 2))

    limits_ok = (traj["q_over"] <= params["q_tol"]
                 and traj["ctrl_over"] <= params["ctrl_tol"]
                 and traj["force_over"] <= params["effort_tol"])
    gate("limits", limits_ok, "pass" if limits_ok else "fail",
         worst_qpos_over_range_rad=round(traj["q_over"], 6),
         q_tol_rad=params["q_tol"],
         worst_ctrl_over_limit_nm=round(traj["ctrl_over"], 6),
         worst_force_over_limit_nm=round(traj["force_over"], 6))

    gate("effort", True, "info",
         mechanical_energy_j=round(traj["energy"], 3),
         peak_tau_nm=round(traj["tau_peak"], 3),
         rms_tau_nm=round(traj["tau_rms"], 3))

    # ---- gate 10: integrity ------------------------------------------------
    integ_ok = judge_hash_before == judge_hash_after and not violations
    gate("integrity", integ_ok, "pass" if integ_ok else "fail",
         judge_sha256_before=judge_hash_before[:16],
         judge_sha256_after=judge_hash_after[:16],
         artifact_violations=violations)

    verdict["all_pass"] = all(g["pass"] for g in verdict["gates"].values())
    verdict["timing"] = {"grade_wall_s": round(time.time() - t_wall0, 2)}
    out = json.dumps(verdict, indent=1, sort_keys=True)
    if args.json:
        with open(args.json, "w") as fh:
            fh.write(out + "\n")
    print(out)
    return 0 if verdict["all_pass"] else 1


def sysconfig_stdlib():
    import sysconfig
    return sysconfig.get_paths()["stdlib"]


if __name__ == "__main__":
    sys.exit(main())
