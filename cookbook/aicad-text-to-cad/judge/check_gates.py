#!/usr/bin/env python3
"""Gates for the aicad-text-to-cad demo.

Usage: check_gates.py <part_dir> --seed N [--json out.json]

<part_dir> is a copy of the artifact (grade.sh made it); this script runs
the pinned tool inside it and judges the DELIVERED files (model.step /
model.stl) against judge/spec.json using four independent sources of
truth (SPEC.md, "Acceptance oracle"):

  1. the OCP CAD kernel  — STEP re-import, BRepCheck_Analyzer validity,
                           exact B-rep volume/bounds, cylindrical faces
  2. trimesh             — STL watertightness, winding consistency, bounds
  3. manifold3d          — boolean XOR of the delivered solid against a
                           reference solid built from spec.json alone
  4. judge/spec.json     — the hand-written contract

Prints exactly one verdict JSON and exits 0 only if every gate passes.
All numbers are deterministic given --seed (PCG64 drives only the
min-wall sampling; kernel tessellation runs single-threaded).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

JUDGE_DIR = Path(__file__).resolve().parent
VENV = Path(os.environ.get("AICAD_JUDGE_VENV", str(Path.home() / ".venvs/aicad-judge")))
VENV_PY = VENV / "bin" / "python"

TOL_BBOX_MM = 0.05           # gate 5: axis extents vs spec
TOL_STL_BBOX_MM = 0.2        # gate 5: STL vs STEP bounds (chord error)
TOL_VOLUME_REL = 0.005       # gate 6: B-rep volume vs analytic
TOL_XOR_REL = 0.010          # gate 7: XOR volume vs reference volume
TOL_POS_MM = 0.05            # gate 8: hole centres vs spec
TOL_RADIUS_MM = 0.01         # gate 8: cylinder radii vs spec
TOL_AXIS_PARALLEL = 1e-7     # gate 8: cylinder axis vs spec axis
TOL_ANGLE_DEG = 0.5          # gate 8: bolt-circle angular spacing
TOL_WALL_MM = 0.1            # gate 9: allowance on min wall
TOL_SPEC_CONSISTENCY = 1e-9  # reference solid volume vs stored analytic

XOR_LINEAR_DEFLECTION = 0.01  # kernel tessellation for the XOR gate
XOR_ANGULAR_TOLERANCE = 0.02
WALL_SAMPLES_PER_HOLE = 48    # seeded rays per hole for the min-wall gate


class Gate(dict):
    """One gate's verdict: pass flag plus measured vs rule detail."""
    def __init__(self):
        super().__init__({"pass": None, "measured": None, "rule": None})
        self.t0 = time.monotonic()

    def ok(self, **kw):
        self["pass"] = True
        self.update(kw)

    def fail(self, **kw):
        self["pass"] = False
        self.update(kw)

    def secs(self):
        self["secs"] = round(time.monotonic() - self.t0, 3)


# ---------------------------------------------------------------------------
# kernel imports
# ---------------------------------------------------------------------------
def import_ocp():
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepBuilderAPI import (
        BRepBuilderAPI_MakeEdge,
        BRepBuilderAPI_MakeFace,
        BRepBuilderAPI_MakeWire,
    )
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Bnd import Bnd_Box
    from OCP.GC import GC_MakeArcOfCircle
    from OCP.GProp import GProp_GProps
    from OCP.GeomAbs import GeomAbs_SurfaceType
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Vec
    from OCP.IFSelect import IFSelect_ReturnStatus
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    return dict(locals())


AXIS_VEC = {"Z": (0.0, 0.0, 1.0), "Y": (0.0, 1.0, 0.0), "X": (1.0, 0.0, 0.0)}


def shape_volume(shape, o):
    props = o["GProp_GProps"]()
    o["BRepGProp"].VolumeProperties_s(shape, props)
    return props.Mass()


def shape_bbox(shape, o):
    box = o["Bnd_Box"]()
    o["BRepBndLib"].Add_s(shape, box)
    return box.Get()  # xmin, ymin, zmin, xmax, ymax, zmax


def solids_of(shape, o):
    out, exp = [], o["TopExp_Explorer"](shape, o["TopAbs_SOLID"])
    while exp.More():
        out.append(exp.Current())
        exp.Next()
    return out


