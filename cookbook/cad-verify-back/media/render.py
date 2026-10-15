"""Shared rendering / parsing helpers for the cad-verify-back media files.

Every number drawn by these helpers is read from a judge output file (the
verdict JSONs written by judge/grade.sh --json during make_media.sh's data
stage, or the delivered artifact files themselves via the same pinned tools
the judge uses).  Nothing here synthesises "representative" data.

Palette: validated reference palette (dataviz skill reference instance):
categorical slots 1-2 for the delivered/spec series, status colors reserved
for pass/fail meaning, neutral grays for chrome.
"""
import json
import math
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

# --- palette (light mode, validated reference instance) --------------------
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
BLUE = "#2a78d6"      # categorical slot 1 - the delivered artifact
ORANGE = "#eb6834"    # categorical slot 2 - the spec / analytic expectation
GOOD = "#0ca30c"      # status: pass
CRIT = "#d03b3b"      # status: fail
GOOD_WASH = "#e2f2e2"
CRIT_WASH = "#f7dcdc"
SKIP_WASH = "#e1e0d9"

GATE_ORDER = [
    "step_solid", "step_valid", "step_bbox", "step_volume", "step_holes",
    "step_pcd", "angular_spacing", "step_xor",
    "stl_watertight", "stl_orient", "stl_volume", "dxf_circles",
    "dxf_outline", "design_rules",
]
GATE_SHORT = {
    "step_solid": "G1\nsolid", "step_valid": "G1b\nvalid",
    "step_bbox": "G2\nbbox", "step_volume": "G3\nvolume",
    "step_holes": "G4\nholes", "step_pcd": "G5\npcd",
    "angular_spacing": "G6\nspacing", "step_xor": "G7\nxor",
    "stl_watertight": "G8\nwatert", "stl_orient": "G9\norient",
    "stl_volume": "G10\nstl vol", "dxf_circles": "G11\ndxf ⌀",
    "dxf_outline": "G12\noutline", "design_rules": "G13\nrules",
}
GATE_RULE = {  # one-line pass rule, for figure captions
    "step_solid": "exactly 1 solid",
    "step_valid": "BRepCheck_Analyzer valid",
    "step_bbox": "≤ 0.01 mm per dim",
    "step_volume": "rel err ≤ 0.1%",
    "step_holes": "bolt_n+1 holes, ± 0.01 mm",
    "step_pcd": "on PCD ± 0.02 mm",
    "angular_spacing": "± 0.05° of 360°/n",
    "step_xor": "XOR ≤ 1% of reference",
    "stl_watertight": "watertight + winding",
    "stl_orient": "signed volume > 0",
    "stl_volume": "within 1% of STEP",
    "dxf_circles": "n+2 circles ± 0.01 mm",
    "dxf_outline": "closed rectangle",
    "design_rules": "edge ≥ 8, lig ≥ 6 mm",
}


def load_verdict(path):
    with open(path) as f:
        return json.load(f)


def verdicts_dir():
    return os.path.join(DATA, "verdicts")


def n_pass(v):
    return sum(1 for g in v["gates"].values() if g.get("pass"))


def named_fails(v):
    """Gates that failed on their own evidence (not 'skipped: ...')."""
    out = []
    for name in GATE_ORDER:
        g = v["gates"].get(name, {})
        if not g.get("pass") and not str(g.get("error", "")).startswith("skipped"):
            out.append(name)
    return out


def skipped(v):
    out = []
    for name in GATE_ORDER:
        g = v["gates"].get(name, {})
        if not g.get("pass") and str(g.get("error", "")).startswith("skipped"):
            out.append(name)
    return out


