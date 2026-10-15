#!/usr/bin/env python3
"""Shared helpers for the aicad-text-to-cad media.

Every number and every mesh drawn by the figures and the video comes
from a file the judge or the pinned tool wrote during a real run:

  * an artifact's delivered model.stl / model.step,
  * a verdict JSON written by judge/grade.sh --seed 42 --json,
  * a reference solid rebuilt from judge/spec.json by the judge's own
    code (check_gates.build_reference + tessellate, imported read-only),
  * a boolean XOR computed with the judge's own gate-7 method
    (manifold3d ^ on kernel tessellations).

Nothing here synthesises data.  Runs under the judge venv
(~/.venvs/aicad-judge: matplotlib 3.11.2, trimesh 4.12.2, manifold3d
3.5.2, OCP 7.9 — all sha256-pinned in judge/requirements.txt).
"""
import json
import os
import sys
import textwrap

import matplotlib.colors
import numpy as np
import trimesh

MEDIA = os.path.dirname(os.path.abspath(__file__))
DEMO = os.path.dirname(MEDIA)
JUDGE = os.path.join(DEMO, "judge")
DATA = os.path.join(MEDIA, "data")
VERDICTS = os.path.join(DATA, "verdicts")

# Okabe-Ito colourblind-safe pair, validated with the dataviz palette
# checker (adjacent CVD dE 11.0, normal-vision dE 25.8, both >= 3:1 on
# white): every pass/fail mark ALSO carries a text label, so colour
# never carries the verdict alone.
PASS = "#009E73"      # bluish green  -- gate passed
FAIL = "#D55E00"      # vermillion    -- gate failed / defect highlight
FAIL_RGB = matplotlib.colors.to_rgb(FAIL)   # for mesh facecolors
BLUE = "#0072B2"      # blue          -- reference geometry (a series, not a status)
INK = "#1b1b1b"
MUTED = "#52514e"
MESH_BASE = (0.72, 0.75, 0.79)


def need(path, what="collect_verdicts.sh"):
    """Fail loudly if a real judge output file is missing."""
    if not os.path.exists(path):
        raise SystemExit(f"missing {path} -- run media/{what} first")
    return path


def load_verdict(name):
    """Verdict JSON dict written by judge/grade.sh --json (name incl. .json)."""
    with open(need(os.path.join(VERDICTS, name))) as fh:
        return json.load(fh)


def judge_module():
    """Import the judge's check_gates (read-only) for reference builds."""
    if JUDGE not in sys.path:
        sys.path.insert(0, JUDGE)
    import check_gates  # noqa: F401  (nothing under judge/ is written)
    return check_gates


def load_stl(path, process=True):
    return trimesh.load_mesh(need(path), process=process)


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------
def shaded_facecolors(mesh, base=MESH_BASE, light=(0.45, 0.25, 0.86)):
    """Lambert-shaded face colours from the mesh's own facet normals."""
    n = np.asarray(mesh.face_normals, dtype=float)
    L = np.array(light, dtype=float)
    L /= np.linalg.norm(L)
    lam = np.clip(n @ L, 0.0, 1.0)          # back facets go dark: depth cue
    inten = 0.40 + 0.60 * lam
    cols = np.clip(np.outer(inten, np.array(base)), 0.0, 1.0)
    return np.column_stack([cols, np.ones(len(cols))])


def draw_mesh(ax, mesh, fc, elev=24, azim=-58, title=None, title_fs=10.5,
              pad=0.05, label=None, label_fs=8.5):
    """Add a shaded Poly3DCollection render of `mesh` to `ax` (axis off)."""
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    tris = np.asarray(mesh.vertices)[np.asarray(mesh.faces)]
    ax.add_collection3d(Poly3DCollection(
        tris, facecolors=fc, edgecolors="none"))
    lo, hi = np.asarray(mesh.bounds)
    span = hi - lo
    m = span.max() * pad
    ax.set_xlim(lo[0] - m, hi[0] + m)
    ax.set_ylim(lo[1] - m, hi[1] + m)
    ax.set_zlim(lo[2] - m, hi[2] + m)
    ax.set_box_aspect(span)
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()
    if title:
        ax.set_title(title, fontsize=title_fs, pad=1, color=INK)
    if label:
        ax.text2D(0.5, 0.015, label, transform=ax.transAxes, ha="center",
                  va="bottom", fontsize=label_fs, color=INK)