def cylindrical_faces(shape, o):
    """[(radius, axis_dir, axis_point)] for every cylindrical face."""
    out, exp = [], o["TopExp_Explorer"](shape, o["TopAbs_FACE"])
    while exp.More():
        face = o["TopoDS"].Face_s(exp.Current())
        surf = o["BRepAdaptor_Surface"](face)
        if surf.GetType() == o["GeomAbs_SurfaceType"].GeomAbs_Cylinder:
            cyl = surf.Cylinder()
            ax = cyl.Axis()
            loc, direction = ax.Location(), ax.Direction()
            out.append((cyl.Radius(),
                        (direction.X(), direction.Y(), direction.Z()),
                        (loc.X(), loc.Y(), loc.Z())))
        exp.Next()
    return out


def tessellate(shape, o, lin=XOR_LINEAR_DEFLECTION, ang=XOR_ANGULAR_TOLERANCE):
    """Single-threaded kernel tessellation -> (verts, tris), 0-based."""
    o["BRepMesh_IncrementalMesh"](shape, lin, False, ang, False)
    verts, tris, offset = [], [], 0
    exp = o["TopExp_Explorer"](shape, o["TopAbs_FACE"])
    loc = o["TopLoc_Location"]()
    while exp.More():
        face = o["TopoDS"].Face_s(exp.Current())
        tri = o["BRep_Tool"].Triangulation_s(face, loc)
        if tri is not None:
            for i in range(1, tri.NbNodes() + 1):
                p = tri.Node(i)
                verts.append((p.X(), p.Y(), p.Z()))
            for i in range(1, tri.NbTriangles() + 1):
                a, b, c = tri.Triangle(i).Get()
                tris.append((a - 1 + offset, b - 1 + offset, c - 1 + offset))
            offset += tri.NbNodes()
        exp.Next()
    return verts, tris


def manifold_from_shape(shape, o):
    import numpy as np
    import manifold3d as m3
    verts, tris = tessellate(shape, o)
    mesh = m3.Mesh(
        np.asarray(verts, dtype=np.float32),
        np.asarray(tris, dtype=np.uint32),
    )
    return m3.Manifold(mesh)


# ---------------------------------------------------------------------------
# reference solids, built from judge/spec.json alone (no tool code)
# ---------------------------------------------------------------------------
def _cyl(o, radius, height, base, axis):
    frame = o["gp_Ax2"](o["gp_Pnt"](*base), o["gp_Dir"](*axis))
    return o["BRepPrimAPI_MakeCylinder"](frame, radius, height).Shape()


def _filleted_profile_edges(spec, o):
    """Polygon walk with the corner replaced by the tangent arc.

    Returns a list of ("line", p, q) / ("arc", p, mid, q) segments in the
    XZ plane, all coordinates taken from spec.json.
    """
    d = spec["dims"]
    pts = [tuple(p) for p in spec["footprint_xz"]]
    r = d["fillet_radius_mm"]
    cx, cz = d["leg_thickness_mm"], d["leg_thickness_mm"]  # re-entrant corner
    t1 = (cx + r, cz)   # tangent on the edge entering the corner
    t2 = (cx, cz + r)   # tangent on the edge leaving the corner
    mid = (cx + r - r / math.sqrt(2), cz + r - r / math.sqrt(2))
    segs = []
    for i, a in enumerate(pts):
        b = pts[(i + 1) % len(pts)]
        start = t2 if a == (cx, cz) else a
        end = t1 if b == (cx, cz) else b
        segs.append(("line", start, end))
        if end == t1:
            segs.append(("arc", t1, mid, t2))
    return segs


