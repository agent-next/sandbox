#!/usr/bin/env python3
"""Offscreen 3D renderer for the aicad-freecad-mcp demo media.

Real renders of real meshes only: pyrender 0.1.45 on the OSMesa backend
(libosmesa6, software GL), Phong-lit steel material, smooth-shaded, with
sharp/silhouette edges drawn dark — a technical-illustration look. All
composition and text happens in PIL downstream; this module only renders
meshes to RGBA images (+ the depth buffer for edge visibility tests).

Geometry helpers (reference solids, XOR) come from the judge itself:
judge/judge.py is imported so the exact same reference solid and
manifold3d symmetric difference that graded the artifact drives the
visual comparison — nothing is re-derived here.
"""
import os
import sys

import osmesa_shim  # noqa: F401  (patches PyOpenGL OSMesa before pyrender)

import numpy as np
import trimesh
import pyrender
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))          # <demo root>
sys.path.insert(0, os.path.join(ROOT, "judge"))

STEEL = np.array([0.62, 0.66, 0.72, 1.0])     # warm steel
STEEL_DARK = np.array([0.50, 0.54, 0.60, 1.0])
RED = np.array([0.85, 0.18, 0.16, 1.0])
EDGE_RGBA = (18, 22, 28, 235)
EDGE_WIDTH_SCALE = 1 / 340.0                    # px per output px


def _metal_material(rgba):
    return pyrender.MetallicRoughnessMaterial(
        baseColorFactor=rgba, metallicFactor=0.25, roughnessFactor=0.6)


def _norm_mesh(mesh, target=2.0):
    """Recenter on bbox centre, scale so the largest extent is `target`."""
    m = mesh.copy()
    m.apply_translation(-m.bounding_box.centroid)
    ext = float(m.extents.max())
    if ext > 0:
        m.apply_scale(target / ext)
    return m


def feature_segments(mesh, dihedral_deg=25.0):
    """Sharp + boundary edges of a mesh as an (N, 2, 3) float array."""
    m = mesh.copy()
    m.merge_vertices()
    adj = m.face_adjacency
    edges = m.face_adjacency_edges
    ang = m.face_adjacency_angles
    sharp = edges[ang > np.radians(dihedral_deg)]
    # boundary = edges used by exactly one face
    try:
        groups = trimesh.grouping.group_rows(
            m.edges_sorted, require_count=1)
        boundary = m.edges_sorted[groups]
    except Exception:
        boundary = np.zeros((0, 2), dtype=np.int64)
    idx = np.vstack([np.asarray(sharp, dtype=np.int64).reshape(-1, 2),
                     np.asarray(boundary, dtype=np.int64).reshape(-1, 2)])
    idx = np.unique(np.sort(idx, axis=1), axis=0)
    return m.vertices[idx]


def _cam_pose(yaw_deg, pitch_deg, dist):
    """Camera pose orbiting +Z, looking at the origin (pyrender frame)."""
    yaw, pitch = np.radians(yaw_deg), np.radians(pitch_deg)
    eye = np.array([np.cos(pitch) * np.cos(yaw),
                    np.cos(pitch) * np.sin(yaw),
                    np.sin(pitch)]) * dist
    z = eye / np.linalg.norm(eye)                     # camera -Z -> eye dir
    up = np.array([0.0, 0.0, 1.0])
    x = np.cross(up, z); x /= np.linalg.norm(x)
    y = np.cross(z, x)
    pose = np.eye(4)
    pose[:3, 0], pose[:3, 1], pose[:3, 2] = x, y, z
    pose[:3, 3] = eye
    return pose, eye


