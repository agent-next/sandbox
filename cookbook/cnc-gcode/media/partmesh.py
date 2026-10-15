#!/usr/bin/env python3
"""Build the demo's 3D solids from the judge's own material-removal output.

Every face of the solid rendered in `media/demo.mp4` comes from the
heightmap the judge computed from the G-code it parsed:
`media/data/trace_good/final.npz`, or a mutant's
`media/data/trace_mut/<name>/final.npz`.  Nothing here redraws the geometry
from the CAM script or from `spec.json` -- the judge's own 0.05 mm grid is
the single source of truth, and every vertex below sits on that grid, so a
mutant whose material removal differs gets a different solid (a gouge, a
swapped-arc scar, 6 mm terraces of leftover stock) rather than a re-drawn
copy of the good one.

The solid is the material still in the block after the program ran: the
stock box of `meta.json` with everything the judge recorded as removed
(``H < 0``) taken out, extruded down to the pocket floor and capped.  The
render shows a slice of the stock's 25 mm height; the visible height is
`media.read_mm` in `make_demo.py`, which only changes how much of the
already-cut block is in shot, never where the cuts are.

Used by make_demo.py.  Meshes are written under media/master/ (git-ignored).

Requires: numpy, trimesh, scikit-image, shapely.  Not needed to run the
demo -- only to rebuild media/demo.mp4 (see media/make_demo.sh).
"""
import json
import os

import numpy as np
import trimesh
from skimage import measure
from shapely.geometry import Polygon

DEMO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(DEMO, "media", "data")

# Colours: dataviz reference instance (light mode), so the render, the
# captions and the two figures read as one set.  TOP_RGB is the uncut stock
# face, FLOOR_RGB the machined floor; partmesh.colour_faces ramps between
# them by surface depth.
TOP_RGB = (0.906, 0.922, 0.937)
FLOOR_RGB = (0.478, 0.541, 0.588)


def orbit_pose(azimuth_deg, elevation_deg, distance, target=(0.0, 0.0, 0.0)):
    """Camera pose for a turntable orbit, in the OpenGL convention pyrender
    uses (the camera looks down its own -Z).

    Azimuth 0 looks at the block from +X with +Y to the left, elevation 0 is
    the horizon and 90 is straight down; +Z is up.
    """
    az, el = np.deg2rad(azimuth_deg), np.deg2rad(elevation_deg)
    # view direction (camera -> target), and the eye is the target minus it
    fwd = -np.array([np.cos(el) * np.cos(az),
                     np.cos(el) * np.sin(az),
                     np.sin(el)])
    eye = target - distance * fwd
    up = np.array([0.0, 0.0, 1.0])
    if abs(float(fwd @ up)) > 0.999:            # looking straight down
        up = np.array([0.0, 1.0, 0.0])
    right = np.cross(fwd, up)
    right /= np.linalg.norm(right)
    true_up = np.cross(right, fwd)
    pose = np.eye(4)
    pose[:3, 0] = right
    pose[:3, 1] = true_up
    pose[:3, 2] = -fwd                         # camera +Z points backwards
    pose[:3, 3] = eye
    return pose

#: how much of the 25 mm stock the render shows (mm).  Everything the judge
#: gates lives in the top 6 mm; a thinner block frames the pocket better.
READ_MM = 14.0


def trace_path(kind):
    """(final.npz, meta.json) for 'trace_good' or 'trace_mut/<name>'."""
    base = os.path.join(DATA, kind)
    fin_p, meta_p = os.path.join(base, "final.npz"), os.path.join(base, "meta.json")
    if not (os.path.exists(fin_p) and os.path.exists(meta_p)):
        raise SystemExit(f"partmesh: missing judge trace in {base} -- run "
                         f"'bash media/collect_mutant_traces.sh' and re-grade "
                         f"the good example with --trace (see make_result.py)")
    return fin_p, meta_p


def _contour_polygon(contour, xs, ys):
    """marching-squares contour (cell centres) -> polygon on grid corners."""
    j = np.clip(np.round(contour[:, 1] - 0.5), 0, len(xs) - 1).astype(int)
    i = np.clip(np.round(contour[:, 0] - 0.5), 0, len(ys) - 1).astype(int)
    pts = np.stack([xs[j], ys[i]], 1)
    keep = np.ones(len(pts), bool)
    keep[1:] = np.any(np.abs(np.diff(pts, axis=0)) > 1e-12, axis=1)
    g = Polygon(pts[keep]).buffer(0)
    if g.is_empty or g.area <= 0:
        raise SystemExit("partmesh: empty contour after snapping to the grid")
    return g


