#!/usr/bin/env python3
"""Render a judge trace (extruded beads + travel moves) with pyvista offscreen.

Input:  <label>.trace.json written by judge.py --trace (interpreter replay of
        the artifact's part.gcode: extruding moves, travel moves, layer Zs).
Output: PNG frames. Beads are tubes of the real line width (0.42 mm), coloured
        by layer height; travel moves are thin grey lines; the print bed is a
        translucent plane. The bracket STL (judge's own task/make_stl.py mesh)
        can be shown beside/behind at the same scale.

Every number comes from the trace / verdict JSON -- nothing is invented.
"""

import json
import os
import sys

import numpy as np
import pyvista as pv

HERE = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(HERE)

# print geometry (from task/spec.json / good verdict)
LINE_WIDTH = 0.42          # line_width in profile.ini
BED_X, BED_Y = 250.0, 210.0
PART_TOP = 15.0            # bracket height

# camera/view defaults (fit the 40x20x15 part with skirt on the 250x210 bed)
# bracket bbox 20..60 x 20..40 x 0..15 mm (STL min corner 20,20 per make_stl.py)
TARGET = (40.0, 30.0, 7.5)   # bracket centre
VIEW_AZIMUTH = -58.0         # degrees around +Z, from +X axis
VIEW_ELEVATION = 24.0        # degrees above the bed plane
VIEW_DIST = 150.0            # camera distance from the target (mm)


def bead_mesh(trace, radius=LINE_WIDTH / 2.0, sides=6, layer_subset=None):
    """Tube beads for extruding moves. Returns (PolyData, per-vertex layer_z).

    layer_subset: iterable of layer indices to keep (None = all). Moves are
    kept whole (a move is not split at a layer boundary).
    """
    extr = np.asarray(trace["extr"], dtype=float)  # (z, x0, y0, x1, y1, dE, feed)
    layer_of = trace["layer_of_extr"]
    if layer_subset is not None:
        keep = np.array([i for i, l in enumerate(layer_of) if l in layer_subset])
        if len(keep) == 0:
            return None, None
        extr = extr[keep]
        layer_of = [layer_of[i] for i in keep]
    n = len(extr)
    if n == 0:
        return None, None

    p0 = np.stack([extr[:, 1], extr[:, 2], extr[:, 0]], axis=1)
    p1 = np.stack([extr[:, 3], extr[:, 4], extr[:, 0]], axis=1)
    d = p1 - p0
    L = np.linalg.norm(d, axis=1)
    ok = L > 1e-4
    p0, p1, d, L = p0[ok], p1[ok], d[ok], L[ok]
    extr, layer_of = extr[ok], [l for l, k in zip(layer_of, ok) if k]
    n = len(p0)
    if n == 0:
        return None, None

    a = d / L[:, None]
    ref = np.where(np.abs(a[:, 2:3]) < 0.9,
                   np.tile([0.0, 0.0, 1.0], (n, 1)),
                   np.tile([1.0, 0.0, 0.0], (n, 1)))
    u = np.cross(a, ref)
    u /= np.linalg.norm(u, axis=1)[:, None]
    v = np.cross(a, u)
    th = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    ring = (np.cos(th)[None, None, :] * u[:, :, None]
            + np.sin(th)[None, None, :] * v[:, :, None])      # (n,3,sides)
    rad = np.full((n, 1, 1), radius)
    A = p0[:, :, None] + ring * rad
    B = p1[:, :, None] + ring * rad
    nv = 2 * sides
    pts = np.concatenate([A, B], axis=2).transpose(0, 2, 1).reshape(-1, 3)
    idx = np.arange(n * nv).reshape(n, nv)
    i0, i1 = idx[:, :sides], idx[:, sides:]
    faces = []
    for k in range(sides):
        k2 = (k + 1) % sides
        f = np.stack([np.stack([i0[:, k], i0[:, k2], i1[:, k]], axis=1),
                      np.stack([i1[:, k], i1[:, k2], i0[:, k2]], axis=1)],
                     axis=1).reshape(-1, 3)
        faces.append(f)
    faces = np.concatenate(faces)
    pd = pv.PolyData(pts, np.column_stack(
        [np.full(len(faces), 3), faces]).ravel())
    layers_z = trace["layers_z"]
    zvals = np.array([layers_z[l] for l in layer_of])
    pd["layer_z"] = np.repeat(zvals, nv)
    return pd, zvals


