#!/usr/bin/env python3
"""sim-tuner judge engine: the hidden scenario, the physics, the error metric.

Everything here is shared by _grade.py (GPU+CPU grading), mutants.py (which
needs the default parameters) and tools/search.py (the GPU evaluate loop that
produced examples/good/). This module is the single source of truth for:

  SCENE_XML     the box-and-arm MJCF rig
  PARAM_SPEC    the five hidden parameters, ranges, defaults, descriptions
  gen_scenario  seeded hidden parameters, initial conditions, noisy recordings
  error_of      RMS trajectory mismatch against a recording set, per-signal scaled
  simulate      CPU MuJoCo 3.8.1 reference integrator
  GPU_EVAL_SRC  the batched mujoco_warp evaluator that runs on the GPU lease

The scenario is regenerated from --seed at every grade; ground truth and the
held-out recordings are never read from anything the artifact can reach.
"""
from __future__ import annotations

import json

import mujoco
import numpy as np

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

# name, low, high, default (the shipped MJCF value), physical meaning
PARAM_SPEC = [
    ("mu", 0.15, 0.90, 0.50, "sliding friction coefficient of the box-table pair"),
    ("solref_tc", 0.005, 0.020, 0.010, "contact solref time constant [s]"),
    ("solref_dr", 0.80, 1.60, 1.00, "contact solref damping ratio"),
    ("damping", 0.02, 0.35, 0.15, "hinge joint damping [N*m*s/rad]"),
    ("armature", 0.005, 0.060, 0.020, "hinge armature [kg*m^2]"),
]
PARAM_NAMES = [p[0] for p in PARAM_SPEC]
DEFAULT_PARAMS = {p[0]: p[3] for p in PARAM_SPEC}
RANGES = {p[0]: (p[1], p[2]) for p in PARAM_SPEC}

NSTEP, SUB, HALF = 500, 4, 250     # 1.0 s at 2 ms; ctrl step at t = 0.5 s; sampled every 8 ms
NOBS = NSTEP // SUB                # 125
NSIG = 6
SIG_NAMES = ["box_x", "box_z", "q1", "q2", "q1dot", "q2dot"]

NOISE_FRAC = 0.015                 # 1.5 % of each signal's RMS, seeded
N_TRAIN, N_HOLDOUT = 6, 4
DOF_H = 6                          # hinge dofs are nv-2 .. nv-1 (after the 6-dof free joint)

# Gate thresholds, calibrated on CPU MuJoCo 3.8.1 (seed 7, see SPEC.md):
# hidden-truth held-out error (the noise floor) 0.01492; the nearest single-
# parameter range-edge move scores 0.02123.
ORACLE_ABS_ERR = 0.030             # ~2x the noise floor, > 1.4x margin to the nearest mutant
ORACLE_REL_FRAC = 0.30             # and below 30 % of the default-parameter error
GPU_CPU_ABS = 0.003                # |gpu train err - cpu train err|
GPU_CPU_TOL = 0.10                 # and within 10 % of the CPU error

# Peak constraint counts of this scene, measured on CPU MuJoCo 3.8.1 over every
# parameter extreme in PARAM_SPEC x all 10 initial conditions x 500 steps:
# ncon <= 4, nefc <= 18 (the box-table contacts plus the two hinge range
# constraints). put_data() sizes its contact and Jacobian buffers from the t=0
# state, where this scene has no contact at all, so both must be passed
# explicitly and well above the measured peak.
PEAK_NCON, PEAK_NEFC = 4, 18
NCONMAX, NJMAX = 4 * PEAK_NCON, 4 * PEAK_NEFC      # 16 / 72

ARCH_KEYS = ["name", "accel", "os", "python", "mujoco", "numpy", "custom_fields"]
ARCH_ACCEL = "RTX 5090 VRAM slice"


