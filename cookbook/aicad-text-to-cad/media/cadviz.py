#!/usr/bin/env python3
"""Shared mesh-rendering helpers for the aicad-text-to-cad media.

Everything drawn comes from a real file: the delivered model.stl of an
artifact, or the reference solid rebuilt from judge/spec.json by the
judge's own code (check_gates.build_reference + tessellate -- imported,
never modified).  Runs under the judge venv (matplotlib 3.11.2, trimesh
4.12.2, manifold3d 3.5.2, OCP -- all sha256-pinned in
judge/requirements.txt).
"""
import os
import sys

import numpy as np
import trimesh

MEDIA = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(MEDIA)
JUDGE = os.path.join(DEMO, "judge")

# colour-blind-safe greys + Okabe-Ito red for defect highlights
BASE = (0.70, 0.73, 0.77)
RED = (0.87, 0.28, 0.13)      # defect / XOR-difference highlight
BLUE = (0.13, 0.44, 0.71)     # reference geometry


def judge_module():
    """Import the judge's check_gates (read-only) for reference builds."""
    if JUDGE not in sys.path:
        sys.path.insert(0, JUDGE)
    import check_gates  # noqa: F401  (nothing in judge/ is written)
    return check_gates


def load_stl(path, process=True):
    if not os.path.exists(path):
        raise SystemExit(f"missing {path} -- run collect_verdicts.sh first")
    return trimesh.load_mesh(path, process=process)


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------
def shaded_facecolors(mesh, base=BASE, light=(0.45, 0.25, 0.86)):
    """Lambert-shaded face colours from the mesh's own facet normals."""
    n = np.asarray(mesh.face_normals, dtype=float)
    L = np.array(light, dtype=float)
    L /= np.linalg.norm(L)
    lam = np.clip(n @ L, 0.0, 1.0)          # back facets go dark: depth cue
    inten = 0.42 + 0.58 * lam
    cols = np.clip(np.outer(inten, np.array(base)), 0.0, 1.0)
    return np.column_stack([cols, np.ones(len(cols))])


def draw_mesh(ax, mesh, fc=None, edge=None, lw=0.0, elev=22, azim=-60,
              title=None, title_fs=10.5, pad=0.06, zoom=None):
    """Add a shaded Poly3DCollection render of `mesh` to `ax`."""
    import matplotlib.pyplot as plt  # noqa: F401
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    if fc is None:
        fc = shaded_facecolors(mesh)
    tris = np.asarray(mesh.vertices)[np.asarray(mesh.faces)]
    pc = Poly3DCollection(tris, facecolors=fc, edgecolors=edge or "none",
                          lw=lw)
    ax.add_collection3d(pc)
    lo, hi = np.asarray(mesh.bounds)
    span = hi - lo
    if zoom:                                   # (i, j): index of axes to zoom
        c = (lo + hi) / 2
        s = span[zoom[0]] if span[zoom[0]] > 0 else 1.0
        s = max(s, span[zoom[1]] if span[zoom[1]] > 0 else 0)
        half = s * (0.5 + pad) * 1.05
        lo, hi = c - half, c + half
        span = hi - lo
    m = span.max() * pad
    lo, hi = lo - m, hi + m
    ax.set_xlim(lo[0], hi[0])
    ax.set_ylim(lo[1], hi[1])
    ax.set_zlim(lo[2], hi[2])
    ax.set_box_aspect(span)
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    if title:
        ax.set_title(title, fontsize=title_fs, pad=2)


# ---------------------------------------------------------------------------
# geometry from the judge's own code path
# ---------------------------------------------------------------------------
def reference_mesh(part):
    """(trimesh, volume_mm3) of the spec-built reference via check_gates."""
    import json

    cg = judge_module()
    spec = json.loads(open(os.path.join(JUDGE, "spec.json")).read())
    o = cg.import_ocp()
    ref = cg.build_reference(part, spec["parts"][part], o)
    vol = cg.shape_volume(ref, o)
    verts, tris = cg.tessellate(ref, o)
    mesh = trimesh.Trimesh(np.asarray(verts, dtype=float),
                           np.asarray(tris, dtype=np.int64), process=False)
    return mesh, vol


