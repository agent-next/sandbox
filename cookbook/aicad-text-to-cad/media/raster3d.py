"""A small real 3D renderer for the demo video's turntable (v0).

numpy z-buffered perspective rasterizer -- no matplotlib, no GL.  It
renders the actual delivered STL facets: rotate -> project -> Gouraud
shade (Lambert + Blinn-Phong on shared-vertex normals) -> z-buffered
triangle fill, supersampled 2x and downsampled with Pillow.  A frame of
a ~1000-facet part takes well under a second at 1080p.
"""
import struct

import numpy as np
from PIL import Image

BG_TOP = (0.945, 0.950, 0.958)     # light figure-style backdrop gradient
BG_BOT = (1.0, 1.0, 1.0)

# three-point studio lighting (directions point towards the scene)
LIGHTS = np.array([
    [0.42, 0.34, 0.84],      # key
    [-0.62, 0.18, 0.40],     # fill
    [-0.05, -0.72, 0.44],    # rim from below
])
LIGHT_W = np.array([0.95, 0.45, 0.30])
AMBIENT = 0.30
SPEC = 0.22


def load_stl(path):
    """Binary STL -> (faces (n, 3, 3), normals (n, 3)) float64.

    The writer's stored facet normals are kept: for planar faces they are
    the surface normal, immune to the float error that a cross product of
    the long sliver triangles a CAD kernel emits would introduce (which
    shows up as spurious radial shading wedges).  A zero stored normal is
    recomputed from the facet.
    """
    with open(path, "rb") as f:
        blob = f.read()
    n = struct.unpack("<I", blob[80:84])[0]
    rec = np.frombuffer(blob[84:84 + 50 * n], dtype=np.uint8).reshape(n, 50)
    tri = np.asarray(rec[:, :48].copy().view("<f4").reshape(n, 4, 3),
                     dtype=np.float64)
    normals = tri[:, 0, :]
    faces = tri[:, 1:, :]
    bad = np.linalg.norm(normals, axis=1) < 1e-9
    if bad.any():
        nrm = np.cross(faces[bad, 1] - faces[bad, 0],
                       faces[bad, 2] - faces[bad, 0])
        normals[bad] = nrm / np.maximum(
            np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    return faces, normals


def _rot(azim_deg, elev_deg):
    a, e = np.radians(azim_deg), np.radians(elev_deg)
    ca, sa, ce, se = np.cos(a), np.sin(a), np.cos(e), np.sin(e)
    rz = np.array([[ca, -sa, 0.0], [sa, ca, 0.0], [0.0, 0.0, 1.0]])
    rx = np.array([[1.0, 0.0, 0.0], [0.0, ce, -se], [0.0, se, ce]])
    return rx @ rz                      # spin about Z, then tilt to camera


def _shade(nrm, base):
    """(m, 3) unit normals -> (m, 3) lit colours, 0..1."""
    view = np.array([0.0, 0.0, 1.0])    # camera far along +Z
    lit = np.full((len(nrm), 3), AMBIENT) * base
    for lw, ld in zip(LIGHT_W, LIGHTS):
        ld = ld / np.linalg.norm(ld)
        diff = np.clip(nrm @ ld, 0.0, None)
        lit += base * (0.62 * lw * diff[:, None])
        half = (ld + view) / np.linalg.norm(ld + view)
        spec = np.clip(nrm @ half, 0.0, None) ** 30.0
        lit += SPEC * lw * spec[:, None]
    return lit


CREASE_DEG = 20.0          # STL dihedral angle below which faces smooth


def _vertex_normals(V, n):
    """Gouraud normals, creases preserved.

    Coincident vertices hash together.  Each corner (vertex, face) gets the
    area-weighted mean of only those incident faces whose normal lies within
    CREASE_DEG of its own, so a tessellated cylinder (9-degree steps) shades
    smoothly while a flat face meeting a wall at 90 degrees keeps its own
    normal instead of spilling into a cone.
    """
    verts = V.reshape(-1, 3)
    keys = np.round(verts / 1e-6).astype(np.int64)
    uniq, inv = np.unique(keys, axis=0, return_inverse=True)
    tri = inv.reshape(-1, 3)                           # (n, 3) vertex ids
    area = np.linalg.norm(n, axis=1)                   # face areas
    flat_v = tri.reshape(-1)
    flat_f = np.repeat(np.arange(len(n)), 3)
    order = np.argsort(flat_v, kind="stable")
    bounds = np.searchsorted(flat_v[order], np.arange(len(uniq) + 1))
    cos_t = np.cos(np.radians(CREASE_DEG))
    out = np.empty((len(n), 3, 3))                     # per corner
    for v in range(len(uniq)):
        lo, hi = bounds[v], bounds[v + 1]
        if lo == hi:
            continue
        fs = flat_f[order[lo:hi]]
        sub = n[fs]                                    # (m, 3)
        w = (sub @ sub.T >= cos_t) * area[fs][None, :]  # (m, m) mask * area
        vn = w @ sub
        vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
        for k, f in enumerate(fs):                     # scatter to corners
            out[f][tri[f] == v] = vn[k]
    return out


def render(faces, normals, width, height, azim, elev, dist=3.6, fit=0.66,
           base=(0.72, 0.75, 0.79), ss=2, smooth=False):
    """One RGB frame of the mesh at (azim, elev) degrees, exact-fit
    framed: the projected bbox is centred and scaled to ~fit of the
    frame height (capped at 88 % of the width).

    smooth=False (default) shades each facet flat -- the clean solid look
    of a CAD viewer, and free of the Gouraud wedges a fan-triangulated
    planar face produces.  smooth=True averages normals at each vertex
    (creases above CREASE_DEG preserved) for rounder cylinders.
    """
    W, H = width * ss, height * ss
    v = faces.reshape(-1, 3)
    cen = (v.min(0) + v.max(0)) / 2.0
    size = float(np.max(v.max(0) - v.min(0)))
    if size <= 0:
        raise ValueError("degenerate mesh")
    R = _rot(azim, elev)
    V = ((faces - cen) / size) @ R.T                   # (n, 3, 3), centred
    n = normals @ R.T
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    # keep only facets whose winding faces the camera at (0, 0, dist)
    front = np.einsum("ij,ij->i", n, V.mean(1) - (0.0, 0.0, dist)) < 0
    V, n = V[front], n[front]
    if smooth:
        vn = _vertex_normals(V, n)
        col = (_shade(vn.reshape(-1, 3), np.asarray(base)).reshape(
            V.shape[0], 3, 3) * 255.0 + 0.5).astype(np.uint8)
    else:
        col = (_shade(n, np.asarray(base)) * 255.0 + 0.5).astype(np.uint8)

    def project(f):
        pz = dist - V[:, :, 2]
        return f * V[:, :, 0] / pz, f * V[:, :, 1] / pz

    f0 = float(H)
    px, py = project(f0)                       # probe pass: measure bbox
    w0 = px.max() - px.min()
    h0 = py.max() - py.min()
    f1 = f0 * min(fit * H / max(h0, 1e-9), 0.88 * W / max(w0, 1e-9))
    px, py = project(f1)                       # final pass: centre exactly
    px += W / 2.0 - (px.min() + px.max()) / 2.0
    py += H / 2.0 - (py.min() + py.max()) / 2.0
    depth = dist - V[:, :, 2]                  # smaller = nearer

    img = np.empty((H, W, 3), np.uint8)
    ramp = (np.linspace(BG_TOP, BG_BOT, H) * 255.0 + 0.5).astype(np.uint8)
    img[:] = ramp[:, None, :]
    zbuf = np.full((H, W), np.inf)

    for i in range(len(V)):
        ix0 = max(int(px[i].min()) - 1, 0)
        ix1 = min(int(px[i].max()) + 2, W)
        iy0 = max(int(py[i].min()) - 1, 0)
        iy1 = min(int(py[i].max()) + 2, H)
        if ix0 >= ix1 or iy0 >= iy1:
            continue
        ax, ay = px[i, 0], py[i, 0]
        bx, by = px[i, 1], py[i, 1]
        cx, cy = px[i, 2], py[i, 2]
        area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        if area == 0.0:
            continue
        inv = 1.0 / area
        gx = np.arange(ix0, ix1, dtype=np.float64)[None, :] + 0.5
        gy = np.arange(iy0, iy1, dtype=np.float64)[:, None] + 0.5
        w0 = ((bx - ax) * (gy - ay) - (by - ay) * (gx - ax)) * inv
        w1 = ((cx - bx) * (gy - by) - (cy - by) * (gx - bx)) * inv
        w2 = ((ax - cx) * (gy - cy) - (ay - cy) * (gx - cx)) * inv
        m = (w0 >= 0.0) & (w1 >= 0.0) & (w2 >= 0.0)
        if not m.any():
            continue
        z = (w0 * depth[i, 0] + w1 * depth[i, 1] + w2 * depth[i, 2])
        sub = zbuf[iy0:iy1, ix0:ix1]
        upd = (sub > z) & m
        if not upd.any():
            continue
        sub[upd] = z[upd]
        rgb = (w0[..., None] * col[i, 0] + w1[..., None] * col[i, 1]
               + w2[..., None] * col[i, 2])
        rgb = np.clip(rgb, 0.0, 255.0)      # guard fp overshoot in the cast
        img[iy0:iy1, ix0:ix1][upd] = rgb[upd].astype(np.uint8)

    if ss > 1:
        img = np.asarray(
            Image.fromarray(img).resize((width, height), Image.LANCZOS))
    return Image.fromarray(img)