# --- gate error -> compact "measured vs limit" cell text --------------------
# Every number below is parsed out of the judge's own error string in the
# verdict JSON; the fallback keeps qualitative gates honest.
def fail_short(gate, err):
    e = err.split("(")[0].strip()
    m = {
        "step_bbox": (r"component errors \[([\d.e+-]+), ([\d.e+-]+), ([\d.e+-]+)\]",
                      lambda g: (f"Δ{max(float(x) for x in g):g} mm", "> 0.01 mm")),
        "step_volume": (r"rel err ([\d.]+)% > ([\d.]+)%",
                        lambda g: (f"{float(g[0]):g}%", f"> {float(g[1]):g}%")),
        "stl_volume": (r"rel err ([\d.]+)% > ([\d.]+)%",
                       lambda g: (f"{float(g[0]):g}%", f"> {float(g[1]):g}%")),
        "angular_spacing": (r"max deviation ([\d.]+) > ([\d.]+) deg",
                            lambda g: (f"{float(g[0]):g}°", f"> {float(g[1]):g}°")),
        "step_xor": (r"\(([0-9.]+)% of the .*solid\) > (\d+)%",
                     lambda g: (f"{float(g[0]):g}%", f"> {float(g[1]):g}%")),
        "design_rules": (r"min edge distance ([\d.]+) mm < spec ([\d.]+)",
                         lambda g: (f"{float(g[0]):g} mm", f"< {float(g[1]):g}")),
    }
    if gate in m:
        pat, fmt = m[gate]
        g = re.search(pat, err)
        if g:
            return fmt(g.groups())
    if gate == "step_holes":
        g = re.search(r"(\d+) bolt-diameter through-holes found, expected (\d+)", err)
        if g:
            return (f"{g.group(1)} found", f"≠ {g.group(2)}")
        return ("no spec bore", "found")
    if gate == "step_pcd":
        g = re.search(r"radial error up to ([\d.]+) mm", err)
        if g:
            return (f"{float(g.group(1)):g} mm", "> 0.02 mm")
        g = re.search(r"positions off by up to ([\d.]+) mm", err)
        if g:
            return (f"pos {float(g.group(1)):g} mm", "> 0.02 mm")
    if gate == "dxf_circles":
        g = re.search(r"(\d+) CIRCLE entities, expected (\d+)", err)
        if g:
            return (f"{g.group(1)} circles", f"≠ {g.group(2)}")
        g = re.search(r"no DXF circle of diameter ([\d.]+) mm at", err)
        if g:
            return (f"⌀{float(g.group(1)):g} missing", "want @ spec")
        return ("dxf ⌀", "mismatch")
    if gate == "stl_watertight":
        if "not watertight" in err:
            return ("not", "watertight")
        if "winding" in err:
            return ("winding", "inconsistent")
    if gate == "dxf_outline":
        return ("outline", "not closed")
    if gate == "step_bbox":
        return ("bbox", "off spec")
    return (e[:14], "") if e else ("FAIL", "")


def fail_oneliner(gate, err):
    """Judge error compressed to one line for video cards."""
    a, b = fail_short(gate, err)
    return f"{a} {b}".strip()


# --- mesh rendering: painter's-algorithm orthographic renderer ---------------
def rot_ypr(yaw_deg, tilt_deg):
    y, t = math.radians(yaw_deg), math.radians(tilt_deg)
    rz = np.array([[math.cos(y), -math.sin(y), 0.0],
                   [math.sin(y), math.cos(y), 0.0], [0.0, 0.0, 1.0]])
    rx = np.array([[1.0, 0.0, 0.0],
                   [0.0, math.cos(t), -math.sin(t)],
                   [0.0, math.sin(t), math.cos(t)]])
    return rx @ rz


def shade_colors(mesh, R, base, amb=0.42, light=(0.35, 0.45, 0.82)):
    n = mesh.face_normals @ R.T
    l = np.array(light) / np.linalg.norm(light)
    s = amb + (1.0 - amb) * np.clip(n @ l, 0.0, 1.0)
    b = np.array(matplotlib.colors.to_rgb(base))
    return np.clip(s[:, None] * b[None, :], 0.0, 1.0)


def draw_mesh(ax, mesh, yaw=35.0, tilt=22.0, base=BLUE, zoom=1.0,
              edge="none", highlight=None, hl_color=CRIT, zorder=2):
    """Orthographic painter render of a trimesh on a 2-D axes.

    highlight: iterable of face indices drawn last, flat hl_color.
    Returns the view rotation so other panels can match it.
    """
    R = rot_ypr(yaw, tilt)
    v = mesh.vertices @ R.T
    f = mesh.faces
    n = (mesh.face_normals @ R.T)[:, 2]
    keep = n > 0.0                       # backface cull (camera on +z)
    order = np.argsort(v[f[keep]].mean(axis=1)[:, 2], kind="stable")
    fk = f[keep][order]
    cols = shade_colors(mesh, R, base)[keep][order]
    if highlight is not None:
        hl = set(highlight)
        idx = np.array([i for i, face in enumerate(fk) if face in hl], dtype=int)
        if len(idx):
            cols[idx] = matplotlib.colors.to_rgb(hl_color)
    from matplotlib.collections import PolyCollection
    pc = PolyCollection(v[fk][:, :, :2], facecolors=cols, edgecolors=edge,
                        linewidths=0.0 if edge == "none" else 0.4)
    pc.set_zorder(zorder)
    ax.add_collection(pc)
    lo, hi = v.min(axis=0), v.max(axis=0)
    c, r = (lo + hi) / 2.0, (hi - lo) / 2.0
    span = max(r[:2]) * 1.12 / zoom
    ax.set_xlim(c[0] - span, c[0] + span)
    ax.set_ylim(c[1] - span, c[1] + span)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    return R


