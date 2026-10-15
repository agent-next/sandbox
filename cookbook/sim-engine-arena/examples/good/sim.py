"""sim-engine-arena agent port: build the arena scenes in MuJoCo.

Reads spec.json (the neutral scene spec: geometry, masses, friction, the
timestep and the required CSV outputs) and simulates each scenario in
MuJoCo at the spec timestep, writing one CSV per scenario. The spec
contains no expected results and neither does this file: it only builds
the scenes from the given parameters and records what happens.

Usage: python sim.py        (spec.json in the current directory)
"""

import csv
import json
import math

import mujoco
import numpy as np

MJCF = """<mujoco model="arena-{name}">
  <option gravity="0 0 -{g}" timestep="{dt}"/>
  {bodies}
</mujoco>
"""

DROP = """  <worldbody>
    <geom name="floor" type="plane" size="5 5 0.1" pos="0 0 0"/>
    <body name="mover" pos="{pos}">
      <freejoint/>
      <geom name="ball" type="sphere" size="{r}" mass="{m}"/>
    </body>
  </worldbody>"""

INCLINE = """  <worldbody>
    <body name="ramp" pos="0 0 0" quat="{quat}">
      <geom name="plane" type="plane" size="5 5 0.1" friction="{mu} {mu} 0.001"/>
    </body>
    <body name="mover" pos="{pos}" quat="{quat}">
      <freejoint/>
      <geom name="box" type="box" size="{hx} {hy} {hz}" mass="{m}"
            friction="{mu} {mu} 0.001"/>
    </body>
  </worldbody>"""

PENDULUM = """  <worldbody>
    <body name="mover" pos="{anchor}">
      <joint name="hinge" type="hinge" axis="0 1 0" pos="0 0 0"/>
      <inertial pos="0 0 -{L}" mass="{m}" diaginertia="1e-8 1e-8 1e-8"/>
      <geom name="bob" type="sphere" size="0.02" pos="0 0 -{L}"/>
    </body>
  </worldbody>"""


def quat_string(axis, angle):
    axis = np.asarray(axis, dtype=float)
    axis = axis / np.linalg.norm(axis)
    q = np.concatenate(([math.cos(angle / 2)], math.sin(angle / 2) * axis))
    return " ".join("%.12g" % v for v in q)


def write_csv(path, columns, rows):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(columns)
        w.writerows(rows)


def run():
    with open("spec.json") as fh:
        spec = json.load(fh)
    g, dt = spec["gravity"], spec["timestep_s"]
    for sc in spec["scenarios"]:
        name = sc["name"]
        if name == "drop":
            xml = MJCF.format(name=name, g=g, dt=dt, bodies=DROP.format(
                pos=" ".join("%g" % v for v in sc["body"]["pos"]),
                r=sc["body"]["radius"], m=sc["body"]["mass_kg"]))
        elif name.startswith("incline"):
            plane = sc["plane"]
            mu = plane["friction_mu"]
            hx, hy, hz = sc["body"]["half_extents"]
            th = math.radians(plane["tilt_deg"])
            # rotate about +y so the surface normal is (+sin, 0, +cos):
            # the surface descends toward +x as the spec requires
            quat = quat_string([0, 1, 0], th)
            pos = hz * np.array([math.sin(th), 0.0, math.cos(th)])
            xml = MJCF.format(name=name, g=g, dt=dt, bodies=INCLINE.format(
                mu=mu, quat=quat, pos=" ".join("%g" % v for v in pos),
                hx=hx, hy=hy, hz=hz, m=sc["body"]["mass_kg"]))
        elif name == "pendulum":
            xml = MJCF.format(name=name, g=g, dt=dt, bodies=PENDULUM.format(
                anchor=" ".join("%g" % v for v in sc["anchor"]),
                L=sc["link"]["L_m"], m=sc["link"]["mass_kg"]))
        else:
            raise ValueError(f"unknown scenario {name}")

        model = mujoco.MjModel.from_xml_string(xml)
        data = mujoco.MjData(model)
        bid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY,
                                sc.get("moving_body_name", "mover"))
        if name == "pendulum":
            # the body origin is the anchor and the inertial mass sits at
            # (0, 0, -L); the hinge turns about +y so the spec's theta
            # (+ toward +x) is -qpos
            jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "hinge")
            qa, va = model.jnt_qposadr[jid], model.jnt_dofadr[jid]
            data.qpos[qa] = -sc["theta0_rad"]
        mujoco.mj_forward(model, data)

        n = int(round(sc["duration_s"] / dt))
        rows = []
        for i in range(n + 1):
            if i:
                mujoco.mj_step(model, data)
            p = data.xpos[bid]
            if name == "drop":
                rows.append([i * dt, p[2], data.qvel[5]])
            elif name.startswith("incline"):
                rows.append([i * dt, p[0], p[2], data.qvel[3], data.qvel[5]])
            else:
                rows.append([i * dt, -data.qpos[qa], -data.qvel[va]])
        write_csv(sc["output"], sc["columns"], rows)
        with open("model_%s.xml" % name, "w") as fh:
            fh.write(xml)


if __name__ == "__main__":
    run()