def check_version_table(actual, expected):
    """Gate the lease stack against the SPEC table.

    Rules (a hard version-lock, not a substring match):
    - keys in ARCH_KEYS (except custom_fields) must match expected exactly
      (os match is on the Linux release field only; Python is matched on
      major.minor.patch, and numpy on the full version);
    - the local mujoco_cv tuple must be >= the expected one (a newer patch
      release of the same solver is accepted, an older one is not);
    - no extra custom fields the judge does not know about may appear.
    """
    problems = []
    if not expected:
        return ["no expected version table recorded (setup --record missing?)"]
    for key in ARCH_KEYS:
        if key == "custom_fields":
            continue
        want = expected.get(key)
        got = actual.get(key)
        if want is None:
            problems.append(f"version table has no entry for {key!r}")
            continue
        if key == "os":
            # platform.platform() is "<system>-<release>-<version>..."-ish;
            # compare on the release field (second "-" token), which carries
            # the kernel release the reference recordings were made under.
            def _rel(s):
                parts = str(s).split("-")
                return parts[1] if len(parts) > 1 else str(s)
            if _rel(got) != _rel(want):
                problems.append(f"os mismatch: got {got!r}, want release of {want!r}")
        elif key == "python":
            if str(got) != str(want):
                problems.append(f"python mismatch: got {got}, want {want}")
        elif str(got) != str(want):
            problems.append(f"{key} mismatch: got {got}, want {want}")
    if tuple(actual.get("mujoco_cv") or ()) < tuple(expected.get("mujoco_cv") or (0,)):
        problems.append(f"mujoco {actual.get('mujoco')} older than expected "
                        f"{expected.get('mujoco')}")
    customs = actual.get("custom_fields") or {}
    if not isinstance(customs, dict):
        problems.append("custom_fields is not a dict")
    else:
        extra = sorted(set(customs) - set(expected.get("custom_fields") or {}))
        if extra:
            problems.append(f"lease reported unknown custom fields: {extra}")
    return problems


# ---------------------------------------------------------------- bundles


def bundle_scenario(scen):
    """JSON-safe snapshot of one generated scenario (the judge's state)."""
    return {
        "seed": scen["seed"],
        "noise_frac": scen["noise_frac"],
        "truth": scen["truth"],
        "ics_train": scen["ics_train"],
        "ics_hold": scen["ics_hold"],
        "refs_train": scen["refs_train"],
        "refs_hold": scen["refs_hold"],
        "scale": scen["scale"],
        "expected_versions": scen["expected_versions"],
    }


def load_scenario(b):
    scen = {
        "seed": int(b["seed"]),
        "noise_frac": float(b["noise_frac"]),
        "truth": {k: float(v) for k, v in b["truth"].items()},
        "ics_train": [{k: float(v) for k, v in ic.items()} for ic in b["ics_train"]],
        "ics_hold": [{k: float(v) for k, v in ic.items()} for ic in b["ics_hold"]],
        "refs_train": [np.array(r, dtype=np.float64) for r in b["refs_train"]],
        "refs_hold": [np.array(r, dtype=np.float64) for r in b["refs_hold"]],
        "scale": np.array(b["scale"], dtype=np.float64),
        "expected_versions": dict(b.get("expected_versions") or {}),
    }
    for ic in scen["ics_train"] + scen["ics_hold"]:
        if set(ic) != {"x0", "y0", "z0", "vx0", "c1a", "c2a", "c1b", "c2b"}:
            raise ValueError(f"initial condition has wrong keys: {sorted(ic)}")
    for split, refs in (("refs_train", scen["refs_train"]), ("refs_hold", scen["refs_hold"])):
        if len(refs) != (N_TRAIN if split == "refs_train" else N_HOLDOUT):
            raise ValueError(f"{split} must hold {N_TRAIN if split == 'refs_train' else N_HOLDOUT} recordings")
        for r in refs:
            if r.shape != (NOBS, NSIG):
                raise ValueError(f"{split} recording has shape {r.shape}, expected ({NOBS}, {NSIG})")
    if scen["scale"].shape != (NSIG,):
        raise ValueError("scale must be a vector of length NSIG")
    return scen


# ---------------------------------------------------------------- CPU physics


def make_model(params):
    m = mujoco.MjModel.from_xml_string(SCENE_XML)
    p = [params[k] for k in PARAM_NAMES]
    # the box and the table carry the same pair coefficients (MuJoCo combines
    # friction by element-wise max, so varying only one surface does nothing)
    m.geom_friction[0, 0] = m.geom_friction[1, 0] = p[0]
    m.geom_solref[0] = m.geom_solref[1] = [p[1], p[2]]
    m.dof_damping[DOF_H:] = p[3]     # hinges only; the free joint must stay clean
    m.dof_armature[DOF_H:] = p[4]
    return m


def simulate(params, ic):
    """CPU MuJoCo, one 1.0 s recording -> (NOBS, NSIG) sampled signals."""
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
            rows.append([d.qpos[0], d.qpos[2], d.qpos[7], d.qpos[8], d.qvel[6], d.qvel[7]])
    return np.array(rows)


def error_of(params, refs, ics, scale):
    """RMS mismatch over all recordings, normalised per signal by the train RMS."""
    tot = []
    for ref, ic in zip(refs, ics):
        sim = simulate(params, ic)
        tot.append(((sim - ref) / scale) ** 2)
    return float(np.sqrt(np.mean(np.concatenate(tot))))


# ---------------------------------------------------------------- scenario