def proj_points(pts, R):
    return (np.asarray(pts) @ R.T)[:, :2]


def mesh_extent(mesh, R):
    v = mesh.vertices @ R.T
    lo, hi = v.min(axis=0), v.max(axis=0)
    c, r = (lo + hi) / 2.0, (hi - lo) / 2.0
    span = max(r[:2]) * 1.12
    return (c[0] - span, c[0] + span, c[1] - span, c[1] + span)


def fit_axes(ax, ext):
    ax.set_xlim(ext[0], ext[1])
    ax.set_ylim(ext[2], ext[3])
    ax.set_aspect("equal")


def style_axes(ax):
    """Hairline grid + muted ticks for metric panels."""
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(BASELINE)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


# --- figure hygiene: fail loudly on text overlap or clipping ----------------
def assert_no_overlaps(fig, what, ignore_xy=False):
    """Every Text artist inside the figure and free of pairwise overlap.

    Called by every figure builder and on sampled video frames so the
    no-overlap rule is enforced by the script, not by eyeballing.
    """
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    items = []

    def collect(a):
        if isinstance(a, matplotlib.text.Text) and a.get_text().strip():
            try:
                bb = a.get_window_extent(rend)
            except Exception:
                return
            if bb.width > 0 and bb.height > 0:
                items.append((a, bb))

    for a in fig.axes:
        for t in a.texts:
            collect(t)
        if a.title.get_text().strip():
            collect(a.title)
        if hasattr(a, "get_legend") and a.get_legend() is not None:
            items.append((a.get_legend(), a.get_legend().get_window_extent(rend)))
        if not ignore_xy:
            xl, yl = a.get_xlim(), a.get_ylim()
            for t in a.get_xticklabels():
                # only ticks inside the view actually draw; the rest are not
                # on screen and must not be checked
                if t.get_text() and xl[0] <= t.get_position()[0] <= xl[1]:
                    collect(t)
            for t in a.get_yticklabels():
                if t.get_text() and yl[0] <= t.get_position()[1] <= yl[1]:
                    collect(t)
        if a.xaxis.label.get_text().strip():
            collect(a.xaxis.label)
        if a.yaxis.label.get_text().strip():
            collect(a.yaxis.label)
    for t in fig.texts:
        collect(t)

    problems = []
    w, h = fig.canvas.get_width_height()
    for a, bb in items:
        if bb.x0 < -1 or bb.y0 < -1 or bb.x1 > w + 1 or bb.y1 > h + 1:
            problems.append(f"{what}: text clipped by figure: "
                            f"{getattr(a, 'get_text', lambda: str(a))()!r}")
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i][1].overlaps(items[j][1]):
                problems.append(
                    f"{what}: overlap {getattr(items[i][0], 'get_text', lambda: repr(items[i][0]))()!r}"
                    f" <-> {getattr(items[j][0], 'get_text', lambda: repr(items[j][0]))()!r}")
    if problems:
        raise SystemExit("\n".join(problems))
    return len(items)


def load_stl(path):
    import trimesh
    return trimesh.load_mesh(path, force="mesh")


def build_xor_mesh(mesh_a, mesh_b):
    """Symmetric difference as a mesh, exactly like the judge's G7 (manifold3d)."""
    from trimesh.boolean import boolean_manifold
    ab = boolean_manifold([mesh_a, mesh_b], "difference", check_volume=False)
    ba = boolean_manifold([mesh_b, mesh_a], "difference", check_volume=False)
    return boolean_manifold([ab, ba], "union", check_volume=False)


def ref_mesh(spec):
    """Reference solid rebuilt from the spec alone via the judge's own code."""
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "judge"))
    import grade  # noqa: E402  (judge's builder, read-only)
    return grade._tessellate_solid(grade.build_reference(spec))


def dxf_circles(path):
    import ezdxf
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    outline = None
    for lwp in msp.query("LWPOLYLINE"):
        pts = [(p[0], p[1]) for p in lwp.get_points("xy")]
        if lwp.closed and len(pts) == 4:
            outline = pts
    circles = [(c.dxf.center.x, c.dxf.center.y, 2.0 * c.dxf.radius)
               for c in msp.query("CIRCLE")]
    return outline, circles


def spec():
    with open(os.path.join(os.path.dirname(HERE), "judge", "spec.json")) as f:
        return json.load(f)


def bolt_angles(centres):
    """Angular position of each bolt centre, degrees in [0, 360)."""
    return [math.degrees(math.atan2(y, x)) % 360.0 for x, y in centres]