def build_reference(part, spec, o):
    """The spec solid via kernel primitives — spec.json is the only input."""
    fuse, cut = o["BRepAlgoAPI_Fuse"], o["BRepAlgoAPI_Cut"]
    gp_Pnt, gp_Vec = o["gp_Pnt"], o["gp_Vec"]

    if part == "bushing":
        d = spec["dims"]
        shaft = _cyl(o, d["shaft_od_mm"] / 2, d["shaft_height_mm"], (0, 0, 0), (0, 0, 1))
        flange = _cyl(o, d["flange_od_mm"] / 2, d["flange_height_mm"],
                      (0, 0, d["shaft_height_mm"]), (0, 0, 1))
        body = fuse(shaft, flange).Shape()
        h = d["shaft_height_mm"] + d["flange_height_mm"] + 2
        return cut(body, _cyl(o, d["bore_d_mm"] / 2, h, (0, 0, -1), (0, 0, 1))).Shape()

    if part == "adapter_plate":
        d = spec["dims"]
        s, t = d["plate_side_mm"], d["plate_thickness_mm"]
        box = o["BRepPrimAPI_MakeBox"](gp_Pnt(-s / 2, -s / 2, 0), gp_Pnt(s / 2, s / 2, t)).Shape()
        body = cut(box, _cyl(o, d["centre_bore_d_mm"] / 2, t + 2, (0, 0, -1), (0, 0, 1))).Shape()
        step = 360.0 / d["bolt_holes"]
        for i in range(d["bolt_holes"]):
            ang = math.radians(d["first_hole_angle_deg"] + i * step)
            x = d["bolt_circle_d_mm"] / 2 * math.cos(ang)
            y = d["bolt_circle_d_mm"] / 2 * math.sin(ang)
            body = cut(body, _cyl(o, d["bolt_hole_d_mm"] / 2, t + 2, (x, y, -1), (0, 0, 1))).Shape()
        return body

    if part == "bracket":
        d = spec["dims"]
        wire = o["BRepBuilderAPI_MakeWire"]()
        mk_edge = o["BRepBuilderAPI_MakeEdge"]
        p3 = lambda p: gp_Pnt(p[0], 0.0, p[1])  # profile lives in XZ
        for seg in _filleted_profile_edges(spec, o):
            if seg[0] == "line":
                wire.Add(mk_edge(p3(seg[1]), p3(seg[2])).Edge())
            else:
                arc = o["GC_MakeArcOfCircle"](p3(seg[1]), p3(seg[2]), p3(seg[3])).Value()
                wire.Add(mk_edge(arc).Edge())
        face = o["BRepBuilderAPI_MakeFace"](wire.Wire()).Face()
        body = o["BRepPrimAPI_MakePrism"](face, gp_Vec(0, d["depth_y_mm"], 0)).Shape()
        for x, z in _bracket_holes(spec):
            body = cut(body, _cyl(o, d["mount_hole_d_mm"] / 2, d["depth_y_mm"] + 2,
                                  (x, -1, z), (0, 1, 0))).Shape()
        return body

    raise ValueError(f"unknown part {part!r}")


def _bracket_holes(spec):
    for h in spec["hole_centres"]:
        if "positions_xz" in h:
            for p in h["positions_xz"]:
                yield tuple(p)


# ---------------------------------------------------------------------------
# the gates
# ---------------------------------------------------------------------------
def g_tool_runs(part_dir, o):
    """Gate 1: the pinned tool executes the artifact's model.py in the copy."""
    g = Gate()
    env = dict(os.environ, CADGEN_DAEMON="0")
    proc = subprocess.run([str(VENV_PY), "model.py"], cwd=part_dir, env=env,
                          capture_output=True, text=True, timeout=300)
    step_ok = (part_dir / "model.step").is_file()
    stl_ok = (part_dir / "model.stl").is_file()
    if proc.returncode == 0 and step_ok and stl_ok:
        g.ok(measured={"exit": 0, "wrote_step": True, "wrote_stl": True},
             rule="cadgen exits 0 and writes model.step + model.stl")
    else:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-6:]
        g.fail(measured={"exit": proc.returncode, "wrote_step": step_ok,
                         "wrote_stl": stl_ok, "log_tail": tail},
               rule="cadgen exits 0 and writes model.step + model.stl")
    g.secs()
    return g


def g_delivery_matches(delivered, regen_dir, spec, o):
    """Gate 2: delivered files are byte-identical to a fresh regeneration."""
    g = Gate()
    detail = {}
    ok = True
    for name in ("model.step", "model.stl"):
        a = hashlib.sha256((delivered / name).read_bytes()).hexdigest()
        b = hashlib.sha256((regen_dir / name).read_bytes()).hexdigest()
        detail[name] = {"delivered": a[:16], "regen": b[:16], "equal": a == b}
        ok = ok and a == b
    (g.ok if ok else g.fail)(measured=detail,
                             rule="sha256(delivered) == sha256(fresh cadgen run)")
    g.secs()
    return g