def _gen_ics(n, seed):
    out = []
    for i in range(n):
        r = np.random.default_rng(seed * 1000 + i)
        out.append({
            "x0": -0.5, "y0": 0.2, "z0": 0.06,
            "vx0": round(float(r.uniform(1.2, 2.4)), 4),
            "c1a": round(float(r.uniform(-0.9, 0.9)), 4),
            "c2a": round(float(r.uniform(-0.7, 0.7)), 4),
            "c1b": round(float(r.uniform(-0.9, 0.9)), 4),
            "c2b": round(float(r.uniform(-0.7, 0.7)), 4)})
    return out


def gen_scenario(seed, expected_versions=None):
    """Hidden parameters + noisy 'real robot' recordings for both splits."""
    rng = np.random.default_rng(seed)
    lo = np.array([p[1] for p in PARAM_SPEC])
    hi = np.array([p[2] for p in PARAM_SPEC])
    truth_v = lo + (hi - lo) * rng.random(len(PARAM_SPEC))
    truth = {k: round(float(v), 5) for k, v in zip(PARAM_NAMES, truth_v)}
    ics_train = _gen_ics(N_TRAIN, seed)
    ics_hold = _gen_ics(N_HOLDOUT, seed + 101)
    refs_train = [simulate(truth, ic) for ic in ics_train]
    refs_hold = [simulate(truth, ic) for ic in ics_hold]
    scale = np.sqrt(np.mean(np.concatenate([r ** 2 for r in refs_train]), axis=0))
    noise = np.random.default_rng(seed + 7)   # one stream: each recording gets its own noise
    for r in refs_train + refs_hold:          # measurement noise on the recorded signals
        r += noise.normal(0, NOISE_FRAC * scale, size=r.shape)
    return {"seed": seed, "noise_frac": NOISE_FRAC, "truth": truth,
            "ics_train": ics_train, "ics_hold": ics_hold,
            "refs_train": refs_train, "refs_hold": refs_hold, "scale": scale,
            "expected_versions": expected_versions or {}}


def host_speed_sample(scen, n=2):
    """Approximate host CPU throughput in candidates/s on the train split."""
    import time
    t0 = time.perf_counter()
    rng = np.random.default_rng(0)
    lo = np.array([p[1] for p in PARAM_SPEC])
    hi = np.array([p[2] for p in PARAM_SPEC])
    for i in range(n):
        p = {k: float(v) for k, v in zip(PARAM_NAMES, lo + (hi - lo) * rng.random(5))}
        error_of(p, scen["refs_train"], scen["ics_train"], scen["scale"])
    return round(n / (time.perf_counter() - t0), 2)


# ---------------------------------------------------------------- GPU batch evaluator

