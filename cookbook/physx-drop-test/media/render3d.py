#!/usr/bin/env python3
"""render3d.py — deterministic software 3D renderer for the drop scene.

The pinned ovphysx wheel is simulation-only: it ships no renderer (its
package contains the PhysX API, types, population and schemas modules and
nothing to draw with), so this module renders the simulator's OWN per-step
samples — judge_runs/traces/good/traj.npz, the exact trajectory the gates
graded — as a shaded perspective 3D view of the authored geometry.

Everything is plain numpy (fixed camera maths, fixed light, no randomness):
two runs render byte-identical frames.  The camera-dependent background
(sky, ground grid, shadows base) is cached per camera, so a fixed-camera
shot only pays for the moving bodies; a fresh orbit camera rebuilds it.

Coordinate system: Y up, ground plane y = 0, box at x = -0.5, ball at
x = +0.5, camera orbits the scene.  Output is a WxHx3 uint8 RGB array.
"""

import numpy as np

# scene constants (SPEC.md) -------------------------------------------------
F32 = np.float32   # every hot array is float32: 2M-pixel frames render ~4x
                   # faster than float64, with identical uint8 output
BOX_X = -0.5
BALL_X = 0.5
HALF = 0.10           # box half-extent == ball radius == resting height
GROUND_EXTENT = 7.0   # ground half-size in metres (visual only)
GRID = 0.25           # ground grid spacing in metres (visual only)
G = 9.81

# palette (dark video theme; colour-blind-safe accents) ----------------------
SKY_TOP = np.array([0.078, 0.086, 0.110], F32)
SKY_BOT = np.array([0.220, 0.235, 0.270], F32)
GROUND = np.array([0.430, 0.445, 0.480], F32)
GRID_C = np.array([0.640, 0.655, 0.690], F32)
BOX_C = np.array([0.212, 0.529, 0.878], F32)     # blue
BALL_C = np.array([0.980, 0.522, 0.267], F32)    # orange
GHOST_C = np.array([0.880, 0.890, 0.920], F32)
WHITE = np.array([1.0, 1.0, 1.0], F32)
GREEN8 = (46, 214, 92)
LIGHT_DIR = np.array([0.45, 0.80, 0.35], F32)
LIGHT_DIR = (LIGHT_DIR / np.linalg.norm(LIGHT_DIR)).astype(F32)


class Camera:
    """Perspective camera; orbit defined by eye/target in metres."""

    def __init__(self, eye, target, fov_y_deg=42.0, w=960, h=540):
        self.eye = np.asarray(eye, F32)
        self.target = np.asarray(target, F32)
        self.f = np.float32(1.0 / np.tan(np.radians(fov_y_deg) / 2.0))
        self.w, self.h = w, h
        fwd = self.target - self.eye
        self.fwd = fwd / np.linalg.norm(fwd)
        world_up = np.array([0.0, 1.0, 0.0], F32)
        if abs(np.dot(self.fwd, world_up)) > 0.999:
            world_up = np.array([0.0, 0.0, 1.0], F32)
        self.right = np.cross(self.fwd, world_up)
        self.right /= np.linalg.norm(self.right)
        self.up = np.cross(self.right, self.fwd)
        self.fwd = self.fwd.astype(F32)
        self.right = self.right.astype(F32)
        self.up = self.up.astype(F32)

    def ray_dirs(self):
        """Unit ray directions for every pixel, shape (H, W, 3)."""
        ys, xs = np.mgrid[0:self.h, 0:self.w]
        ndc_x = ((xs + 0.5) / self.w * 2.0 - 1.0).astype(F32)
        ndc_y = (1.0 - (ys + 0.5) / self.h * 2.0).astype(F32)
        aspect = np.float32(self.w / self.h)
        d = (self.fwd[None, None, :]
             + ndc_x[..., None] * (aspect / self.f) * self.right[None, None, :]
             + ndc_y[..., None] / self.f * self.up[None, None, :])
        return (d / np.linalg.norm(d, axis=-1, keepdims=True)).astype(F32)

    def project(self, pts):
        """World points (N,3) -> pixel coords (N,2); z<=0 maps to nan."""
        pts = np.atleast_2d(np.asarray(pts, F32))
        v = pts - self.eye
        x = v @ self.right
        y = v @ self.up
        z = v @ self.fwd
        aspect = np.float32(self.w / self.h)
        with np.errstate(divide="ignore", invalid="ignore"):
            sx = x / (z / self.f * aspect)
            sy = y / (z / self.f)
            px = (sx * np.float32(0.5) + np.float32(0.5)) * self.w
            py = (np.float32(0.5) - sy * np.float32(0.5)) * self.h
        out = np.stack([px, py], axis=-1)
        out[z <= np.float32(1e-6)] = np.nan
        return out


