"""Real offscreen 3D renders of the real meshes (pyrender + OSMesa).

Owner rule (2026-10-15): every image of the part in result.png and every
frame of demo.mp4 that shows the part is a real 3D render of the real
mesh — never a matplotlib/painter drawing.  Here that is pyrender 0.1.45
on PyOpenGL 3.1.10 driving Mesa's software OpenGL (OSMesa, apt
libosmesa6 22.3.6); pip pins + sha256 in media/requirements-media.txt.

Rendering style (what the reviewer checks):
  * lit scene (one directional key light + ambient fill)
  * flat shading, so each planar face of the solid is one even tone
  * feature edges (dihedral angle > FEATURE_EDGE_DEG) drawn as thin
    dark tubes, so the part's real outline is legible
  * optional per-face highlight set (defect facets painted red)
"""
import math
import os

os.environ.setdefault("PYOPENGL_PLATFORM", "osmesa")

import numpy as np  # noqa: E402
import trimesh  # noqa: E402
import pyrender  # noqa: E402
from PIL import Image  # noqa: E402

FEATURE_EDGE_DEG = 25.0

# one renderer/context for the whole process (OSMesa context setup is slow)
_RENDERER = None


def _renderer(w, h):
    global _RENDERER
    if _RENDERER is None or _RENDERER.viewport_width != w \
            or _RENDERER.viewport_height != h:
        _RENDERER = pyrender.OffscreenRenderer(w, h)
    return _RENDERER


def rot(yaw_deg, tilt_deg):
    """View rotation: yaw about +Z, then tilt about +X (same convention as
    the old painter renderer)."""
    y, t = math.radians(yaw_deg), math.radians(tilt_deg)
    rz = np.array([[math.cos(y), -math.sin(y), 0.0],
                   [math.sin(y), math.cos(y), 0.0], [0.0, 0.0, 1.0]])
    rx = np.array([[1.0, 0.0, 0.0],
                   [0.0, math.cos(t), -math.sin(t)],
                   [0.0, math.sin(t), math.cos(t)]])
    return rx @ rz


def view_pose(yaw_deg, tilt_deg):
    """Rigid transform part -> camera space.  Camera looks down -Z."""
    R = rot(yaw_deg, tilt_deg)
    M = np.eye(4)
    M[:3, :3] = R
    return M, R


def feature_edges(mesh, angle_deg=FEATURE_EDGE_DEG):
    """Vertex-pair list of sharp edges (dihedral angle above threshold)."""
    adj = mesh.face_adjacency
    if len(adj) == 0:
        return []
    ang = np.degrees(mesh.face_adjacency_angles)
    sharp = adj[ang > angle_deg]
    # face_adjacency_edges is (n, 2, 2): the shared edge expressed once per
    # adjacent face (winding may differ); column 0 is enough
    pairs = mesh.face_adjacency_edges[sharp][:, 0, :]
    pairs = np.sort(pairs, axis=1)
    return np.unique(pairs, axis=0)


def edge_tubes(mesh, radius, angle_deg=FEATURE_EDGE_DEG):
    """Feature edges as one merged thin-cylinder mesh (drawn near-black)."""
    pairs = feature_edges(mesh, angle_deg)
    segs = mesh.vertices[pairs]
    tubes = []
    for a, b in segs:
        d = b - a
        h = np.linalg.norm(d)
        if h < 1e-9:
            continue
        cyl = trimesh.creation.cylinder(radius=radius, height=h,
                                        sections=6)
        z = np.array([0.0, 0.0, 1.0])
        v = d / h
        axis = np.cross(z, v)
        na = np.linalg.norm(axis)
        if na > 1e-9:
            axis = axis / na   # trimesh does not normalise -> scale skew
            angle = math.acos(np.clip(z @ v, -1.0, 1.0))
            cyl.apply_transform(
                trimesh.transformations.rotation_matrix(angle, axis))
        elif z @ v < 0:
            cyl.apply_transform(
                trimesh.transformations.rotation_matrix(math.pi,
                                                        [1.0, 0, 0]))
        cyl.apply_translation((a + b) / 2.0)
        tubes.append(cyl)
    if not tubes:
        return None
    return trimesh.util.concatenate(tubes)


def _mat(rgb):
    return pyrender.MetallicRoughnessMaterial(
        baseColorFactor=[*rgb, 1.0], metallicFactor=0.0,
        roughnessFactor=0.75)


def _to_rgb(c):
    c = np.asarray(c, dtype=float)
    if c.max() > 1.0:
        c = c / 255.0
    return c