def g_step_valid(step_path, o):
    """Gate 3: STEP re-imports, is BRepCheck-valid, exactly one solid."""
    g = Gate()
    reader = o["STEPControl_Reader"]()
    status = reader.ReadFile(str(step_path))
    if status != o["IFSelect_ReturnStatus"].IFSelect_RetDone:
        g.fail(measured={"import": str(status)}, rule="STEP import returns IFSelect_RetDone")
        g.secs()
        return g
    reader.TransferRoots()
    shape = reader.OneShape()
    valid = o["BRepCheck_Analyzer"](shape).IsValid()
    n = len(solids_of(shape, o))
    measured = {"import": "ok", "brepcheck_valid": valid, "solids": n}
    if valid and n == 1:
        g.ok(measured=measured, rule="BRepCheck_Analyzer valid and exactly 1 solid")
    else:
        g.fail(measured=measured, rule="BRepCheck_Analyzer valid and exactly 1 solid")
    g.secs()
    return g, shape


def g_stl_valid(stl_path, o):
    """Gate 4: STL is watertight, winding-consistent, one body."""
    import trimesh
    g = Gate()
    mesh = trimesh.load_mesh(str(stl_path))
    measured = {"watertight": bool(mesh.is_watertight),
                "winding_consistent": bool(mesh.is_winding_consistent),
                "bodies": int(mesh.body_count),
                "facets": int(len(mesh.faces))}
    if measured["watertight"] and measured["winding_consistent"] and measured["bodies"] == 1:
        g.ok(measured=measured, rule="is_watertight and is_winding_consistent, 1 body")
    else:
        g.fail(measured=measured, rule="is_watertight and is_winding_consistent, 1 body")
    g.secs()
    return g, mesh


def g_bbox(shape, mesh, spec, o):
    """Gate 5: STEP bounds vs spec; STL bounds vs STEP."""
    g = Gate()
    want = spec["bbox_mm"]
    bb = shape_bbox(shape, o)
    extents = [bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]]
    step_dev = [abs(e - w) for e, w in zip(extents, want)]
    mb = mesh.bounds
    mext = [mb[1][i] - mb[0][i] for i in range(3)]
    stl_dev = [abs(a - b) for a, b in zip(mext, extents)]
    measured = {"step_extents": [round(x, 4) for x in extents],
                "spec": want,
                "step_max_dev_mm": round(max(step_dev), 4),
                "stl_max_dev_vs_step_mm": round(max(stl_dev), 4)}
    rule = (f"each axis within {TOL_BBOX_MM} mm of spec; "
            f"STL within {TOL_STL_BBOX_MM} mm of STEP")
    if max(step_dev) <= TOL_BBOX_MM and max(stl_dev) <= TOL_STL_BBOX_MM:
        g.ok(measured=measured, rule=rule)
    else:
        g.fail(measured=measured, rule=rule)
    g.secs()
    return g


def g_volume_analytic(shape, spec, o):
    """Gate 6: exact B-rep volume vs the spec's analytic volume."""
    g = Gate()
    vol = shape_volume(shape, o)
    want = spec["analytic_volume_mm3"] if "analytic_volume_mm3" in spec \
        else spec["analytic_volume_pi_scale"] * math.pi
    rel = abs(vol - want) / want
    measured = {"volume_mm3": round(vol, 6), "analytic_mm3": round(want, 6),
                "rel_err": round(rel, 9)}
    if rel <= TOL_VOLUME_REL:
        g.ok(measured=measured, rule=f"relative error <= {TOL_VOLUME_REL:.1%}")
    else:
        g.fail(measured=measured, rule=f"relative error <= {TOL_VOLUME_REL:.1%}")
    g.secs()
    return g