class Renderer:
    """One OSMesa context, reused for many renders at a fixed size."""

    def __init__(self, width, height):
        self.w, self.h = width, height
        self.r = pyrender.OffscreenRenderer(width, height)

    def render(self, mesh, yaw=35.0, pitch=22.0, dist=None,
               rgba=STEEL, face_colors=None, edges=True, fov_deg=28.0,
               smooth=False, margin=1.25):
        """Render `mesh` (trimesh, already posed/scaled) -> PIL RGBA image.

        dist: camera distance; None = auto from mesh extents + fov, scaled
              by `margin` (1.25 fills the frame; larger leaves headroom).
        smooth: False draws crisp faceted normals (correct for planar
              faces; CAD tessellations are coarse, so vertex-averaged
              normals smear flat faces into starbursts), True averages.
        face_colors: optional (F,4) uint8 overrides baked onto a copy.

        `mesh.visual.face_colors` is honoured — trimesh's own face_colors
        property does not reach pyrender for a process=False mesh.
        """
        m = mesh.copy()
        if face_colors is None and getattr(m.visual, "kind", None) == "face":
            face_colors = m.visual.face_colors
        if face_colors is not None:
            m.visual.face_colors = face_colors
            pm = pyrender.Mesh.from_trimesh(m, smooth=smooth)
        else:
            pm = pyrender.Mesh.from_trimesh(m, smooth=smooth,
                                            material=_metal_material(rgba))
        scene = pyrender.Scene(
            ambient_light=np.array([0.30, 0.30, 0.33, 1.0]),
            bg_color=np.array([0.0, 0.0, 0.0, 0.0]))
        scene.add(pm)
        if dist is None:
            ext = float(m.extents.max())
            dist = margin * (ext / 2.0) / np.tan(np.radians(fov_deg) / 2)
        pose, eye = _cam_pose(yaw, pitch, dist)
        cam = pyrender.PerspectiveCamera(yfov=np.radians(fov_deg),
                                       znear=dist * 0.02, zfar=dist * 20)
        scene.add(cam, pose=pose)

        key = pyrender.DirectionalLight(color=np.ones(3), intensity=3.2)
        scene.add(key, pose=_cam_pose(yaw + 35, 55, 1.0)[0])
        fill = pyrender.DirectionalLight(color=np.array([0.75, 0.82, 0.95]),
                                         intensity=1.1)
        scene.add(fill, pose=_cam_pose(yaw - 115, 15, 1.0)[0])
        rim = pyrender.DirectionalLight(color=np.array([1.0, 0.92, 0.80]),
                                        intensity=1.6)
        scene.add(rim, pose=_cam_pose(yaw + 165, 35, 1.0)[0])

        color, depth = self.r.render(scene)
        # OSMesa reads back RGB only; alpha comes from the depth buffer
        # (0 = background pixel), feathered 1 px for anti-aliased edges.
        img = Image.fromarray(color, "RGB").convert("RGBA")
        mask = Image.fromarray(
            np.where(depth > 0, 255, 0).astype(np.uint8), "L")
        mask = mask.filter(ImageFilter.GaussianBlur(0.8))
        img.putalpha(mask)

        if edges:
            segs = feature_segments(m)
            if len(segs):
                self._draw_edges(img, segs, depth, cam, pose, eye, dist)
        return img

    def _draw_edges(self, img, segs, depth, cam, cam_pose, eye, dist):
        """Project mesh edges; draw only portions not occluded by the mesh."""
        w, h = self.w, self.h
        view = np.linalg.inv(cam_pose)
        pts = segs.reshape(-1, 3)
        p4 = np.hstack([pts, np.ones((len(pts), 1))]) @ view.T
        z = -p4[:, 2]
        ok = z > cam.znear
        P = cam.get_projection_matrix(w, h)
        f = P[1, 1]
        fx = P[0, 0]
        # screen coords (y down): x' = cx + fx*X/-Z, y' = cy - fy*Y/-Z
        sx = (w / 2.0) + fx * (p4[:, 0] / z) * (w / 2.0)
        sy = (h / 2.0) - f * (p4[:, 1] / z) * (h / 2.0)
        dmap = depth  # linearized camera -Z per pixel (0 = background)
        draw = ImageDraw.Draw(img, "RGBA")
        lw = max(1, int(round(w * EDGE_WIDTH_SCALE)))
        tol = 0.035
        n = len(segs)
        sub = 5
        for i in range(n):
            j = 2 * i
            x0, y0, z0 = sx[j], sy[j], z[j]
            x1, y1, z1 = sx[j + 1], sy[j + 1], z[j + 1]
            if not (ok[j] and ok[j + 1]):
                continue
            span = np.linspace(0.0, 1.0, sub)
            X = x0 + (x1 - x0) * span
            Y = y0 + (y1 - y0) * span
            Z = z0 + (z1 - z0) * span   # camera-space -Z (plane depth)
            vis = np.zeros(sub, bool)
            for k in range(sub):
                px, py = int(X[k]), int(Y[k])
                if px < 0 or py < 0 or px >= w or py >= h:
                    continue
                dd = dmap[py, px]
                if dd <= 0:
                    continue
                # rendered depth is camera -Z; edge point visible if its -Z
                # is not behind the surface stored at that pixel
                if Z[k] <= dd * (1.0 + tol) + 0.002 * dist:
                    vis[k] = True
            for k in range(sub - 1):
                if vis[k] and vis[k + 1]:
                    draw.line([(X[k], Y[k]), (X[k + 1], Y[k + 1])],
                              fill=EDGE_RGBA, width=lw)

    def delete(self):
        self.r.delete()