def step_mesh(step_path):
    """(trimesh, brep_volume) of a delivered/imported STEP, judge path."""
    cg = judge_module()
    o = cg.import_ocp()
    reader = o["STEPControl_Reader"]()
    if reader.ReadFile(str(step_path)) != o["IFSelect_ReturnStatus"].IFSelect_RetDone:
        raise SystemExit(f"STEP import failed: {step_path}")
    reader.TransferRoots()
    shape = reader.OneShape()
    vol = cg.shape_volume(shape, o)
    verts, tris = cg.tessellate(shape, o)
    mesh = trimesh.Trimesh(np.asarray(verts, dtype=float),
                           np.asarray(tris, dtype=np.int64), process=False)
    return mesh, vol


def xor_solid(a, b):
    """manifold3d XOR of two closed meshes -> (trimesh of the difference,
    its volume).  Same boolean the judge's gate 7 uses (manifold3d ^)."""
    import manifold3d as m3

    def M(m):
        return m3.Manifold(
            m3.Mesh(np.asarray(m.vertices, dtype=np.float32),
                    np.asarray(m.faces, dtype=np.uint32)))

    x = M(a) ^ M(b)
    vm = x.to_mesh()
    verts = np.asarray(vm.vert_properties, dtype=float)[:, :3]
    tris = np.asarray(vm.tri_verts, dtype=np.int64)
    diff = trimesh.Trimesh(verts, tris, process=False)
    return diff, float(x.volume())


def faces_in_solid(mesh, solid):
    """Boolean per face of `mesh`: centroid inside the `solid` trimesh."""
    if len(solid.faces) == 0:
        return np.zeros(len(mesh.faces), dtype=bool)
    centroids = mesh.triangles_center
    return np.asarray(solid.contains(centroids), dtype=bool)


# ---------------------------------------------------------------------------
# STL byte-edit defects (drop_triangle / flip_facet mutants)
# ---------------------------------------------------------------------------
def _key(tri, nd=5):
    return tuple(sorted(map(tuple, np.round(np.asarray(tri, float), nd))))


def stl_byte_defect(mutant_stl, good_stl):
    """Locate the single STL facet edit between a mutant and its good part.

    Returns (kind, faces, note): kind 'dropped' or 'flipped'; `faces` are
    indices into the mutant mesh (merged vertices) to highlight; `note`
    is a short provenance string.  Raises if the two STLs match.
    """
    mut = load_stl(mutant_stl)          # merge_vertices default: adjacency ok
    good_raw = load_stl(good_stl, process=False)

    good_map = {}
    for f in np.asarray(good_raw.faces):
        tri = np.asarray(good_raw.vertices)[f]
        good_map.setdefault(_key(tri), []).append(tuple(map(tuple, tri)))
    tri_keys = {}
    for i, f in enumerate(np.asarray(mut.faces)):
        tri = np.asarray(mut.vertices)[f]
        tri_keys.setdefault(_key(tri), []).append(i)

    dropped = [k for k in good_map if k not in tri_keys]
    flipped = [k for k in good_map if k in tri_keys
               and any(tuple(map(tuple, t)) != tuple(map(tuple, np.asarray(mut.vertices)[mut.faces[tri_keys[k][0]]]))
                       for t in good_map[k])]
    if dropped:
        k = dropped[0]
        pts = np.array(k)
        # highlight the hole rim: mutant faces sharing >= 2 of the
        # removed triangle's corner coordinates
        v = np.asarray(mut.vertices)
        near = [np.argmin(np.linalg.norm(v - p, axis=1)) for p in pts]
        faces = [i for i, f in enumerate(np.asarray(mut.faces))
                 if sum(int(x in near) for x in f) >= 2]
        return ("dropped", faces,
                f"1 of {len(good_map)} facets deleted from the delivered STL "
                f"-- hole rim highlighted ({len(faces)} adjacent faces)")
    if flipped:
        k = flipped[0]
        return ("flipped", tri_keys[k],
                "1 facet's vertex order swapped (winding flipped) -- "
                "that facet highlighted")
    raise SystemExit(f"no STL byte difference found {mutant_stl} vs {good_stl}")