def g_xor_volume(shape, part, spec, o):
    """Gate 7: manifold3d XOR of delivered solid vs the spec-built reference."""
    g = Gate()
    import manifold3d as m3
    ref = build_reference(part, spec, o)
    ref_vol = shape_volume(ref, o)
    want = spec["analytic_volume_mm3"] if "analytic_volume_mm3" in spec \
        else spec["analytic_volume_pi_scale"] * math.pi
    consistency = abs(ref_vol - want) / want
    if consistency > TOL_SPEC_CONSISTENCY:
        # the judge's own spec numbers disagree with the kernel — refuse
        g.fail(measured={"reference_volume_mm3": round(ref_vol, 6),
                         "spec_analytic_mm3": round(want, 6),
                         "rel_mismatch": round(consistency, 12)},
               rule=f"spec.json analytic volume matches kernel-built reference "
                    f"within {TOL_SPEC_CONSISTENCY:.0e} (judge self-check)")
        g.secs()
        return g
    a = manifold_from_shape(shape, o)
    b = manifold_from_shape(ref, o)
    xor = a ^ b
    xor_vol = xor.volume()
    rel = xor_vol / ref_vol
    measured = {"xor_volume_mm3": round(xor_vol, 6),
                "reference_volume_mm3": round(ref_vol, 6),
                "rel": round(rel, 6),
                "tessellation": {"linear_deflection": XOR_LINEAR_DEFLECTION,
                                 "angular_tolerance": XOR_ANGULAR_TOLERANCE}}
    if rel <= TOL_XOR_REL:
        g.ok(measured=measured, rule=f"XOR volume <= {TOL_XOR_REL:.1%} of reference")
    else:
        g.fail(measured=measured, rule=f"XOR volume <= {TOL_XOR_REL:.1%} of reference")
    g.secs()
    return g


def g_features(shape, part, spec, o):
    """Gate 8: cylindrical faces — counts, radii, hole centres, spacing.

    The only home-grown gate: it reads the kernel's cylinder analysis and
    applies SPEC.md's rules (counts/radii per class, hole centres within
    0.05 mm, bolt-circle spacing 90° ± 0.5°).
    """
    g = Gate()
    faces = cylindrical_faces(shape, o)
    measured_classes, errors = {}, []

    for cyl in spec["cylinders"]:
        cls, want_r = cyl["class"], cyl["radius_mm"]
        axis = AXIS_VEC[cyl["axis"]]
        matches = [
            f for f in faces
            if abs(f[0] - want_r) <= TOL_RADIUS_MM
            and abs(abs(_dot(f[1], axis)) - 1.0) <= TOL_AXIS_PARALLEL
        ]
        measured_classes[cls] = {
            "radius_mm": sorted(round(f[0], 6) for f in matches),
            "count": len(matches),
            "count_expected": cyl["count"],
            "centres": sorted(
                (_axis_pos(f, cyl["axis"]) for f in matches),
                key=lambda c: (round(c[0], 4), round(c[1], 4))),
        }
        if len(matches) != cyl["count"]:
            errors.append(f"{cls}: {len(matches)} faces, spec wants {cyl['count']}")

    # hole-centre positions (bushing bore, plate bores, bracket holes)
    centres_by_class = {}
    for h in spec.get("hole_centres", []):
        cls = h["class"]
        if cls not in measured_classes:
            continue
        centres_by_class[cls] = measured_classes[cls]["centres"]
        if "centre" in h:
            want = [h["centre"]]
            for c in measured_classes[cls]["centres"]:
                if _dist2(c, want[0]) > TOL_POS_MM ** 2:
                    errors.append(f"{cls}: centre ({c[0]:.3f},{c[1]:.3f}) not within "
                                  f"{TOL_POS_MM} mm of {want[0]}")
        if "positions_xz" in h:
            want = [tuple(p) for p in h["positions_xz"]]
            for c in measured_classes[cls]["centres"]:
                if min(_dist2(c, w) for w in want) > TOL_POS_MM ** 2:
                    errors.append(f"{cls}: centre ({c[0]:.3f},{c[1]:.3f}) not within "
                                  f"{TOL_POS_MM} mm of any spec position")
        if "bolt_circle_radius_mm" in h:
            r_bcd, angles = h["bolt_circle_radius_mm"], h["angles_deg"]
            want = [(r_bcd * math.cos(math.radians(a)), r_bcd * math.sin(math.radians(a)))
                    for a in angles]
            for c in measured_classes[cls]["centres"]:
                if min(_dist2(c, w) for w in want) > TOL_POS_MM ** 2:
                    errors.append(f"{cls}: centre ({c[0]:.3f},{c[1]:.3f}) not within "
                                  f"{TOL_POS_MM} mm of any spec bolt position")
            got_angles = sorted(
                math.degrees(math.atan2(c[1], c[0])) % 360.0
                for c in measured_classes[cls]["centres"])
            if len(got_angles) >= 2:
                gaps = [(got_angles[(i + 1) % len(got_angles)] - got_angles[i]) % 360.0
                        for i in range(len(got_angles))]
                measured_classes[cls]["angular_gaps_deg"] = [round(x, 3) for x in gaps]
                if any(abs(gap - 360.0 / len(got_angles)) > TOL_ANGLE_DEG for gap in gaps):
                    errors.append(f"{cls}: angular gaps {measured_classes[cls]['angular_gaps_deg']} "
                                  f"not within {TOL_ANGLE_DEG}° of equal spacing")

    measured = {"cylindrical_faces_total": len(faces),
                "classes": measured_classes, "errors": errors}
    if not errors:
        g.ok(measured=measured, rule="counts/radii per class exact; centres within "
                                     f"{TOL_POS_MM} mm; spacing within {TOL_ANGLE_DEG}°")
    else:
        g.fail(measured=measured, rule="counts/radii per class exact; centres within "
                                       f"{TOL_POS_MM} mm; spacing within {TOL_ANGLE_DEG}°")
    g.secs()
    return g


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _dist2(a, b):
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2