# ---------------------------------------------------------------------------
# per-camera background cache (sky + ground grid): one entry, the last camera
_BG = {}


def _background(cam):
    """(img, depth, ground_mask, ground_points) for this camera."""
    key = (cam.w, cam.h, cam.eye.tobytes())
    if _BG.get("key") == key:
        return _BG["val"]
    w, h = cam.w, cam.h
    o = np.broadcast_to(cam.eye, (h, w, 3)).astype(F32).copy()
    d = cam.ray_dirs()

    tgrad = np.linspace(0.0, 1.0, h, dtype=F32)[:, None, None]
    img = (SKY_TOP[None, None, :] * (1 - tgrad) + SKY_BOT[None, None, :] * tgrad)
    img = np.ascontiguousarray(np.broadcast_to(img, (h, w, 3)))
    depth = np.full((h, w), np.inf, dtype=F32)

    with np.errstate(divide="ignore", invalid="ignore"):
        tg = np.where(d[..., 1] < np.float32(-1e-9), -o[..., 1] / d[..., 1],
                      np.float32(np.inf)).astype(F32)
    p = o + np.where(np.isfinite(tg), tg, 0.0)[..., None] * d
    p = p.astype(F32)
    inside = (np.abs(p[..., 0]) < GROUND_EXTENT) & \
             (np.abs(p[..., 2]) < GROUND_EXTENT) & (tg > np.float32(1e-6))
    tground = np.where(inside, tg, np.float32(np.inf)).astype(F32)

    # grid lines + checker tint + gentle distance fade (the checker gives
    # camera motion high contrast at any distance)
    gx = np.abs(np.mod(p[..., 0] + np.float32(GRID / 2), GRID)
                - np.float32(GRID / 2))
    gz = np.abs(np.mod(p[..., 2] + np.float32(GRID / 2), GRID)
                - np.float32(GRID / 2))
    line = (gx < 0.008) | (gz < 0.008)
    checker = (np.mod(np.floor(p[..., 0] / GRID) + np.floor(p[..., 2] / GRID),
                      2) < 1)[..., None]
    ground = np.where(checker, GROUND, GROUND * np.float32(0.72)).astype(F32)
    base = np.where(line[..., None], GRID_C[None, None, :], ground)
    m = np.isfinite(tground) & (tground < depth)
    col = base * np.float32(0.55 + 0.45 * float(LIGHT_DIR[1]))
    fade = np.clip(np.float32(1.15) - np.hypot(p[..., 0], p[..., 2])
                   * np.float32(0.14), 0.25, 1.0)[..., None].astype(F32)
    col = np.clip(SKY_BOT[None, None, :] * (1 - fade) + col * fade, 0, 1)
    img[m] = col[m]
    depth[m] = tground[m]
    inv = np.where(d != 0, np.float32(1.0) / np.where(d == 0, np.float32(1.0), d),
                   np.float32(np.inf)).astype(F32)
    _BG["key"] = key
    _BG["val"] = (img, depth, m, p, o, d, inv)
    return _BG["val"]


def _hit_aabb(o, d, inv, lo, hi):
    """Slab test.  Returns (t, normal, u, v); t=inf where missed.
    u,v are the face parametrisation in [0, 1] (for edge highlights).
    Normals/uvs are filled in only on hit pixels (they are sparse)."""
    lo = np.asarray(lo, F32)
    hi = np.asarray(hi, F32)
    t0 = (lo - o) * inv
    t1 = (hi - o) * inv
    tmin = np.minimum(t0, t1)
    tmax = np.maximum(t0, t1)
    tn = np.max(tmin, axis=-1)
    tf = np.min(tmax, axis=-1)
    hit = (tn <= tf) & (tn > 1e-6)
    t = np.where(hit, tn, np.inf)

    n = np.zeros_like(d)
    u = np.zeros(t.shape)
    v = np.zeros(t.shape)
    ii, jj = np.nonzero(hit)
    if len(ii):
        axis = np.argmax(tmin[ii, jj], axis=-1)
        dd = d[ii, jj]
        p = o[ii, jj] + t[ii, jj, None] * dd
        other = {0: (1, 2), 1: (0, 2), 2: (0, 1)}
        for a in (0, 1, 2):
            ma = axis == a
            if not ma.any():
                continue
            # normal sign: entering face opposes the ray direction on that axis
            sign = np.where(dd[ma, a] > 0, -1.0, 1.0)
            n[ii[ma], jj[ma], a] = sign
            i1, i2 = other[a]
            lo1, hi1 = lo[i1], hi[i1]
            lo2, hi2 = lo[i2], hi[i2]
            u[ii[ma], jj[ma]] = (p[ma, i1] - lo1) / (hi1 - lo1)
            v[ii[ma], jj[ma]] = (p[ma, i2] - lo2) / (hi2 - lo2)
    return t, n, u, v