# ---------------------------------------------------------------------------
# geometry via the judge's own code path
# ---------------------------------------------------------------------------
def import_ocp():
    return judge_module().import_ocp()


def reference_mesh(part):
    """(trimesh, brep_volume_mm3) of the spec-built reference solid."""
    cg = judge_module()
    spec = json.loads(open(need(os.path.join(JUDGE, "spec.json"))).read())
    o = cg.import_ocp()
    ref = cg.build_reference(part, spec["parts"][part], o)
    vol = cg.shape_volume(ref, o)
    verts, tris = cg.tessellate(ref, o)
    mesh = trimesh.Trimesh(np.asarray(verts, dtype=float),
                           np.asarray(tris, dtype=np.int64), process=False)
    return mesh, vol


def step_mesh(step_path):
    """(trimesh, brep_volume_mm3) of a delivered STEP, judge's own import."""
    cg = judge_module()
    o = cg.import_ocp()
    reader = o["STEPControl_Reader"]()
    if reader.ReadFile(str(need(step_path))) != \
            o["IFSelect_ReturnStatus"].IFSelect_RetDone:
        raise SystemExit(f"STEP import failed: {step_path}")
    reader.TransferRoots()
    shape = reader.OneShape()
    vol = cg.shape_volume(shape, o)
    verts, tris = cg.tessellate(shape, o)
    mesh = trimesh.Trimesh(np.asarray(verts, dtype=float),
                           np.asarray(tris, dtype=np.int64), process=False)
    return mesh, vol


def xor_solid(a, b):
    """manifold3d XOR of two closed meshes -> (trimesh, volume_mm3).

    The same boolean the judge's gate 7 runs on the kernel tessellations.
    """
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
    return np.asarray(solid.contains(mesh.triangles_center), dtype=bool)


# ---------------------------------------------------------------------------
# STL byte-edit defects (drop_triangle / flip_facet mutants)
# ---------------------------------------------------------------------------
def _key(tri, nd=5):
    return tuple(sorted(map(tuple, np.round(np.asarray(tri, float), nd))))


def stl_byte_defect(mutant_stl, good_stl):
    """Locate the single STL facet edit between a mutant and its good part.

    Returns (kind, face_indices, note): kind 'dropped' or 'flipped';
    `face_indices` index into the mutant mesh (merged vertices) and are
    the faces to highlight; `note` states the edit.
    """
    mut = load_stl(mutant_stl)                # merge vertices: adjacency ok
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
    if dropped:
        pts = np.array(dropped[0])
        v = np.asarray(mut.vertices)
        near = {int(np.argmin(np.linalg.norm(v - p, axis=1))) for p in pts}
        faces = [i for i, f in enumerate(np.asarray(mut.faces))
                 if sum(int(x in near) for x in f) >= 2]
        return ("dropped", faces,
                f"1 of {len(good_map)} facets deleted from the delivered STL"
                f" -- the hole rim it leaves ({len(faces)} adjacent facets) "
                "is highlighted")
    flipped = [k for k in good_map if k in tri_keys
               and any(tuple(map(tuple, t)) !=
                       tuple(map(tuple, np.asarray(mut.vertices)[
                           mut.faces[tri_keys[k][0]]]))
                       for t in good_map[k])]
    if flipped:
        k = flipped[0]
        return ("flipped", tri_keys[k],
                "1 facet's vertex order swapped in the delivered STL"
                " (winding flipped) -- that facet is highlighted")
    raise SystemExit(f"no STL byte difference found {mutant_stl} vs {good_stl}")