# One exec = one batched mujoco_warp run over nworld = len(candidates) x len(ics)
# worlds, with per-world model parameters (geom_friction, geom_solref,
# dof_damping, dof_armature) and per-world initial states. Per-world fields are
# expanded with the world axis (the nworld=1 put_model() result is broadcast).
GPU_EVAL_SRC = r'''
import json, time
import numpy as np
import mujoco, mujoco_warp as mjw
import warp as wp
import importlib.metadata as _md

XML = %(xml)s
NSTEP, SUB, HALF, NSIG = %(nstep)d, %(sub)d, %(half)d, %(nsig)d
NCONMAX, NJMAX = %(nconmax)d, %(njmax)d
DOF_H = 6
# PAYLOAD_JSON is replaced with a JSON string literal: candidates, ics, refs, scale.

ARCH_KEYS = %(arch_keys)r

def get_versions():
    import sys, platform
    mj_cv = tuple(int(x) for x in mujoco.__version__.split(".") if x.isdigit())
    return {
        "name": "gpu-lease",
        "accel": %(accel)r,
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "mujoco": mujoco.__version__,
        "mujoco_warp": _md.version("mujoco-warp"),
        "warp": _md.version("warp-lang"),
        "numpy": np.__version__,
        "mujoco_cv": list(mj_cv),
    }

def run_eval(payload):
    cands = payload["candidates"]
    ics = payload["ics"]
    refs = np.array(payload["refs"], dtype=np.float64)
    scale = np.array(payload["scale"], dtype=np.float64)
    n_ic, nobs = refs.shape[0], refs.shape[1]
    NC = len(cands)
    NW = NC * n_ic
    m = mujoco.MjModel.from_xml_string(XML)
    mm = mjw.put_model(m)
    # nconmax/njmax: put_data() sizes these from the t=0 state (here: no
    # contacts), so they must be given explicitly -- with the defaults the
    # box's contacts overflow once the box lands.
    dd = mjw.put_data(m, mujoco.MjData(m), nworld=NW, nconmax=NCONMAX, njmax=NJMAX)

    def set_model(field, npval, dtype, is_vec):
        shape = npval.shape[:-1] if is_vec else npval.shape
        arr = wp.array(np.ascontiguousarray(npval), dtype=dtype, shape=shape)
        arr._is_batched = True
        setattr(mm, field, arr)

    C = np.array(cands, dtype=np.float32)
    fr = np.tile(m.geom_friction, (NW, 1, 1))
    sr = np.tile(m.geom_solref, (NW, 1, 1))
    dm = np.tile(m.dof_damping, (NW, 1))
    am = np.tile(m.dof_armature, (NW, 1))
    for w in range(NW):
        ci, t = w %% NC, w // NC
        fr[w, 0, 0] = fr[w, 1, 0] = C[ci, 0]
        sr[w, 0] = sr[w, 1] = [C[ci, 1], C[ci, 2]]
        dm[w, DOF_H:] = C[ci, 3]
        am[w, DOF_H:] = C[ci, 4]
    set_model("geom_friction", fr, wp.vec3, True)
    set_model("geom_solref", sr, wp.vec2, True)
    set_model("dof_damping", dm, float, False)
    set_model("dof_armature", am, float, False)

    qpos = np.tile(m.qpos0, (NW, 1))
    qvel = np.zeros((NW, m.nv))
    ctrlA = np.zeros((NW, m.nu), dtype=np.float32)
    ctrlB = np.zeros((NW, m.nu), dtype=np.float32)
    for w in range(NW):
        ci, t = w %% NC, w // NC
        ic = ics[t]
        qpos[w, 0], qpos[w, 1], qpos[w, 2] = ic["x0"], ic["y0"], ic["z0"]
        qvel[w, 0] = ic["vx0"]
        ctrlA[w] = [ic["c1a"], ic["c2a"]]
        ctrlB[w] = [ic["c1b"], ic["c2b"]]
    dd.qpos = wp.array(qpos.astype(np.float32), dtype=float)
    dd.qvel = wp.array(qvel.astype(np.float32), dtype=float)
    dd.ctrl = wp.array(ctrlA, dtype=float)

    acc = np.zeros(NC, dtype=np.float64)
    t0 = time.perf_counter()
    step, obs, zmin = 0, 0, float("inf")
    for blk in range(2):
        if blk == 1:
            dd.ctrl = wp.array(ctrlB, dtype=float)
        for _ in range(HALF):
            mjw.step(mm, dd)
            step += 1
            if step %% SUB == 0:
                wp.synchronize()
                qp = dd.qpos.numpy(); qv = dd.qvel.numpy()
                zmin = min(zmin, float(qp[:, 2].min()))
                sig = np.stack([qp[:, 0], qp[:, 2], qp[:, 7], qp[:, 8], qv[:, 6], qv[:, 7]], axis=1)
                d = (sig.reshape(n_ic, NC, NSIG) - refs[:, obs, :].reshape(n_ic, 1, NSIG)) / scale
                acc += (d ** 2).sum(axis=(0, 2))
                obs += 1
    wp.synchronize()
    err = np.sqrt(acc / (n_ic * NSIG * nobs))
    return {"err": [round(float(e), 6) for e in err],
            "best": int(err.argmin()), "best_err": round(float(err.min()), 6),
            "nworld": NW, "sim_s": round(time.perf_counter() - t0, 3),
            "finite": bool(np.all(np.isfinite(err))),
            "min_box_z": round(zmin, 4)}

payload = json.loads(PAYLOAD_JSON)
report = run_eval(payload)
report["versions"] = get_versions()
'''

GPU_EVAL_SRC = GPU_EVAL_SRC % {
    "xml": json.dumps(SCENE_XML), "nstep": NSTEP, "sub": SUB, "half": HALF, "nsig": NSIG,
    "nconmax": NCONMAX, "njmax": NJMAX, "arch_keys": ARCH_KEYS, "accel": ARCH_ACCEL,
}

MAX_WORLDS = 1024          # worlds per GPU exec (candidates x train recordings)


def gpu_eval_code(candidates, ics, refs, scale):
    """Render one chunk of the batched GPU evaluation as exec code."""
    payload = {
        "candidates": [[c[k] for k in PARAM_NAMES] for c in candidates],
        "ics": ics,
        "refs": [r.tolist() for r in refs],
        "scale": [float(v) for v in scale],
    }
    return GPU_EVAL_SRC.replace("PAYLOAD_JSON", json.dumps(json.dumps(payload)))


def gpu_eval_chunks(candidates, ics):
    """Split a candidate list into chunks that fit MAX_WORLDS."""
    per_chunk = max(1, MAX_WORLDS // len(ics))
    for i in range(0, len(candidates), per_chunk):
        yield candidates[i:i + per_chunk]
