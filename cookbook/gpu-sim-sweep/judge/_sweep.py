"""Runners executed on the GPU lease: CPU reference and GPU sweep points.

Imported by _grade.py inside lease exec payloads. Two entry points:

  cpu_reference(xml, target, ...) — single-world mujoco mj_step: final state,
      per-step qpos trajectory for the parity gate, and steps/s.

  gpu_point(xml, target, nworld, ...) — one mujoco_warp batch of `nworld`
      identical worlds: cold-compile time, settle phase, timed batches
      (aggregate world-steps/s), and an oracle read-back aggregated over all
      worlds. nconmax/njmax None -> mujoco_warp sizes them from the t=0 state
      (the real capacity trap this demo documents).

Each exec is its own process on purpose: device memory is fully returned
between sweep points (warp's memory pool would otherwise keep the high-water
mark across points in one process).
"""

import time

import numpy as np

NQ_ARM = 7          # arm hinge joints
NQ_BOX = 7          # free joint: 3 pos + 4 quat
BOX_Z_OFF = 2       # z within a box's 3-vector position


def _box_slices(nq: int, nv: int) -> list:
    """(z_index, vel_offset) per box, from the model layout.

    qpos: 7 arm hinges + per box 7 (3 pos + 4 quat); qvel: 7 arm + 6 per box.
    """
    n_boxes = (nq - NQ_ARM) // NQ_BOX
    return [(NQ_ARM + i * NQ_BOX + BOX_Z_OFF, NQ_ARM + i * (nv - NQ_ARM) // n_boxes)
            for i in range(n_boxes)]


def cpu_reference(xml: str, target: list, settle: int = 800, warmup: int = 1000,
                  timed: int = 20000, record: bool = True) -> dict:
    """Single-world CPU run of the same XML the GPU sweeps."""
    import mujoco

    m = mujoco.MjModel.from_xml_string(xml)
    d = mujoco.MjData(m)
    d.ctrl[:] = target
    traj = []
    if record:  # world-0 parity gate: qpos at every step of the settle window
        traj.append(np.asarray(d.qpos).tolist())
    for _ in range(settle):
        mujoco.mj_step(m, d)
        if record:
            traj.append(np.asarray(d.qpos).tolist())
    q = np.asarray(d.qpos)
    v = np.asarray(d.qvel)
    slices = _box_slices(m.nq, m.nv)
    out = {
        "mujoco_version": mujoco.__version__,
        "nq": int(m.nq),
        "nv": int(m.nv),
        "nbox": len(slices),
        "qpos_final": q.tolist(),
        "qvel_max": float(np.abs(v).max()),
        "arm_max_err": float(np.abs(q[:NQ_ARM] - np.asarray(target)).max()),
        "box_z": [float(q[s[0]]) for s in slices],
        "box_speed_max": float(max(np.abs(v[s[1]:s[1] + 6]).max() for s in slices)),
        "steps_per_s": None,
        "traj": traj,
    }
    for _ in range(warmup):
        mujoco.mj_step(m, d)
    t0 = time.perf_counter()
    for _ in range(timed):
        mujoco.mj_step(m, d)
    out["steps_per_s"] = round(timed / (time.perf_counter() - t0))
    out["traj_steps"] = len(traj)
    return out


def gpu_point(xml: str, target: list, nworld: int, nconmax=None, njmax=None,
              cache_dir: str = None,  # noqa: ARG001 (mirrors _grade.py call site)
              settle: int = 800, timed: int = 200, batches: int = 2,
              record_traj: bool = False, oom_probe: bool = False) -> dict:
    """One sweep point: `nworld` identical worlds stepped in lockstep.

    Returns an oracle read-back aggregated over all worlds plus timings.
    Raises (with a classified message) on allocation failure, so the caller
    can report an over-capacity point as a clean failure, not a crash.
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
    except Exception as e:  # over-capacity: classified, re-raised for the judge
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
        traj.append(dd.qpos.numpy()[0].tolist())
    for _ in range(settle):
        mjw.step(md, dd)
        if record_traj:
            traj.append(dd.qpos.numpy()[0].tolist())
    if record_traj:
        out["traj"] = traj
        out["traj_steps"] = len(traj)

    spss = []
    if not oom_probe:
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
    slices = _box_slices(m.nq, m.nv)
    out["nq"] = int(m.nq)
    out["nv"] = int(m.nv)
    out["nworld_confirmed"] = int(q.shape[0])
    out["qpos_finite"] = bool(np.isfinite(q).all())
    out["qvel_finite"] = bool(np.isfinite(v).all())
    out["arm_max_err"] = float(np.nanmax(np.abs(q[:, :NQ_ARM] - np.asarray(target))))
    zs = [q[:, s[0]] for s in slices]
    out["box_z_min"] = float(np.nanmin(np.concatenate(zs)))
    out["box_z_max"] = float(np.nanmax(np.concatenate(zs)))
    out["box_speed_max"] = float(max(
        np.nanmax(np.abs(v[:, s[1]:s[1] + 6])) for s in slices))
    out["ncon_final"] = int(dd.ncon.numpy().sum()) if hasattr(dd, "ncon") else None
    return out