def _axis_pos(face, axis_name):
    """Cylinder axis position in the plane perpendicular to its axis."""
    r, direction, loc = face
    if axis_name == "Z":
        return (loc[0], loc[1])
    if axis_name == "Y":
        return (loc[0], loc[2])
    return (loc[1], loc[2])


def g_min_wall(mesh, part, spec, o, seed):
    """Gate 9: seeded ray-cast wall thickness at the spec's hole surfaces."""
    import numpy as np
    import trimesh
    g = Gate()
    if spec.get("min_wall_mm") is None:
        g.ok(measured={"applicable": False},
             rule=f"not graded for {part} (spec sets min_wall_mm = null)")
        g.secs()
        return g
    want = spec["min_wall_mm"]
    rng = np.random.Generator(np.random.PCG64(seed))
    origins, dirs = [], []
    hole_classes = [c for c in spec["cylinders"]
                    if c["class"] in {h["class"] for h in spec.get("hole_centres", [])}]
    for cyl in hole_classes:
        axis_name = cyl["axis"]
        # hole axis positions (2-D, in the plane perpendicular to the axis)
        centres = _spec_hole_axes(spec, cyl["class"], axis_name)
        for centre in centres:
            for _ in range(WALL_SAMPLES_PER_HOLE):
                theta = 2 * math.pi * rng.random()
                c, s = math.cos(theta), math.sin(theta)
                if axis_name == "Z":      # 2-D plane (x, y)
                    radial3 = (c, s, 0.0)
                    base = (centre[0] + cyl["radius_mm"] * c,
                            centre[1] + cyl["radius_mm"] * s, _axis_mid(spec, part))
                else:                     # axis Y: 2-D plane (x, z)
                    radial3 = (c, 0.0, s)
                    base = (centre[0] + cyl["radius_mm"] * c,
                            spec["dims"]["depth_y_mm"] / 2,
                            centre[1] + cyl["radius_mm"] * s)
                origins.append([base[i] + 1e-4 * radial3[i] for i in range(3)])
                dirs.append(list(radial3))
    locs, index_ray, _ = mesh.ray.intersects_location(
        np.array(origins), np.array(dirs), multiple_hits=False)
    if len(locs) == 0:
        g.fail(measured={"rays": len(origins), "hits": 0},
               rule=f"min wall >= {want} - {TOL_WALL_MM} mm (every ray must hit)")
        g.secs()
        return g
    import numpy as np2
    d = np2.linalg.norm(locs - np.array(origins)[index_ray], axis=1)
    wall = float(d.min())
    measured = {"rays": len(origins), "min_wall_mm": round(wall, 4),
                "spec_min_wall_mm": want}
    if wall >= want - TOL_WALL_MM:
        g.ok(measured=measured, rule=f"min wall >= {want} - {TOL_WALL_MM} mm")
    else:
        g.fail(measured=measured, rule=f"min wall >= {want} - {TOL_WALL_MM} mm")
    g.secs()
    return g


def _spec_hole_axes(spec, cls, axis_name):
    """Hole-axis centre positions (2-D) from the spec's hole_centres."""
    out = []
    for h in spec.get("hole_centres", []):
        if h["class"] != cls:
            continue
        if "centre" in h:
            out.append(tuple(h["centre"]))
        if "positions_xz" in h:
            out.extend(tuple(p) for p in h["positions_xz"])
        if "bolt_circle_radius_mm" in h:
            for a in h["angles_deg"]:
                t = math.radians(a)
                out.append((h["bolt_circle_radius_mm"] * math.cos(t),
                            h["bolt_circle_radius_mm"] * math.sin(t)))
    return out


