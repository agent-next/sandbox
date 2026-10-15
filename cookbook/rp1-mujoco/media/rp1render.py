"""Shared headless MuJoCo renderer for the rp1-mujoco media.

Renders the real RP1 humanoid from the judge's own per-step trace
(media/data/traces/<name>/trace.csv.gz, written by `grade.sh --trace`) at the
exact state the judge graded.  EGL is the pinned backend (mujoco 3.14.0
ships its own EGL loader; libEGL_mesa is the system driver).  OSMesa is
the fallback.  Nothing here re-simulates: every frame is a pose read out
of the judge's trace file.
"""
import csv
import gzip
import os

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco  # noqa: E402
import numpy as np  # noqa: E402

# columns written by grade.py's _Trace (see judge/grade.py)
N_SCALAR = 14          # t, xyz, quat(4), roll, pitch, tilt, fz, tau, frac
QPOS0 = N_SCALAR       # qpos_00 .. qpos_23 (the 24 hinge joints)
TAU0 = QPOS0 + 24      # tau_00 .. tau_23


class Trace:
    """One judged trajectory, read back from the judge's trace CSV."""

    def __init__(self, path):
        if not os.path.exists(path):
            raise SystemExit(
                f"missing trace {path} -- run media/collect_data.sh "
                "(grade.sh --trace) first")
        self.path = path
        # traces are stored gzipped (a raw trace.csv is ~1 MB per run; the
        # repo keeps no file over 1 MB except the demo media)
        opener = gzip.open if path.endswith(".gz") else open
        with opener(path, "rt", newline="") as fh:
            rows = list(csv.reader(fh))
        self.header = rows[0]
        if len(self.header) != TAU0 + 24:
            raise SystemExit(f"{path}: unexpected trace header "
                             f"({len(self.header)} columns)")
        self.rows = [[float(v) for v in r] for r in rows[1:]]
        if not self.rows:
            raise SystemExit(f"{path}: no trace rows")
        a = np.asarray(self.rows)
        self.t = a[:, 0]
        self.pos = a[:, 1:4]                 # base_link xyz
        self.quat = a[:, 4:8]                # base_link wxyz
        self.roll = a[:, 8]
        self.pitch = a[:, 9]
        self.tilt = a[:, 10]
        self.fz = a[:, 11]
        self.tau_peak = a[:, 12]
        self.tau_frac = a[:, 13]
        self.qpos = a[:, QPOS0:QPOS0 + 24]   # 24 hinge joints
        self.tau = a[:, TAU0:TAU0 + 24]

    def __len__(self):
        return len(self.rows)

    def index_at(self, t):
        """Index of the row nearest time t (the trace is uniform)."""
        return int(np.argmin(np.abs(self.t - t)))


class Renderer:
    """MuJoCo offscreen renderer over the judged scene, driven by a Trace."""

    def __init__(self, scene, width=1920, height=1080):
        self.model = mujoco.MjModel.from_xml_path(scene)
        self.data = mujoco.MjData(self.model)
        mujoco.mj_forward(self.model, self.data)
        self.width, self.height = width, height
        self.renderer = mujoco.Renderer(self.model, height, width)
        self.cam = mujoco.MjvCamera()

    def set_state(self, trace, k):
        """Load trace row k into the model (base free joint + 24 hinges)."""
        d = self.data
        d.qpos[:3] = trace.pos[k]
        d.qpos[3:7] = trace.quat[k]
        d.qpos[7:] = trace.qpos[k]
        mujoco.mj_forward(self.model, d)

    def aim(self, distance=2.35, azimuth=132.0, elevation=-4.0,
            lookat_z=0.86):
        d = self.data
        self.cam.lookat[:] = [float(d.qpos[0]), float(d.qpos[1]), lookat_z]
        self.cam.distance = distance
        self.cam.azimuth = azimuth
        self.cam.elevation = elevation

    def render(self):
        self.renderer.update_scene(self.data, camera=self.cam)
        return self.renderer.render()