def removed_regions(fin):
    """The removed material, as [(outer polygon, [holes]), ...], largest first.

    Connected components of the judge's removed set are labelled and each is
    contoured on its own: ``find_contours`` then returns that component's
    outer boundary plus one curve per uncut island inside it, so the largest
    ring is the outline and the rest are holes -- no guessing which of two
    nested curves is which.
    """
    from scipy import ndimage

    H = fin["H"]
    xs, ys = fin["xs"], fin["ys"]
    removed = H < -1e-9
    if not removed.any():
        return []
    labels, n = ndimage.label(removed)
    regions = []
    for lab in range(1, n + 1):
        comp = labels == lab
        rings = [_contour_polygon(c, xs, ys)
                 for c in measure.find_contours(comp.astype(np.float64), 0.5)]
        rings.sort(key=lambda g: -g.area)
        regions.append((rings[0], rings[1:]))
    stock = float(xs[-1] - xs[0] + 0.05) * float(ys[-1] - ys[0] + 0.05)
    total = sum(g.area - sum(h.area for h in hs) for g, hs in regions)
    if not regions or total >= 0.9 * stock:
        raise SystemExit(f"partmesh: removed region covers {total:.0f} mm2 of "
                         f"a {stock:.0f} mm2 block -- the mask is inverted")
    regions.sort(key=lambda t: -t[0].area)
    return regions


def stock_box(meta, read_mm):
    """The block: top face at z = 0, bottom read_mm below it (a slice of the
    25 mm stock -- everything the judge gates lives in the top 6 mm)."""
    sx, sy = float(meta["stock"]["x_mm"]), float(meta["stock"]["y_mm"])
    box = trimesh.creation.box(extents=[sx, sy, read_mm])
    box.apply_translation([sx / 2.0, sy / 2.0, -read_mm / 2.0])
    return box


def cut_solids(fin, regions, depth, eps=1e-3):
    """Prisms of the removed material, from z = -depth up past the top face."""
    prisms = []
    for outer, holes in regions:
        prism = trimesh.creation.extrude_polygon(
            Polygon(outer.exterior, [h.exterior for h in holes]),
            height=depth + eps)
        prism.apply_translation([0.0, 0.0, -(depth - eps)])
        prisms.append(prism)
    return trimesh.util.concatenate(prisms) if prisms else None


def colour_faces(mesh, depth):
    """Colour every face by what the judge says its surface is.

    Horizontal faces carry the real depth of their own surface below the
    original stock top: pale aluminium at 0 mm, the machined shade at the
    floor (-depth), and -- only a mutant can have them -- uncut terraces at
    the pass depths in between, at their own step of the same ramp.  Every
    other face (walls, block sides, the sliced bottom) is one wall shade, so
    a wall made of tall triangles does not band.
    """
    mesh.update_faces(mesh.unique_faces())
    mesh.update_faces(mesh.nondegenerate_faces())
    mesh.merge_vertices()
    mesh.fix_normals()
    up = mesh.face_normals[:, 2] > 0.99
    z = np.round(mesh.triangles_center[:, 2], 6)
    t = np.clip(-z / depth, 0.0, 1.0)           # 0 = top face, 1 = floor
    top_rgb, floor_rgb = np.asarray(TOP_RGB), np.asarray(FLOOR_RGB)
    ramp = floor_rgb * (1.0 - t[:, None]) + top_rgb * t[:, None]
    wall = floor_rgb * 0.45 + top_rgb * 0.55
    rgb = np.where(up[:, None], ramp, wall[None, :])
    mesh.visual = trimesh.visual.ColorVisuals(
        mesh=mesh, face_colors=np.round(rgb * 255).astype(np.uint8))
    return mesh


def block_solid(kind="trace_good", read_mm=14.0):
    """The machined block for one judge trace: (trimesh.Trimesh, stats)."""
    fin_p, meta_p = trace_path(kind)
    fin, meta = np.load(fin_p), json.load(open(meta_p))
    H = fin["H"]
    depth = float(-H.min())
    regions = removed_regions(fin)
    if depth <= 0:
        raise SystemExit(f"partmesh: {kind}: judge recorded no material "
                         f"removed (H never goes below 0)")
    box = stock_box(meta, read_mm)
    cutter = cut_solids(fin, regions, depth)
    if cutter is None:
        raise SystemExit(f"partmesh: {kind}: no removed regions found")
    solid = box.difference(cutter, engine="manifold")
    if not solid.is_watertight:
        raise SystemExit(f"partmesh: {kind}: boolean produced a non-watertight "
                         f"solid ({len(solid.faces)} faces)")
    solid = colour_faces(solid, depth)
    stats = {
        "trace": kind,
        "pocket_depth_mm": depth,
        "removed_area_mm2": float(sum(g.area - sum(h.area for h in hs)
                                     for g, hs in regions)),
        "removed_cells": int((H < -1e-9).sum()),
        "faces": int(len(solid.faces)),
        "volume_mm3": float(solid.volume),
    }
    return solid, stats


def main():
    out = os.path.join(DEMO, "media", "master")
    os.makedirs(out, exist_ok=True)
    kinds = ["trace_good"] + sorted(
        os.path.join("trace_mut", n)
        for n in os.listdir(os.path.join(DATA, "trace_mut"))
        if os.path.isdir(os.path.join(DATA, "trace_mut", n)))
    for kind in kinds:
        solid, stats = block_solid(kind, read_mm=READ_MM)
        name = kind.replace("/", "_")
        solid.export(os.path.join(out, f"{name}.ply"))
        print(f"partmesh: {name}: {stats['faces']:,} faces, pocket "
              f"{stats['pocket_depth_mm']:g} mm deep, "
              f"{stats['removed_cells']:,} cells removed by the judge")


if __name__ == "__main__":
    main()