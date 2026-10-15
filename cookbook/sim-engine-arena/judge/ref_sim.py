"""Reference MuJoCo port of the sim-engine-arena scene spec (judge-owned).

This is the judge's own port of judge/spec.json into MuJoCo, run every grade
under a judge-controlled seed. The agent's artifact is compared with this as
the cross-engine agreement check (SPEC gate 5). It reads the same spec the
agent gets and contains no oracle values.

Usage: python ref_sim.py <spec.json> <outdir> [--seed N]
Writes <outdir>/traj_<scenario>.csv and <outdir>/model_<scenario>.xml.
"""

import argparse
import csv
import json
import math
import os

import mujoco
import numpy as np

MJCF = """<mujoco model="arena-{name}">
  <option gravity="0 0 -{g}" timestep="{dt}"/>
  {bodies}
</mujoco>
"""

BODIES_DROP = """  <worldbody>
    <geom name="floor" type="plane" size="5 5 0.1" pos="0 0 0" friction="1 1 0.001"/>
    <body name="mover" pos="{pos}">
      <freejoint/>
      <geom name="ball" type="sphere" size="{r}" mass="{m}" friction="1 1 0.001"/>
    </body>
  </worldbody>"""

BODIES_INCLINE = """  <worldbody>
    <body name="ramp" pos="0 0 0" quat="{quat}">
      <geom name="plane" type="plane" size="5 5 0.1" friction="{mu} {mu} 0.001"/>
    </body>
    <body name="mover" pos="{pos}" quat="{quat}">
      <freejoint/>
      <geom name="box" type="box" size="{hx} {hy} {hz}" mass="{m}" friction="{mu} {mu} 0.001"/>
    </body>
  </worldbody>"""

BODIES_PENDULUM = """  <worldbody>
    <body name="mover" pos="{anchor}">
      <joint name="hinge" type="hinge" axis="0 1 0" pos="0 0 0"/>
      <inertial pos="0 0 -{L}" mass="{m}" diaginertia="1e-8 1e-8 1e-8"/>
      <geom name="bob" type="sphere" size="0.02" pos="0 0 -{L}"/>
    </body>
  </worldbody>"""


def quat_string(axis, angle):
    """MJCF quat (w x y z) rotating `angle` rad about `axis`."""
    axis = np.asarray(axis, dtype=float)
    axis = axis / np.linalg.norm(axis)
    q = np.concatenate(([math.cos(angle / 2)], math.sin(angle / 2) * axis))
    return " ".join("%.12g" % v for v in q)


def write_csv(path, columns, rows):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(columns)
        w.writerows(rows)


def build_and_run(spec, outdir, seed=0):
    g = spec["gravity"]
    dt = spec["timestep_s"]
    os.makedirs(outdir, exist_ok=True)
    for sc in spec["scenarios"]:
        name, kind = sc["name"], None
        if name == "drop":
            kind, cols = "drop", sc["columns"]
            r = sc["body"]["radius"]
            xml = MJCF.format(name=name, g=g, dt=dt, bodies=BODIES_DROP.format(
                pos=" ".join("%g" % v for v in sc["body"]["pos"]),
                r=r, m=sc["body"]["mass_kg"]))
        elif name.startswith("incline"):
            kind, cols = "incline", sc["columns"]
            mu = sc["plane"]["friction_mu"]
            hx, hy, hz = sc["body"]["half_extents"]
            th = math.radians(sc["plane"]["tilt_deg"])
            # +tilt about y: surface normal (+sin t, 0, +cos t), so the
            # surface z = -tan(t) * x descends toward +x as the spec says.
            quat = quat_string([0, 1, 0], th)
            pos = hz * np.array([math.sin(th), 0.0, math.cos(th)])
            xml = MJCF.format(name=name, g=g, dt=dt, bodies=BODIES_INCLINE.format(
                mu=mu, quat=quat, pos=" ".join("%g" % v for v in pos),
                hx=hx, hy=hy, hz=hz, m=sc["body"]["mass_kg"]))
        elif name == "pendulum":
            kind, cols = "pendulum", sc["columns"]
            L = sc["link"]["L_m"]
            xml = MJCF.format(name=name, g=g, dt=dt, bodies=BODIES_PENDULUM.format(
                anchor=" ".join("%g" % v for v in sc["anchor"]),
                L=L, m=sc["link"]["mass_kg"]))
        else:
            raise ValueError(f"unknown scenario {name}")

        model = mujoco.MjModel.from_xml_string(xml)
        data = mujoco.MjData(model)
        bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "mover")
        if kind == "pendulum":
            # hinge about +y: bob sits at (-L sin q, 0, -L cos q), so the
            # spec's theta (+ toward +x) is -qpos.
            jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "hinge")
            qa = model.jnt_qposadr[jid]
            va = model.jnt_dofadr[jid]
            data.qpos[qa] = -sc["theta0_rad"]
        mujoco.mj_forward(model, data)

        n = int(round(sc["duration_s"] / dt))
        rows = []
        for i in range(n + 1):
            if i:
                mujoco.mj_step(model, data)
            p = data.xpos[bid]
            if kind == "drop":
                # free-joint qvel: (3 rot, 3 lin) with the linear part in
                # world coordinates
                rows.append([i * dt, p[2], data.qvel[5]])
            elif kind == "incline":
                rows.append([i * dt, p[0], p[2], data.qvel[3], data.qvel[5]])
            else:
                rows.append([i * dt, -data.qpos[qa], -data.qvel[va]])
        write_csv(os.path.join(outdir, sc["output"]), cols, rows)
        with open(os.path.join(outdir, "model_%s.xml" % name), "w") as fh:
            fh.write(xml)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("outdir")
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    with open(a.spec) as fh:
        build_and_run(json.load(fh), a.outdir, seed=a.seed)