def render_mesh(mesh, size, yaw, tilt, *, base=(42, 120, 214),
              highlight=None, edge_rgb=(35, 34, 32), edge_radius=None,
              bg=(252, 252, 251), zoom=1.0, extra=None, xmag=None):
    """Render a trimesh in a lit, flat-shaded scene.  Returns a PIL image.

    mesh       trimesh.Trimesh (part coordinates, mm)
    size       (w, h) px
    yaw, tilt  view angles in degrees (turntable spins yaw)
    highlight  iterable of face indices painted red (defect facets)
    edge_radius  tube radius for feature edges; default = extent/400
    zoom       > 1 pushes in; < 1 pulls out
    xmag       explicit half-width of the ortho view in mm (keeps two
               renders at the same world scale for side-by-side tiles)
    extra      list of (trimesh, rgb) drawn with the same pose (e.g. a
               drift arrow or the defect facet in red)
    """
    pose, _ = view_pose(yaw, tilt)
    # frame the part: rotate once, measure the camera-space extent
    v = mesh.vertices @ pose[:3, :3].T
    lo, hi = v.min(axis=0), v.max(axis=0)
    centre = (lo + hi) / 2.0
    extent = float(max(hi[0] - lo[0], hi[1] - lo[1]))

    # re-centre so the part's bounding centre sits on the optical axis
    M = pose.copy()
    M[:3, 3] = -centre

    scene = pyrender.Scene(bg_color=[*(_to_rgb(bg)), 255],
                           ambient_light=np.array([0.38, 0.38, 0.38]))

    if highlight:
        hset = np.asarray(sorted(set(int(f) for f in highlight)))
        mask = np.zeros(len(mesh.faces), dtype=bool)
        mask[hset] = True
        body = trimesh.Trimesh(mesh.vertices, mesh.faces[~mask],
                               process=False)
        hot = trimesh.Trimesh(mesh.vertices, mesh.faces[mask],
                              process=False)
        if len(body.faces):
            scene.add(pyrender.Mesh.from_trimesh(
                body, material=_mat(_to_rgb(base)), smooth=False), pose=M)
        if len(hot.faces):
            m = _mat(_to_rgb((208, 59, 59)))
            m.emissiveFactor = [0.35, 0.05, 0.05]
            scene.add(pyrender.Mesh.from_trimesh(hot, material=m,
                                                 smooth=False), pose=M)
    else:
        scene.add(pyrender.Mesh.from_trimesh(
            mesh, material=_mat(_to_rgb(base)), smooth=False), pose=M)

    if extra:
        for emesh, rgb in extra:
            scene.add(pyrender.Mesh.from_trimesh(
                emesh, material=_mat(_to_rgb(rgb)), smooth=False), pose=M)

    if edge_radius is None:
        edge_radius = extent / 700.0
    tubes = edge_tubes(mesh, edge_radius)
    if tubes is not None:
        scene.add(pyrender.Mesh.from_trimesh(
            tubes, material=_mat(_to_rgb(edge_rgb)), smooth=True), pose=M)

    xm = (xmag or extent / 2.0 * 1.10) / zoom
    cam = pyrender.OrthographicCamera(xmag=xm,
                                      ymag=xm * size[1] / size[0],
                                      znear=0.001 * extent,
                                      zfar=20.0 * extent + 10.0)
    scene.add(cam, pose=np.array([[1, 0, 0, 0], [0, 1, 0, 0],
                                  [0, 0, 1, 4 * extent + 1],
                                  [0, 0, 0, 1]]))
    key = pyrender.DirectionalLight(color=np.ones(3), intensity=2.6)
    scene.add(key, pose=np.array([[1, 0, 0, 0], [0, 0.8, -0.6, 0],
                                  [0, 0.6, 0.8, 0], [0, 0, 0, 1]]))
    fill = pyrender.DirectionalLight(color=np.ones(3), intensity=1.1)
    scene.add(fill, pose=np.array([[1, 0, 0, 0], [0, -0.5, -0.87, 0],
                                   [0, -0.87, 0.5, 0], [0, 0, 0, 1]]))

    color, _ = _renderer(*size).render(
        scene, flags=pyrender.RenderFlags.FLAT)
    return Image.fromarray(color)


def extent_at(mesh, yaw, tilt):
    """Camera-space extent (mm) for matching scale across two renders."""
    R = rot(yaw, tilt)
    v = mesh.vertices @ R.T
    lo, hi = v.min(axis=0), v.max(axis=0)
    return (hi - lo)[:2]