# --------------------------------------------------------------------------
# Judge-derived geometry: reference solids and XOR difference meshes use
# judge.py itself (the exact code that graded the artifact).
# --------------------------------------------------------------------------

def reference_mesh(part, deflection=0.02):
    import judge
    return judge.tessellate(judge.reference_solid(part), deflection)


def xor_mesh(part, stl_path, deflection=0.02):
    """manifold3d symmetric-difference mesh (a-b | b-a), same as the gate."""
    import judge
    import manifold3d
    ref = reference_mesh(part, deflection)
    got = trimesh.load(stl_path, force="mesh")
    a, b = judge.to_manifold(got), judge.to_manifold(ref)
    diff = (a - b) + (b - a)
    m = diff.to_mesh()
    return trimesh.Trimesh(vertices=np.asarray(m.vert_properties),
                           faces=np.asarray(m.tri_verts), process=False)


def deviation_colors(stl_path, ref_mesh, vmax_mm=0.35):
    """Per-face RGBA colors on the delivered mesh: distance to reference.

    Green where it sits on the reference (|d| ~ 0) through yellow to red at
    vmax_mm. Computed as unsigned centroid distance — the same geometric
    difference the xor_reference gate measures volumetrically.
    """
    mesh = trimesh.load(stl_path, force="mesh")
    centers = mesh.triangles.mean(axis=1)
    _, dist, _ = trimesh.proximity.closest_point(ref_mesh, centers)
    t = np.clip(np.abs(dist) / vmax_mm, 0.0, 1.0)
    r = (t ** 0.6 * 255).astype(np.uint8)
    g = ((1.0 - t ** 0.7) * 200 + 30).astype(np.uint8)
    b = np.full(len(t), 40, np.uint8)
    a = np.full(len(t), 255, np.uint8)
    return mesh, np.stack([r, g, b, a], axis=1), np.abs(dist)


# --------------------------------------------------------------------------

def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("stl")
    ap.add_argument("out")
    ap.add_argument("--yaw", type=float, default=35.0)
    ap.add_argument("--pitch", type=float, default=22.0)
    ap.add_argument("--size", default="900x900")
    ap.add_argument("--fov", type=float, default=28.0)
    ap.add_argument("--norm", type=float, default=2.0)
    ap.add_argument("--no-edges", action="store_true")
    args = ap.parse_args()
    w, h = (int(v) for v in args.size.split("x"))
    mesh = _norm_mesh(trimesh.load(args.stl, force="mesh"), args.norm)
    r = Renderer(w, h)
    try:
        img = r.render(mesh, yaw=args.yaw, pitch=args.pitch,
                       edges=not args.no_edges, fov_deg=args.fov)
    finally:
        r.delete()
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    img.save(args.out)
    print("wrote", args.out)


if __name__ == "__main__":
    main()