def travel_mesh(trace, max_z=None):
    """Thin grey line segments for travel moves (optionally only z <= max_z)."""
    tv = np.asarray(trace["travel"], dtype=float)
    if max_z is not None:
        tv = tv[tv[:, 0] <= max_z + 1e-9]
    if len(tv) == 0:
        return None
    n = len(tv)
    pts = np.empty((2 * n, 3))
    pts[0::2] = np.stack([tv[:, 1], tv[:, 2], tv[:, 0]], axis=1)
    pts[1::2] = np.stack([tv[:, 3], tv[:, 4], tv[:, 0]], axis=1)
    lines = np.column_stack([np.full(n, 2), 2 * np.arange(n),
                             2 * np.arange(n) + 1]).ravel()
    return pv.PolyData(pts, lines)


def bracket_mesh():
    """The bracket STL as the judge's task/make_stl.py writes it (deterministic).

    make_stl.py is stdlib-only and writes the same mesh the judge grades;
    generate it into a temp dir rather than shipping a binary.
    """
    import subprocess
    import tempfile
    tmp = tempfile.mkdtemp(prefix="media-stl-")
    subprocess.run([sys.executable, os.path.join(DEMO, "task", "make_stl.py"),
                    "--outdir", tmp], check=True, stdout=subprocess.DEVNULL)
    return pv.read(os.path.join(tmp, "bracket.stl"))


def make_plotter(shape=(1920, 1080)):
    pl = pv.Plotter(off_screen=True, window_size=shape)
    pl.set_background("#101418")
    return pl


def add_bed(pl):
    bed = pv.Plane(center=(BED_X / 2, BED_Y / 2, -0.06),
                   i_size=BED_X, j_size=BED_Y, direction=(0, 0, 1))
    pl.add_mesh(bed, color="#3a4150", opacity=0.55, ambient=0.4,
                diffuse=0.6, specular=0.1)
    # bed border
    edge = pv.Line((0, 0, 0), (BED_X, 0, 0))
    for (p0, p1) in [((0, 0, 0), (BED_X, 0, 0)),
                     ((BED_X, 0, 0), (BED_X, BED_Y, 0)),
                     ((BED_X, BED_Y, 0), (0, BED_Y, 0)),
                     ((0, BED_Y, 0), (0, 0, 0))]:
        pl.add_mesh(pv.Line(p0, p1), color="#5b6472", line_width=1.5)


def camera_part(pl, azimuth=VIEW_AZIMUTH, elevation=VIEW_ELEVATION,
                dist=VIEW_DIST, target=TARGET):
    """Deterministic camera: position = target + dist along the az/el ray."""
    import math
    az = math.radians(azimuth)
    el = math.radians(elevation)
    pl.camera.focal_point = target
    pl.camera.position = (target[0] + dist * math.cos(el) * math.cos(az),
                         target[1] + dist * math.cos(el) * math.sin(az),
                         target[2] + dist * math.sin(el))
    pl.camera.view_up = (0.0, 0.0, 1.0)


def render_frame(trace, out_path, layer_upto=None, show_stl=False,
                 azimuth=VIEW_AZIMUTH, elevation=VIEW_ELEVATION,
                 bead_cmap="plasma", dim_old=False, title=None):
    """Render one frame. layer_upto: show only layers <= this index
    (None = the finished print)."""
    pl = make_plotter()
    add_bed(pl)
    subset = None if layer_upto is None else set(range(layer_upto + 1))
    pd, zvals = bead_mesh(trace, layer_subset=subset)
    if pd is not None and pd.n_points:
        opacity = 0.55 if dim_old else 1.0
        pl.add_mesh(pd, scalars="layer_z", cmap=bead_cmap, smooth_shading=True,
                    specular=0.35, specular_power=24, diffuse=0.8,
                    ambient=0.3, opacity=opacity)
    # travel moves up to the highest shown bead layer
    if layer_upto is not None and trace["layers_z"]:
        maxz = trace["layers_z"][layer_upto]
    else:
        maxz = None
    tv = travel_mesh(trace, max_z=maxz)
    if tv is not None:
        pl.add_mesh(tv, color="#9aa2ad", line_width=1.0, opacity=0.8)
    if show_stl:
        stl = bracket_mesh()
        pl.add_mesh(stl, color="#2e6f9e", opacity=0.28, smooth_shading=True,
                    specular=0.2, diffuse=0.7, ambient=0.35)
    camera_part(pl, azimuth, elevation)
    pl.screenshot(out_path)
    pl.close()


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("trace")
    ap.add_argument("out")
    ap.add_argument("--layer-upto", type=int, default=None)
    ap.add_argument("--stl", action="store_true")
    ap.add_argument("--azimuth", type=float, default=VIEW_AZIMUTH)
    ap.add_argument("--elevation", type=float, default=VIEW_ELEVATION)
    args = ap.parse_args()
    trace = json.load(open(args.trace))
    render_frame(trace, args.out, layer_upto=args.layer_upto,
                 show_stl=args.stl, azimuth=args.azimuth,
                 elevation=args.elevation)
    print("wrote", args.out)


if __name__ == "__main__":
    main()
