#!/usr/bin/env python3
"""project.py — analytic projection helpers shared by the stage-2 gates.

Everything here is computed from the scene USD with pxr on the CPU and
compared against the rendered frames; the math mirrors the verified
reference implementation (agent-infra examples/gpu/omniverse_smoke.py):
project the world-space bbox corners through the camera's
world-to-local (view) matrix using the SAME aperture/focal parameters
the USD camera carries, then compare pixel rectangles.

No matplotlib, no invented numbers: every function returns measured
quantities with units in their names.
"""

from __future__ import annotations

import itertools
import math

from pxr import Gf, Usd, UsdGeom


def find_camera(stage: Usd.Stage) -> UsdGeom.Camera:
    cams = [UsdGeom.Camera(p) for p in stage.Traverse()
            if p.IsA(UsdGeom.Camera)]
    if not cams:
        raise ValueError("scene has no Camera prim")
    return cams[0]


def camera_matrix(stage: Usd.Stage, t: float) -> tuple[Gf.Matrix4d, float,
                                                       float, float, float]:
    """(world-to-camera matrix, fx, fy, cx, cy) in PIXELS for time t (s).

    fx = W * focal / horizontalAperture, exactly the smoke-test formula;
    the USD camera prim carries camera-to-world, so the view matrix is
    its inverse."""
    cam = find_camera(stage)
    prim = cam.GetPrim()
    xf = UsdGeom.XformCache(Usd.TimeCode(t * stage.GetTimeCodesPerSecond()))
    c2w = xf.GetLocalToWorldTransform(prim)
    view = c2w.GetInverse()

    focal = float(cam.GetFocalLengthAttr().Get(Usd.TimeCode(
        t * stage.GetTimeCodesPerSecond())))
    ha = float(cam.GetHorizontalApertureAttr().Get())
    va = float(cam.GetVerticalApertureAttr().Get())
    # RenderProduct resolution (authored by render_job.author_wrapper);
    # read from the stage so a resolution change needs no edit here.
    w = h = None
    for p in stage.Traverse():
        if p.GetTypeName() == "UsdRenderProduct":
            res = p.GetAttribute("resolution").Get()
            if res:
                w, h = int(res[0]), int(res[1])
            break
    if not w:
        w, h = 1920, 1080
    fx = w * focal / ha
    fy = h * focal / va
    return view, fx, fy, w / 2.0, h / 2.0


def project_prim_bbox(stage: Usd.Stage, prim_path: str, t: float) -> dict:
    """Project the tracked prim's world bbox at time t (s).

    Returns {bbox_px: [x0, y0, x1, y1], visible: bool, z_min, z_max}
    where y is the IMAGE row (down-positive) and z is camera-space
    depth (negative in front of the camera, USD convention)."""
    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsActive():
        return {"bbox_px": None, "visible": False}
    tc = Usd.TimeCode(t * stage.GetTimeCodesPerSecond())
    cache = UsdGeom.BBoxCache(tc, ["default", "render"])
    bound = cache.ComputeWorldBound(prim)
    rng = bound.ComputeAlignedRange()
    if rng.IsEmpty():
        return {"bbox_px": None, "visible": False}
    lo, hi = list(rng.GetMin()), list(rng.GetMax())

    view, fx, fy, cx, cy = camera_matrix(stage, t)
    corners = [[*p, 1.0] for p in itertools.product(*zip(lo, hi))]
    # Gf's `M * v` computes M@v, but the camera transform is applied as a
    # row-vector product (v@M) — the verified smoke-test convention.  Use
    # `v * view` (== np.array(v) @ np.array(view)).
    pts = [Gf.Vec4d(*c) * view for c in corners]
    front = [p for p in pts if p[2] < -1e-6]
    if not front:
        return {"bbox_px": None, "visible": False}
    xs = [cx + p[0] / -p[2] * fx for p in front]
    ys = [cy - p[1] / -p[2] * fy for p in front]
    return {
        "bbox_px": [min(xs), min(ys), max(xs), max(ys)],
        "visible": True,
        "z_min": min(p[2] for p in front),
        "z_max": max(p[2] for p in front),
    }


def rect_iou(a, b) -> float:
    """IoU of two [x0, y0, x1, y1] rectangles; 0.0 when either is None."""
    if not a or not b:
        return 0.0
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


# --------------------------------------------------------------------------- #
# PhysX energy from the baked trajectory (deterministic, USD-only)
# --------------------------------------------------------------------------- #
def _quat_mul(a, b):
    w1, x1, y1, z1 = a
    w2, x2, y2, z2 = b
    return (w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
            w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2)


def _quat_conj(q):
    return (q[0], -q[1], -q[2], -q[3])


def baked_body_energy(stage: Usd.Stage, prim_path: str, mass_kg: float,
                      dims_m: tuple[float, float, float],
                      frame_a: int, frame_b: int, fps: float = 30.0) -> dict:
    """Translational + rotational KE of a baked rigid body between two frames.

    Velocities are finite differences of the baked time samples — the
    same samples the renderer displayed, so this measures the trajectory
    the viewer saw, not a re-simulation."""
    prim = stage.GetPrimAtPath(prim_path)
    if not prim:
        return {"ke_j": None, "speed_mps": None}
    tattr = prim.GetAttribute("xformOp:translate")
    oattr = prim.GetAttribute("xformOp:orient")
    ta = tattr.Get(frame_a)
    tb = tattr.Get(frame_b)
    qa = oattr.Get(frame_a)
    qb = oattr.Get(frame_b)
    # pxr quats are not iterable; take (w, x, y, z) explicitly
    qa = (float(qa.GetReal()), float(qa.GetImaginary()[0]),
          float(qa.GetImaginary()[1]), float(qa.GetImaginary()[2]))
    qb = (float(qb.GetReal()), float(qb.GetImaginary()[0]),
          float(qb.GetImaginary()[1]), float(qb.GetImaginary()[2]))
    dt = (frame_b - frame_a) / fps
    if ta is None or tb is None or qa is None or qb is None or dt <= 0:
        return {"ke_j": None, "speed_mps": None}

    v = [(float(tb[i]) - float(ta[i])) / dt for i in range(3)]
    ke_lin = 0.5 * mass_kg * sum(c * c for c in v)

    dq = _quat_mul(qb, _quat_conj(qa))
    if dq[0] < 0:                       # shortest arc
        dq = tuple(-c for c in dq)
    n = math.sqrt(sum(c * c for c in dq[1:4]))
    angle = 2.0 * math.atan2(n, dq[0])
    if n < 1e-12:
        omega = [0.0, 0.0, 0.0]
    else:
        axis = [dq[1 + i] / n for i in range(3)]
        omega = [angle / dt * c for c in axis]
    dx, dy, dz = dims_m
    ixx = mass_kg * (dy ** 2 + dz ** 2) / 12.0
    iyy = mass_kg * (dx ** 2 + dz ** 2) / 12.0
    izz = mass_kg * (dx ** 2 + dy ** 2) / 12.0
    ke_rot = 0.5 * (ixx * omega[0] ** 2 + iyy * omega[1] ** 2
                    + izz * omega[2] ** 2)
    return {"ke_j": round(ke_lin + ke_rot, 6),
            "speed_mps": round(math.sqrt(sum(c * c for c in v)), 6),
            "omega_rps": round(math.sqrt(sum(c * c for c in omega)), 6)}