def _hit_sphere(o, d, c, r):
    oc = o - np.asarray(c, F32)
    b = np.sum(oc * d, axis=-1)
    cc = np.sum(oc * oc, axis=-1) - r * r
    disc = b * b - cc
    hit = disc > 0
    sq = np.sqrt(np.where(hit, disc, 0))
    t = -b - sq
    t = np.where(hit & (t > 1e-6), t, np.inf)
    n = np.zeros_like(d)
    ii, jj = np.nonzero(np.isfinite(t))
    if len(ii):
        n[ii, jj] = (o[ii, jj] + t[ii, jj, None] * d[ii, jj] - c) / r
    return t, n


def _body_window(cam, center, r, pad=10):
    """Screen-space bounding box (row/col slices) of a sphere around `center`.

    Returns None when the body is entirely off-screen or behind the camera.
    """
    c = np.asarray(center, F32)
    corners = c + r * np.array([[1, 1, 1], [1, 1, -1], [1, -1, 1], [1, -1, -1],
                                 [-1, 1, 1], [-1, 1, -1], [-1, -1, 1], [-1, -1, -1]],
                                F32)
    sp = cam.project(corners)
    ok = np.isfinite(sp[:, 0]) & np.isfinite(sp[:, 1])
    if not ok.any():
        return None
    x0 = max(int(np.floor(sp[ok, 0].min())) - pad, 0)
    x1 = min(int(np.ceil(sp[ok, 0].max())) + pad, cam.w)
    y0 = max(int(np.floor(sp[ok, 1].min())) - pad, 0)
    y1 = min(int(np.ceil(sp[ok, 1].max())) + pad, cam.h)
    if x1 <= x0 or y1 <= y0:
        return None
    return slice(y0, y1), slice(x0, x1)


def render_frame(cam, box_y, ball_y, ghost_box_y=None, apex_line=None,
                 rest_line=True, trail=None):
    """One RGB frame (uint8), shape (cam.h, cam.w, 3).

    box_y/ball_y   : body centre heights (m) at this instant
    ghost_box_y    : analytic y0 - g t^2/2 ghost position for the box
    apex_line      : height (m) to draw the dashed analytic-apex line at
    rest_line      : draw the y_rest = 0.10 m judge pass line
    trail          : list of (x, y, z) past positions to draw as a trail
    """
    img, depth, m, p, o, d, inv = _background(cam)
    img = img.copy()
    depth = depth.copy()

    # contact shadows (soft dark ellipses on the ground under each body) ------
    for cx, cy, rad in ((BOX_X, box_y, HALF * 1.5), (BALL_X, ball_y, HALF)):
        if cy is None or not np.isfinite(cy):
            continue
        dist = np.hypot(p[..., 0] - cx, p[..., 2]) / max(rad, 1e-6)
        strength = 0.55 * np.clip(1.0 - cy / 1.4, 0.12, 1.0)
        sh = m & (dist < 1.0)
        img[sh] = np.clip(img[sh] * (1 - strength * (1 - dist[sh] ** 2))[..., None], 0, 1)

    def paint(win, t, n, base, u=None, v=None, glow=False):
        """Shade only the (sparse) hit pixels; t also z-buffers into depth.

        win (a row/col slice pair) is the screen window of the body: hits
        outside it are impossible, so painting is local to that block."""
        ii, jj = np.nonzero(np.isfinite(t) & (t < depth[win]))
        if len(ii) == 0:
            return
        nn = n[ii, jj]
        lam = np.maximum(nn @ LIGHT_DIR, 0.0)[:, None]
        col = base * (0.42 + 0.58 * lam)
        if u is not None and v is not None:
            uu, vv = u[ii, jj], v[ii, jj]
            edge = (uu < 0.055) | (uu > 0.945) | (vv < 0.055) | (vv > 0.945)
            col = np.where(edge[:, None], np.clip(col * 1.9, 0, 1), col)
        if glow:
            col = np.clip(col * 1.35, 0, 1)
        img[win][ii, jj] = np.clip(col, 0, 1)
        depth[win][ii, jj] = t[ii, jj]

    # ghost box (analytic free-fall position) ---------------------------------
    if ghost_box_y is not None and np.isfinite(ghost_box_y):
        win = _body_window(cam, (BOX_X, ghost_box_y, 0.0), HALF * np.sqrt(3))
        if win is not None:
            lo = [BOX_X - HALF, ghost_box_y - HALF, -HALF]
            hi = [BOX_X + HALF, ghost_box_y + HALF, HALF]
            tg_, ng_, ug_, vg_ = _hit_aabb(o[win], d[win], inv[win], lo, hi)
            ii, jj = np.nonzero(np.isfinite(tg_) & (tg_ < depth[win] + 0.5))  # over ground only
            if len(ii):
                lam = np.maximum(ng_[ii, jj] @ LIGHT_DIR, 0.0)[:, None]
                edge = (ug_[ii, jj] < 0.06) | (ug_[ii, jj] > 0.94) | \
                       (vg_[ii, jj] < 0.06) | (vg_[ii, jj] > 0.94)
                gcol = GHOST_C * (0.5 + 0.5 * lam)
                gcol = np.where(edge[:, None], WHITE[None, :], gcol)
                img[win][ii, jj] = np.clip(gcol * 0.38 + img[win][ii, jj] * 0.62, 0, 1)

    # box ----------------------------------------------------------------------
    win = _body_window(cam, (BOX_X, box_y, 0.0), HALF * np.sqrt(3))
    if win is not None:
        lo = [BOX_X - HALF, box_y - HALF, -HALF]
        hi = [BOX_X + HALF, box_y + HALF, HALF]
        tb, nb, ub, vb = _hit_aabb(o[win], d[win], inv[win], lo, hi)
        paint(win, tb, nb, BOX_C, u=ub, v=vb)

    # ball ---------------------------------------------------------------------
    win = _body_window(cam, (BALL_X, ball_y, 0.0), HALF)
    if win is not None:
        ts, ns = _hit_sphere(o[win], d[win], (BALL_X, ball_y, 0.0), HALF)
        paint(win, ts, ns, BALL_C, glow=True)

    img8 = np.clip(img * 255, 0, 255).astype(np.uint8)

    # overlays in screen space --------------------------------------------------
    if rest_line:
        _dashed_line(img8, cam, (-1.9, 0.004, 0), (1.9, 0.004, 0), GREEN8)
    if apex_line is not None:
        _dashed_line(img8, cam, (BALL_X - 0.45, apex_line, 0),
                     (BALL_X + 0.45, apex_line, 0), GREEN8)
    if trail:
        sp = cam.project(np.asarray(trail, F32))
        for k in range(0, len(sp)):
            fade_ = 0.12 + 0.5 * k / max(len(sp) - 1, 1)
            _disk(img8, sp[k], 2.5, (255, 255, 255), fade_)
    return img8


