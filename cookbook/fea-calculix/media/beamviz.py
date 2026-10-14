#!/usr/bin/env python3
"""Shared helpers to draw the real CalculiX beam field (work/<case>/fields.npz).

The mesh drawn is exactly the judge-generated mesh.inc the solver consumed;
displacements and von Mises are the nodal values ccx wrote to job.frd
(von Mises from the .frd stress components, same formula as the judge).
Rendering is an orthographic projection + painter-sorted PolyCollection,
no data is resampled or smoothed.
"""
import os
import numpy as np

MEDIA = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(MEDIA, "work")

# C3D8 boundary faces, node indices per face (0-based within element)
HEX_FACES = ((0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7))


def load_fields(case):
    """Return dict(coords, conn, disp, vm) for a solved work/<case>."""
    p = os.path.join(WORK, case, "fields.npz")
    if not os.path.exists(p):
        raise SystemExit(f"missing {p} -- run media/solve_fields.py first")
    z = np.load(p)
    return dict(coords=z["coords"], conn=z["conn"],
                disp=z["disp"], vm=z["vm"])


def boundary_faces(conn):
    """Return (K,4) node-index quads of faces owned by exactly one element."""
    faces = conn[:, list(HEX_FACES)].reshape(-1, 4)          # (6M,4)
    key = np.sort(faces, axis=1)
    order = np.lexsort(key.T[::-1])
    sk = key[order]
    same = np.all(sk[1:] == sk[:-1], axis=1)
    shared = np.zeros(len(sk), bool)
    shared[1:] |= same
    shared[:-1] |= same
    return faces[order[~shared]]


def view_axes(elev_deg, azim_deg):
    """Screen basis for an orthographic camera at (elev, azim)."""
    el, az = np.radians(elev_deg), np.radians(azim_deg)
    view = np.array([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az),
                     np.sin(el)])
    right = np.cross(view, [0., 0., 1.])
    right /= np.linalg.norm(right)
    up = np.cross(right, view)
    return view, right, up


def project(xyz, elev_deg=15.0, azim_deg=-75.0):
    """xyz (...,3) -> (x2, y2, depth) each (...,)."""
    view, right, up = view_axes(elev_deg, azim_deg)
    return xyz @ right, xyz @ up, xyz @ view


def face_draw_order(face_xyz, elev_deg=15.0, azim_deg=-75.0):
    """Painter order: far faces first. Returns (verts2d (K,4,2), order, depth)."""
    _, right, up = view_axes(elev_deg, azim_deg)
    pts = np.stack([face_xyz @ right, face_xyz @ up], axis=-1)
    depth = face_xyz @ view_axes(elev_deg, azim_deg)[0]
    order = np.argsort(depth.mean(axis=1), kind="stable")
    return pts[order], order


def hull2d(pts):
    """Convex hull of 2-D points (N,2) -> (M,2) CCW, monotonic chain."""
    pts = sorted(set(map(tuple, pts)))
    if len(pts) <= 2:
        return np.array(pts)

    def cross(o, a, b):
        return ((a[0] - o[0]) * (b[1] - o[1])
                - (a[1] - o[1]) * (b[0] - o[0]))

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return np.array(lower[:-1] + upper[:-1])


def undeformed_outline(ax, xyz_min, xyz_max, elev_deg, azim_deg, **kw):
    """Silhouette of the undeformed box under the same orthographic
    projection -- a straight outline, not a full wireframe (interior
    edges of a projected wireframe read as a tilted/bent box).
    Returns the hull vertices so callers can place a label."""
    x0, y0, z0 = xyz_min
    x1, y1, z1 = xyz_max
    corners = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
                        [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]])
    cx, cy, _ = project(corners, elev_deg, azim_deg)
    hull = hull2d(np.column_stack([cx, cy]))
    ax.plot(np.r_[hull[:, 0], hull[0, 0]],
            np.r_[hull[:, 1], hull[0, 1]], **kw)
    return hull