# ---------------------------------------------------------------------------
# defect highlight: the red facets on a mutant, from real files only
# ---------------------------------------------------------------------------
MUTANT_PART = {           # which good part each single-edit mutant comes from
    "plate-hole-count": "adapter_plate",
    "plate-hole-diameter": "adapter_plate",
    "plate-hole-drift": "adapter_plate",
    "plate-flipped-facet": "adapter_plate",
    "bracket-missing-fillet": "bracket",
    "bracket-fillet-radius": "bracket",
    "bushing-scale-25_4": "bushing",
    "bushing-non-watertight": "bushing",
}
STL_BYTE_MUTANTS = {"bushing-non-watertight", "plate-flipped-facet"}


def defect_highlight(mutant_name):
    """(part, faces_to_paint_red, note) for a mutant's DELIVERED mesh.

    Geometry mutants (a one-line model.py edit, rebuilt by the tool): the
    red facets are the delivered-mesh faces inside the boolean XOR of the
    mutant vs the spec-built reference -- the same difference gate 7
    measures.  STL byte mutants: the located facet edit itself.
    """
    part = MUTANT_PART[mutant_name]
    mdir = os.path.join(DATA, "mutants", mutant_name)
    gdir = os.path.join(DEMO, "examples", "good", part)

    if mutant_name in STL_BYTE_MUTANTS:
        kind, faces, note = stl_byte_defect(os.path.join(mdir, "model.stl"),
                                             os.path.join(gdir, "model.stl"))
        return part, faces, note

    delivered = step_mesh(os.path.join(mdir, "model.step"))[0]
    ref = reference_mesh(part)[0]
    diff, xor_vol = xor_solid(delivered, ref)
    hi = faces_in_solid(delivered, diff)
    if not hi.any():
        raise SystemExit(f"{mutant_name}: XOR vs reference is empty -- "
                         "nothing to highlight (unexpected for a mutant)")
    rel = xor_vol / ref_vol
    return part, list(np.flatnonzero(hi)), (
        f"boolean XOR vs the spec reference = {xor_vol:.1f} mm3 "
        f"({rel * 100:.2f} % of it) -- red facets lie inside that "
        "difference solid")


# ---------------------------------------------------------------------------
# layout police: no overlapping text, nothing clipped (script-enforced)
# ---------------------------------------------------------------------------
def _visible_texts(fig):
    out = []
    for ax in fig.axes:
        if not ax.get_visible():
            continue
        for t in list(ax.texts) + [ax.title] + \
                list(ax.get_xticklabels()) + list(ax.get_yticklabels()) + \
                list(ax.get_xgridlines())[:0] + list(ax.texts)[:0]:
            if t is not None and t.get_visible() and t.get_text().strip():
                out.append(t)
    for t in fig.texts:
        if t.get_visible() and t.get_text().strip():
            out.append(t)
    return out


def check_no_overlap(fig, name, pad=1.5):
    """Fail (SystemExit) if any two visible texts overlap or leave the
    canvas.  `pad` px of tolerance so hairline kisses do not fail."""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    items = []
    for t in _visible_texts(fig):
        try:
            bb = t.get_window_extent(renderer=r)
        except Exception:
            continue
        if bb.width <= 0 or bb.height <= 0:
            continue
        items.append((t, bb))
    bad = []
    for i in range(len(items)):
        ti, bi = items[i]
        for j in range(i + 1, len(items)):
            tj, bj = items[j]
            if bi.x0 - pad < bj.x1 and bj.x0 - pad < bi.x1 and \
               bi.y0 - pad < bj.y1 and bj.y0 - pad < bi.y1:
                bad.append((ti.get_text()[:28], tj.get_text()[:28]))
    W, H = fig.canvas.get_width_height()
    for t, bb in items:
        if bb.x0 < -pad or bb.y0 < -pad or bb.x1 > W + pad or bb.y1 > H + pad:
            bad.append((t.get_text()[:28], "<clipped at canvas edge>"))
    if bad:
        raise SystemExit(f"[layout] {name}: OVERLAP/CLIP CHECK FAILED "
                         f"({len(bad)} pairs) e.g. {bad[:6]}")
    print(f"[layout] {name}: {len(items)} text artists checked -- "
          "no overlaps, nothing clipped")


def wrap(text, width):
    return "\n".join(textwrap.wrap(text, width=width))
