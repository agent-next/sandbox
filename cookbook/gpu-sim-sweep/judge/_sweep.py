"""Sim runners the judge executes itself during grading.

Imported by _grade.py. The judge — never the artifact — runs these:

  cpu_reference(xml, target, ...) — single-world mujoco mj_step: oracle state
      right after the settle window, a per-step world-0 qpos trajectory for
      the parity gate, and a timed steps/s benchmark.

  gpu_point(xml, target, nworld, ...) — one mujoco_warp batch of `nworld`
      identical worlds: put_data timing, cold-compile first-step time, settle
      phase, timed batches (aggregate world-steps/s), and an oracle read-back
      aggregated over all worlds. nconmax/njmax=None asks mujoco_warp to size
      the contact buffers from the t=0 state (the real capacity trap this
      demo documents: boxes in the air -> tiny buffers -> tunnelling once
      they land).

Oracle state is read right after the settle window, before the timed
batches, in BOTH runners — so a too-short settle leaves the boxes mid-air in
the read-back.
"""

import time

import numpy as np

NQ_ARM = 7          # arm hinge joints
NQ_BOX = 7          # free joint: 3 pos + 4 quat
BOX_Z_OFF = 2       # z within a box's 3-vector position


def _box_slices(nq: int, nv: int) -> list:
    """(qpos z index, qvel offset) per box, from the model layout.

    qpos: 7 arm hinges + per box 7 (3 pos + 4 quat); qvel: 7 arm + 6 per box.
    """
    n_boxes = (nq - NQ_ARM) // NQ_BOX
    return [(NQ_ARM + i * NQ_BOX + BOX_Z_OFF,
             NQ_ARM + i * (nv - NQ_ARM) // n_boxes)
            for i in range(n_boxes)]


def _oracle_from_state(q: np.ndarray, v: np.ndarray, m, target: list,
                       batched: bool = False) -> dict:
    """Aggregate the oracle read-back. q/v are (nq,) for CPU or
    (nworld, nq) for GPU; batched selects the indexing."""
    slices = _box_slices(m.nq, m.nv)
    tgt = np.asarray(target)
    if batched:
        arm_err = np.abs(q[:, :NQ_ARM] - tgt).max()
        z = np.concatenate([q[:, s[0]] for s in slices])
        spd = max(float(np.abs(v[:, s[1]:s[1] + 6]).max()) for s in slices)
    else:
        arm_err = np.abs(q[:NQ_ARM] - tgt).max()
        z = np.asarray([q[s[0]] for s in slices])
        spd = max(float(np.abs(v[s[1]:s[1] + 6]).max()) for s in slices)
    return {
        "qpos_finite": bool(np.isfinite(q).all()),
        "qvel_finite": bool(np.isfinite(v).all()),
        "arm_max_err": float(np.nanmax(arm_err)),
        "box_z_min": float(np.nanmin(z)),
        "box_z_max": float(np.nanmax(z)),
        "box_speed_max": float(np.nanmax(spd)),
    }


def cpu_reference(xml: str, target: list, settle: int = 800,
                  warmup: int = 1000, timed: int = 20000,
                  record: bool = True) -> dict:
    """Single-world CPU run of the same XML the GPU sweeps.

    Oracle state is read immediately after `settle` steps (copied out —
    np.asarray(d.qpos) is a live view that would keep mutating during the
    timed loop). The trajectory is the settle window for the parity gate.
    """
    import mujoco

    m = mujoco.MjModel.from_xml_string(xml)
    d = mujoco.MjData(m)
    d.ctrl[:] = target
    traj = []
    if record:  # world-0 parity gate: qpos at every step of the settle window
        traj.append(np.asarray(d.qpos).copy().tolist())
    for _ in range(settle):
        mujoco.mj_step(m, d)
        if record:
            traj.append(np.asarray(d.qpos).copy().tolist())
    q = np.asarray(d.qpos).copy()
    v = np.asarray(d.qvel).copy()
    out = {
        "mujoco_version": mujoco.__version__,
        "nq": int(m.nq),
        "nv": int(m.nv),
        "traj": traj,
        "traj_steps": len(traj),
        "steps_per_s": None,
        **_oracle_from_state(q, v, m, target, batched=False),
    }
    for _ in range(warmup):
        mujoco.mj_step(m, d)
    t0 = time.perf_counter()
    for _ in range(timed):
        mujoco.mj_step(m, d)
    out["steps_per_s"] = round(timed / (time.perf_counter() - t0))
    return out


def gpu_point(xml: str, target: list, nworld: int, nconmax=None, njmax=None,
              settle: int = 800, timed: int = 200, batches: int = 2,
              record_traj: bool = False) -> dict:
    """One sweep point: `nworld` identical worlds stepped in lockstep.

    Returns an oracle read-back aggregated over all worlds plus timings.
    Allocation failures propagate (the caller classifies them into a clean
    point failure — e.g. a ladder point past slice capacity).
    """
    import mujoco
    import mujoco_warp as mjw
    import warp as wp

    out = {
        "nworld": nworld, "nconmax": nconmax, "njmax": njmax,
        "mujoco_version": mujoco.__version__,
        "mujoco_warp_version": getattr(mjw, "__version__", "?"),
        "warp_version": getattr(wp, "__version__", "?"),
    }
    m = mujoco.MjModel.from_xml_string(xml)
    d = mujoco.MjData(m)
    d.ctrl[:] = target
    md = mjw.put_model(m)
    cap = {} if nconmax is None and njmax is None else dict(
        nconmax=nconmax, njmax=njmax)
    t0 = time.perf_counter()
    try:
        dd = mjw.put_data(m, d, nworld=nworld, **cap)
        wp.synchronize()
    except Exception as e:  # over-capacity: classified for the judge
        raise MemoryError(
            f"put_data nworld={nworld} cap={cap or 'defaults'} failed: "
            f"{type(e).__name__}: {e}") from e
    out["put_data_s"] = round(time.perf_counter() - t0, 3)

    t0 = time.perf_counter()
    mjw.step(md, dd)  # first step pays the Warp kernel compile on a cold lease
    wp.synchronize()
    out["first_step_s"] = round(time.perf_counter() - t0, 3)

    traj = []
    if record_traj:  # world-0 qpos every step of the settle window
        traj.append(dd.qpos.numpy()[0].copy().tolist())
    for _ in range(settle):
        mjw.step(md, dd)
        if record_traj:
            traj.append(dd.qpos.numpy()[0].copy().tolist())
    if record_traj:
        out["traj"] = traj
        out["traj_steps"] = len(traj)

    spss = []
    for _ in range(batches):
        t0 = time.perf_counter()
        for _ in range(timed):
            mjw.step(md, dd)
        wp.synchronize()
        spss.append(round(timed * nworld / (time.perf_counter() - t0)))
    out["steps_per_s"] = max(spss)
    out["steps_per_s_batches"] = spss
    out["timed_steps"] = timed

    # oracle read-back over the whole batch (nan-aware: a NaN world must
    # surface through the finite flags, not kill the aggregation)
    q = dd.qpos.numpy()
    v = dd.qvel.numpy()
    out["nq"] = int(m.nq)
    out["nv"] = int(m.nv)
    out["nworld_confirmed"] = int(q.shape[0])
    out.update(_oracle_from_state(q, v, m, target, batched=True))
    return out