def _dashed_line(img8, cam, p0, p1, rgb, dash=0.75):
    """Dashed 3D segment projected to screen, 3px thick."""
    a, b = cam.project(np.array([p0, p1], F32))
    if np.isnan(a).any() or np.isnan(b).any():
        return
    n = int(np.hypot(*(b - a))) + 2
    seglen = np.hypot(*(b - a))
    on = (np.arange(n) * seglen / max(n - 1, 1)) % 24 < 14
    ts = np.linspace(0, 1, n)
    pts = a[None, :] + ts[:, None] * (b - a)[None, :]
    for P, keep in zip(pts, on):
        if not keep:
            continue
        x0, y0 = int(P[0]), int(P[1])
        h, w = img8.shape[:2]
        if 1 <= y0 < h - 1 and 1 <= x0 < w - 1:
            img8[y0 - 1:y0 + 2, x0 - 1:x0 + 2] = np.maximum(
                img8[y0 - 1:y0 + 2, x0 - 1:x0 + 2],
                np.array(rgb, np.uint8))


def _disk(img8, center, r, rgb, alpha):
    h, w = img8.shape[:2]
    if np.isnan(center).any():
        return
    x0, y0 = int(round(center[0])), int(round(center[1]))
    for yy in range(y0 - int(r) - 1, y0 + int(r) + 2):
        if not (0 <= yy < h):
            continue
        for xx in range(x0 - int(r) - 1, x0 + int(r) + 2):
            if not (0 <= xx < w):
                continue
            if (xx - x0) ** 2 + (yy - y0) ** 2 <= r * r:
                img8[yy, xx] = np.clip(
                    img8[yy, xx] * (1 - alpha) + np.array(rgb) * alpha,
                    0, 255).astype(np.uint8)


def orbit_camera(az_deg, el_deg, dist, target=(0.0, 0.42, 0.0),
                 fov_y_deg=42.0, w=960, h=540):
    az, el = np.radians(az_deg), np.radians(el_deg)
    t = np.asarray(target, F32)
    eye = t + np.float32(dist) * np.array([np.cos(az) * np.cos(el),
                                           np.sin(el),
                                           np.sin(az) * np.cos(el)], F32)
    return Camera(eye, t, fov_y_deg=fov_y_deg, w=w, h=h)
