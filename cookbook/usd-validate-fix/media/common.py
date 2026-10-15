#!/usr/bin/env python3
"""Shared loading, validation and drawing for the usd-validate-fix media.

Every number drawn comes from media/data/ (real judge output produced by
make_data.sh) or from the graded assets themselves; each loader validates
the whole file before anything is drawn and names the first missing field.

Palette: light-mode tokens from the agent-next dataviz reference palette.
Status colors (pass/fail) always ship with a glyph and a word, never
color alone; data marks use categorical slot 1 (blue).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

DEMO_NAME = "usd-validate-fix"
SEED = "20261015"

# --- palette (dataviz reference instance, light mode) ----------------------
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
BLUE = "#2a78d6"        # categorical slot 1: data marks
GOOD = "#0ca30c"        # status: pass
CRITICAL = "#d03b3b"    # status: fail
CARD_BG = "#f6f5f1"     # one step off the surface, for cards/rows

# SPEC.md judge constants (rules the figure draws as pass lines).
UNIT_TOL = 1e-4         # |norm|-1 tolerance
BBOX_TOL = 1e-6         # cm, geometry invariance vs the original
AREA_TOL = 1e-9         # cm^2, triangle-fan area

# Mutant -> SPEC.md defect id / description (SPEC tables, not measurements).
MUTANT_IDS = {
    "no_normals": "D1", "mpu_1": "D2a", "upaxis_z": "D2b",
    "zero_face": "D3", "unbind": "D4", "no_defaultprim": "D5",
    "no_extent": "D6", "delete_band": "cheat", "scale_points": "cheat",
    "short_normals": "cheat", "no_collision": "cheat",
    "sublayer_cheat": "cheat",
}
MUTANT_ORDER = ["no_normals", "mpu_1", "upaxis_z", "zero_face", "unbind",
                "no_defaultprim", "no_extent", "delete_band",
                "scale_points", "short_normals", "no_collision",
                "sublayer_cheat"]
GATE_ORDER = ["validator", "oracle", "geometry", "recount"]
GATE_LABEL = {"validator": "gate 1\nNVIDIA validator",
              "oracle": "gate 2\nusd-core oracle",
              "geometry": "gate 3\ngeometry kept",
              "recount": "gate 4\nclean-room text recount"}


def die(msg):
    print("%s: %s" % (os.path.basename(sys.argv[0]), msg), file=sys.stderr)
    raise SystemExit(1)


def need(obj, *keys):
    """Return obj[keys...] or die naming the missing dotted path."""
    cur = obj
    for i, key in enumerate(keys):
        if not isinstance(cur, dict) or key not in cur:
            die("data file missing field %s" % ".".join(keys[:i + 1]))
        cur = cur[key]
    return cur


def load_json(relpath, *required):
    path = os.path.join(DATA, relpath)
    if not os.path.isfile(path):
        die("missing %s -- run media/make_data.sh first" % relpath)
    try:
        with open(path, encoding="utf-8") as fh:
            obj = json.load(fh)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        die("%s is not valid JSON: %s" % (relpath, exc))
    for dotted in required:
        need(obj, *dotted.split("."))
    return obj


def load_verdict(name):
    """A grade.sh verdict JSON from media/data, fully validated."""
    v = load_json(
        "grade_%s.json" % name,
        "artifact", "seed", "passed", "failed_gate", "timing.total_s",
        "gates.validator.passed", "gates.validator.errors",
        "gates.validator.issues_by_severity",
        "gates.validator.validator_status",
        "gates.oracle.passed", "gates.oracle.errors",
        "gates.geometry.passed", "gates.geometry.errors",
        "gates.recount.passed", "gates.recount.errors",
        "facts.oracle.meshes", "facts.oracle.colliders",
        "facts.geometry", "facts.crosscheck",
    )
    for mesh in need(v, "facts", "oracle", "meshes").values():
        for key in ("points", "face_corners", "zero_area_faces",
                    "max_normal_dev"):
            need(mesh, key)
    for fact in need(v, "facts", "geometry").values():
        for key in ("points", "bbox_dev_cm"):
            need(fact, key)
    need(v, "facts", "crosscheck", "passed")
    for key in ("recount", "recount_geometry"):
        need(v, "facts", key)
    return v


def error_classes(errors, width=34):
    """Collapse a gate's error list to short 'N x label' lines (real counts)."""
    classes = {}
    for err in errors:
        key = err.split(":")[0].strip()[:width]
        classes[key] = classes.get(key, 0) + 1
    return classes


# SPEC.md's seeded defects, each with a predicate over the *real* oracle
# error strings of the broken asset.  defect_counts() below asserts that the
# predicates partition the verdict's error list, so no error is dropped and
# no count is invented.
DEFECTS = [
    ("D1", "no normals on any mesh", "NormalsExistChecker ×3 + oracle ×3",
     lambda e: "normals not authored" in e),
    ("D2a", "metersPerUnit 1.0 ≠ 0.01", "oracle (values, not presence)",
     lambda e: e.startswith("metersPerUnit")),
    ("D2b", "upAxis Z ≠ Y", "oracle",
     lambda e: e.startswith("upAxis")),
    ("D3", "degenerate face on Band", "ZeroAreaFaceChecker + oracle ×1",
     lambda e: "triangle-fan area" in e),
    ("D4", "Band has no material binding",
     "oracle: no computable bound material",
     lambda e: "bound material" in e),
    ("D5", "no defaultPrim", "DefaultPrimChecker + oracle ×1",
     lambda e: "defaultPrim" in e),
    ("D6", "no extents on any mesh", "ExtentsChecker ×3 + oracle ×3",
     lambda e: "extent not authored" in e),
]


