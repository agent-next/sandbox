#!/usr/bin/env python3
"""Shared MuJoCo scene and simulation for the sim-tuner demo.

This module is the single source of truth for the physical rig: the MJCF,
the calibration parameter set, the error metric, and one CPU MuJoCo rollout.
It imports only `mujoco` and `numpy` (pinned in judge/requirements.txt).

The scene: a box slides across a table while a 2-link planar arm tracks a
step command. The 5 hidden parameters are contact friction/solver constants
of the box-table pair and the hinge damping/armature of the two arm joints.
Everything else (masses, geometry, actuator gains, timestep) is fixed.
"""

import json
import math

NSTEP = 500          # 1.0 s at 0.002 s timestep
SUB = 4              # record every 4th step -> 125 samples at 4 ms
HALF = 250           # actuator command steps at t = 0.5 s
NOBS = NSTEP // SUB  # 125
SIG_NAMES = ["box_x", "box_z", "q1", "q2", "q1dot", "q2dot"]
NSIG = len(SIG_NAMES)
DOF_H = 6            # hinge dofs 6..7 (after the 6-dof freejoint)

# name, low, high, default (the shipped MJCF value), what it physically is
PARAM_SPEC = [
    ("mu",        0.15,  0.90,  0.50,  "sliding friction of the box-table pair"),
    ("solref_tc", 0.005, 0.020, 0.010, "contact solref time constant [s]"),
    ("solref_dr", 0.80,  1.60,  1.00,  "contact solref damping ratio"),
    ("damping",   0.02,  0.35,  0.15,  "hinge joint damping [N.m.s/rad]"),
    ("armature",  0.005, 0.060, 0.020, "hinge armature [kg.m2]"),
]
PARAM_NAMES = [p[0] for p in PARAM_SPEC]
DEFAULT_PARAMS = {p[0]: p[3] for p in PARAM_SPEC}
PARAM_LO = {p[0]: p[1] for p in PARAM_SPEC}
PARAM_HI = {p[0]: p[2] for p in PARAM_SPEC}
PARAM_DESC = {p[0]: p[4] for p in PARAM_SPEC}

SCENE_XML = """<mujoco model="tuner">
  <option timestep="0.002" gravity="0 0 -9.81"/>
  <worldbody>
    <geom name="table" type="plane" size="3 3 .1" friction="0.5 0.02 0.0001" solref="0.01 1"
          solimp="0.99 0.999 0.001 0.5 2"/>
    <body name="box" pos="-0.5 0.2 0.06">
      <freejoint/>
      <geom name="boxgeom" type="box" size="0.05 0.05 0.05" mass="0.2" friction="0.5 0.02 0.0001"
            solref="0.01 1" solimp="0.99 0.999 0.001 0.5 2"/>
    </body>
    <body name="arm" pos="0.7 0 0.4">
      <joint name="j1" type="hinge" axis="0 1 0" range="-1.5 1.5" damping="0.15" armature="0.02"/>
      <geom name="l1" type="capsule" size="0.03" fromto="0 0 0 0.4 0 0" mass="0.15"/>
      <body name="link2" pos="0.4 0 0">
        <joint name="j2" type="hinge" axis="0 1 0" range="-1.5 1.5" damping="0.15" armature="0.02"/>
        <geom name="l2" type="capsule" size="0.025" fromto="0 0 0 0.35 0 0" mass="0.10"/>
      </body>
    </body>
  </worldbody>
  <actuator>
    <position name="a1" joint="j1" kp="60"/>
    <position name="a2" joint="j2" kp="60"/>
  </actuator>
</mujoco>"""


def make_model(params):
    """Build the MjModel with the given calibration parameter values."""
    import mujoco
    m = mujoco.MjModel.from_xml_string(SCENE_XML)
    p = [float(params[k]) for k in PARAM_NAMES]
    # the box and the table carry the same pair coefficients (MuJoCo combines
    # geom friction by element-wise max of the two surfaces, so varying only
    # one surface does nothing)
    m.geom_friction[0, 0] = m.geom_friction[1, 0] = p[0]
    m.geom_solref[0] = m.geom_solref[1] = [p[1], p[2]]
    m.dof_damping[DOF_H:] = p[3]     # hinges only; the free joint stays clean
    m.dof_armature[DOF_H:] = p[4]
    return m


def simulate(params, ic):
    """One CPU MuJoCo rollout -> list of NOBS rows of NSIG signals.

    ic keys: x0, y0, z0, vx0 (box), c1a, c2a, c1b, c2b (arm commands).
    """
    import mujoco
    m = make_model(params)
    d = mujoco.MjData(m)
    d.qpos[0:3] = [ic["x0"], ic["y0"], ic["z0"]]
    d.qvel[0:3] = [ic["vx0"], 0.0, 0.0]
    d.ctrl[:] = [ic["c1a"], ic["c2a"]]
    rows = []
    for k in range(NSTEP):
        if k == HALF:
            d.ctrl[:] = [ic["c1b"], ic["c2b"]]
        mujoco.mj_step(m, d)
        if (k + 1) % SUB == 0:
            rows.append([d.qpos[0], d.qpos[2], d.qpos[7], d.qpos[8],
                         d.qvel[6], d.qvel[7]])
    return rows


def read_params_json(path):
    """Read and validate a params.json artifact.

    Returns the params dict. Raises ValueError with a precise message on any
    violation: malformed JSON, non-object, missing/extra keys, non-finite or
    non-numeric values, values outside the physical ranges in PARAM_SPEC
    (tolerance 1e-9 so the exact range edges count as inside).
    """
    try:
        with open(path) as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        raise ValueError(f"unreadable or malformed JSON: {exc}") from None
    if not isinstance(data, dict):
        raise ValueError(f"top level must be an object, got {type(data).__name__}")
    missing = [k for k in PARAM_NAMES if k not in data]
    extra = [k for k in data if k not in PARAM_LO]
    if missing:
        raise ValueError(f"missing parameters: {', '.join(missing)}")
    if extra:
        raise ValueError(f"unknown parameters: {', '.join(extra)}")
    out = {}
    for k in PARAM_NAMES:
        v = data[k]
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"{k} must be a number, got {v!r}")
        v = float(v)
        if not math.isfinite(v):
            raise ValueError(f"{k} must be finite, got {v!r}")
        if v < PARAM_LO[k] - 1e-9 or v > PARAM_HI[k] + 1e-9:
            raise ValueError(
                f"{k} = {v} outside physical range "
                f"[{PARAM_LO[k]}, {PARAM_HI[k]}] ({PARAM_DESC[k]})")
        out[k] = v
    return out


def err_rms(params, ics, refs, scale):
    """Normalised RMS trajectory error of params vs recorded references.

    refs and ics are parallel lists; scale is a length-NSIG list. Returns
    float('nan') if any rollout produces a non-finite state (contact blow-up).
    """
    tot = 0.0
    n = 0
    for ic, ref in zip(ics, refs):
        sim = simulate(params, ic)
        for row_s, row_r in zip(sim, ref):
            for j in range(NSIG):
                d = (row_s[j] - row_r[j]) / scale[j]
                if not math.isfinite(d):
                    return float("nan")
                tot += d * d
                n += 1
    return math.sqrt(tot / n) if n else float("nan")