def _axis_mid(spec, part):
    """Mid-height along the Z axis for Z-axis holes (ray origin height)."""
    bbox = spec["bbox_mm"]
    return bbox[2] / 2


def g_judge_intact(before: dict, o):
    """Gate 10: nothing under judge/ changed while the artifact ran."""
    g = Gate()
    after = judge_hashes()
    changed = {k for k in before if before[k] != after.get(k)}
    if not changed and len(after) == len(before):
        g.ok(measured={"files": len(after)}, rule="sha256 of every judge/ file unchanged")
    else:
        g.fail(measured={"changed": sorted(changed)},
               rule="sha256 of every judge/ file unchanged")
    g.secs()
    return g


def judge_hashes():
    out = {}
    for p in sorted(JUDGE_DIR.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(JUDGE_DIR))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("part_dir", type=Path)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()
    part_dir = args.part_dir.resolve()

    spec_all = json.loads((JUDGE_DIR / "spec.json").read_text())
    # part identity: mutants carry part.txt; good examples use the dir name
    part_file = part_dir / "part.txt"
    part = part_file.read_text().strip() if part_file.is_file() else part_dir.name
    if part not in spec_all["parts"]:
        print(json.dumps({"error": f"unknown part {part!r} (dir {part_dir.name!r})"}))
        return 2
    spec = spec_all["parts"][part]

    import shutil, tempfile
    o = import_ocp()

    judge_before = judge_hashes()
    verdict = {"part": part, "artifact": part_dir.name, "seed": args.seed,
               "tool": "cadgen 0.7.2 (github.com/earthtojake/text-to-cad, MIT)",
               "gates": {}, "timing": {}}

    # gates 1+2: run the tool in a fresh scratch copy, compare to delivered
    with tempfile.TemporaryDirectory(prefix="aicad-regen-") as td:
        regen = Path(td) / "regen"
        shutil.copytree(part_dir, regen,
                        ignore=shutil.ignore_patterns("model.step", "model.stl"))
        g1 = g_tool_runs(regen, o)
        verdict["gates"]["tool_runs"] = g1
        if g1["pass"]:
            verdict["gates"]["delivery_matches"] = g_delivery_matches(part_dir, regen, spec, o)
        else:
            verdict["gates"]["delivery_matches"] = Gate()
            verdict["gates"]["delivery_matches"].fail(
                measured={"skipped": True}, rule="tool did not run; nothing to compare")

    # gates 3-9 on the DELIVERED files
    g3, shape = g_step_valid(part_dir / "model.step", o)
    verdict["gates"]["step_valid"] = g3
    g4, mesh = g_stl_valid(part_dir / "model.stl", o)
    verdict["gates"]["stl_valid"] = g4

    if shape is not None:
        verdict["gates"]["bbox"] = g_bbox(shape, mesh, spec, o)
        verdict["gates"]["volume_analytic"] = g_volume_analytic(shape, spec, o)
        verdict["gates"]["xor_volume"] = g_xor_volume(shape, part, spec, o)
        verdict["gates"]["features"] = g_features(shape, part, spec, o)
        verdict["gates"]["min_wall"] = g_min_wall(mesh, part, spec, o, args.seed)
    else:
        for name in ("bbox", "volume_analytic", "xor_volume", "features", "min_wall"):
            gg = Gate()
            gg.fail(measured={"skipped": True}, rule="STEP did not import; gate skipped")
            verdict["gates"][name] = gg

    verdict["gates"]["judge_intact"] = g_judge_intact(judge_before, o)

    # wall-time fields live ONLY under "timing" so the rest of the verdict
    # is byte-identical across same-seed runs (DEMO-STANDARD.md)
    verdict["pass"] = all(v.get("pass") is True for v in verdict["gates"].values())
    verdict["timing"] = {k: v.pop("secs") for k, v in sorted(verdict["gates"].items())}
    verdict["timing"]["total_s"] = round(sum(verdict["timing"].values()), 3)

    text = json.dumps(verdict, indent=2, sort_keys=True)
    if args.json:
        args.json.write_text(text + "\n")
    print(text)
    return 0 if verdict["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