def defect_counts(oracle_errors):
    """[(defect id, label, caught-by, error count)] counted from real errors.

    Dies if the predicates do not partition the list (every error must be
    attributed to exactly one seeded defect).
    """
    out = []
    for did, label, caught_by, pred in DEFECTS:
        hits = [e for e in oracle_errors if pred(e)]
        out.append((did, label, caught_by, len(hits)))
    total = sum(c for *_, c in out)
    if total != len(oracle_errors):
        die("oracle errors do not partition into the SPEC defects: %d of %d "
            "attributed" % (total, len(oracle_errors)))
    return out


def load_mesh(name):
    """An extract_mesh.py dump of the graded asset, fully validated."""
    m = load_json(
        "mesh_%s.json" % name,
        "asset", "metadata.metersPerUnit", "metadata.upAxis",
    )
    meshes = need(m, "meshes")
    if not meshes:
        die("mesh_%s.json has no meshes" % name)
    for mesh in meshes:
        for key in ("path", "points", "faceVertexCounts", "faceVertexIndices",
                    "bound_material"):
            need(mesh, key)
    return m


def mesh_by_path(mesh_dump):
    return {mesh["path"]: mesh for mesh in mesh_dump["meshes"]}


def faces(mesh):
    """Yield ([(x, y, z), ...], corner_normals) per face of a mesh dump."""
    pts = mesh["points"]
    fvi = mesh["faceVertexIndices"]
    normals = mesh.get("normals")
    k = 0
    for count in mesh["faceVertexCounts"]:
        idx = fvi[k:k + count]
        yield [tuple(pts[i]) for i in idx], \
            [normals[k + j] for j in range(count)] if normals else None
        k += count


def newell_normal(verts):
    """Flat face normal (unnormalized) -- display shading only."""
    nx = ny = nz = 0.0
    for j in range(len(verts)):
        cur, nxt = verts[j], verts[(j + 1) % len(verts)]
        nx += (cur[1] - nxt[1]) * (cur[2] + nxt[2])
        ny += (cur[2] - nxt[2]) * (cur[0] + nxt[0])
        nz += (cur[0] - nxt[0]) * (cur[1] + nxt[1])
    ln = (nx * nx + ny * ny + nz * nz) ** 0.5 or 1.0
    return nx / ln, ny / ln, nz / ln


def shade(color, normal, light=(0.35, -0.5, 0.8)):
    """Lambert shade of an asset material color for display."""
    dot = sum(c * n for c, n in zip(light, normal))
    k = 0.55 + 0.45 * max(0.0, dot)
    return tuple(min(1.0, c * k) for c in color)


def draw_cone(ax, mesh_dump, show_normals=False, normals_len=2.6, elev=14,
              azim=-68, unbound_color=(0.62, 0.62, 0.62)):
    """Render the asset's own meshes; optionally its authored normals.

    Face fills are the asset's bound material diffuseColor, Lambert-shaded
    with flat face normals for display; an unbound mesh falls back to gray.
    Normal arrows are the asset's authored face-varying values (first
    corner of each face), never computed ones.
    """
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    for mesh in mesh_dump["meshes"]:
        color = mesh.get("diffuseColor") or unbound_color
        polys, colors = [], []
        for verts, corner_normals in faces(mesh):
            polys.append(verts)
            colors.append(shade(color, newell_normal(verts)))
        coll = Poly3DCollection(polys, facecolors=colors,
                                edgecolors=(0.25, 0.25, 0.25, 0.35),
                                linewidths=0.4)
        ax.add_collection3d(coll)
        if show_normals and mesh.get("normals"):
            centroids, dirs = [], []
            for verts, corner_normals in faces(mesh):
                n = corner_normals[0]           # authored value
                centroids.append(tuple(
                    sum(v[a] for v in verts) / len(verts)
                    + normals_len * 0.5 * n[a] for a in range(3)))
                dirs.append(tuple(n))
            ax.quiver([c[0] for c in centroids], [c[1] for c in centroids],
                      [c[2] for c in centroids],
                      [d[0] * normals_len for d in dirs],
                      [d[1] * normals_len for d in dirs],
                      [d[2] * normals_len for d in dirs],
                      color=INK_2, linewidth=0.9, arrow_length_ratio=0.22)
    ax.set_xlim(-21, 21)
    ax.set_ylim(-21, 21)
    ax.set_zlim(0, 62)
    ax.set_box_aspect((1, 1, 62 / 42))   # true proportions: 42x42x62 cm window
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()


def badge(ax, x, y, text, status, fontsize=13):
    """A status chip: colored fill + glyph + word, never color alone."""
    fill = GOOD if status == "pass" else CRITICAL
    glyph = "✓" if status == "pass" else "✗"
    ax.text(x, y, "%s %s" % (glyph, text), transform=ax.transAxes,
            color="#ffffff", fontsize=fontsize, fontweight="bold",
            va="center", ha="left", clip_on=False,
            bbox=dict(boxstyle="round,pad=0.45", linewidth=0,
                      facecolor=fill))
