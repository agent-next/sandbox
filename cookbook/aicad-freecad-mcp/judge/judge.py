#!/usr/bin/env python3
"""Grade one delivered part against its spec, using pinned open-source CAD
libraries as the oracle:

- CadQuery / OCP: STEP re-import, BRepCheck_Analyzer validity, exact B-rep
  volume, cylindrical-face inventory (radii, axes, positions)
- trimesh: STL watertight / winding / volume / bounds
- manifold3d: boolean symmetric difference vs a reference solid that the
  judge rebuilds from the spec with CadQuery
- ezdxf: DXF audit + entity read (plate only)

Only the spec-specific rules (hole counts, diameters, angular spacing, fillet
radius) are demo code. Prints one JSON verdict; exit 0 iff every gate passes.
"""
import argparse
import json
import math
import os
import sys
import time

import cadquery as cq
import ezdxf
import manifold3d
import numpy as np
import trimesh
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.GeomAbs import GeomAbs_SurfaceType
from OCP.GProp import GProp_GProps

BBOX_TOL = 0.05          # mm, per axis vs the spec box
VOLUME_TOL = 0.005       # 0.5 % vs analytic volume
XOR_FRAC = 0.01          # XOR volume <= 1 % of reference volume
MIN_WALL = 1.2           # mm, measured minimum wall (spec minimum 1.5 mm)
RADIUS_TOL = 0.05        # mm, matching cylindrical faces to spec radii
ANGLE_TOL = 0.1          # degrees, bolt-hole angular positions


def analytic_volume(part):
    pi = math.pi
    if part == "bushing":
        return pi * (18.0 ** 2 * 40.0 - 10.0 ** 2 * 40.0 + (30.0 ** 2 - 18.0 ** 2) * 8.0)
    if part == "plate":
        return (100.0 * 80.0 * 10.0 - pi * 15.0 ** 2 * 10.0
                - 6.0 * pi * 2.75 ** 2 * 10.0)
    if part == "bracket":
        return (80.0 * 50.0 * 10.0 + 10.0 * 50.0 * 50.0
                + 8.0 ** 2 * (1.0 - pi / 4.0) * 50.0
                - 2.0 * pi * 5.0 ** 2 * 10.0 - 2.0 * pi * 6.0 ** 2 * 10.0)
    raise ValueError("unknown part %r" % part)


def spec_bbox(part):
    return {
        "bushing": (60.0, 60.0, 40.0),
        "plate": (100.0, 80.0, 10.0),
        "bracket": (80.0, 50.0, 60.0),
    }[part]


def reference_solid(part):
    """Judge-built CadQuery reference solid from the spec constants."""
    if part == "bushing":
        hub = cq.Workplane("XY").circle(18.0).extrude(40.0)
        flange = cq.Workplane("XY").circle(30.0).extrude(8.0)
        bore = cq.Workplane("XY").circle(10.0).extrude(42.0)
        return (hub.union(flange)).cut(bore)
    if part == "plate":
        plate = cq.Workplane("XY").box(100.0, 80.0, 10.0)
        # the plate is centred on z=0; cutters must pass all the way through
        plate = plate - cq.Workplane("XY").workplane(offset=-6.0) \
            .circle(15.0).extrude(12.0)
        for i in range(6):
            a = math.radians(i * 60.0)
            plate = plate - (
                cq.Workplane("XY").workplane(offset=-6.0)
                .center(35.0 * math.cos(a), 35.0 * math.sin(a))
                .circle(2.75).extrude(12.0))
        return plate
    if part == "bracket":
        # pure OCP build: boxes + cylinders + a fillet, so the reference is
        # independent of the CadQuery Workplane layer
        from OCP.BRep import BRep_Tool
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
        from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
        from OCP.BRepPrimAPI import (BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder)
        from OCP.GeomAbs import GeomAbs_CurveType
        from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
        from OCP.TopAbs import TopAbs_EDGE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS

        def box(x0, y0, z0, dx, dy, dz):
            return BRepPrimAPI_MakeBox(gp_Pnt(x0, y0, z0),
                                       gp_Pnt(x0 + dx, y0 + dy, z0 + dz)).Shape()

        def cyl(px, py, pz, dx, dy, dz, r, h):
            return BRepPrimAPI_MakeCylinder(
                gp_Ax2(gp_Pnt(px, py, pz), gp_Dir(dx, dy, dz)), r, h).Shape()

        def fuse(a, b):
            op = BRepAlgoAPI_Fuse(a, b)
            op.Build()
            return op.Shape()

        def cut(a, b):
            op = BRepAlgoAPI_Cut(a, b)
            op.Build()
            return op.Shape()

        solid = fuse(box(0, 0, 0, 80, 50, 10), box(70, 0, 10, 10, 50, 50))
        # fillet the inner concave edge: straight edge along y at x=70, z=10
        target = None
        explorer = TopExp_Explorer(solid, TopAbs_EDGE)
        while explorer.More():
            edge = TopoDS.Edge_s(explorer.Current())
            ad = BRepAdaptor_Curve(edge)
            if ad.GetType() == GeomAbs_CurveType.GeomAbs_Line:
                p1, p2 = ad.Value(ad.FirstParameter()), ad.Value(ad.LastParameter())
                if (abs(p1.X() - 70.0) < 1e-6 and abs(p1.Z() - 10.0) < 1e-6
                        and abs(p2.X() - 70.0) < 1e-6 and abs(p2.Z() - 10.0) < 1e-6
                        and abs(p2.Y() - p1.Y() - 50.0) < 1e-6):
                    target = edge
                    break
            explorer.Next()
        if target is None:
            raise RuntimeError("reference: inner edge not found")
        fillet = BRepFilletAPI_MakeFillet(solid)
        fillet.Add(8.0, target)
        fillet.Build()
        solid = fillet.Shape()
        solid = cut(solid, cyl(25, 25, -1, 0, 0, 1, 5.0, 12.0))
        solid = cut(solid, cyl(55, 25, -1, 0, 0, 1, 5.0, 12.0))
        solid = cut(solid, cyl(69, 15, 45, 1, 0, 0, 6.0, 12.0))
        solid = cut(solid, cyl(69, 35, 45, 1, 0, 0, 6.0, 12.0))
        return cq.Workplane(obj=cq.Shape.cast(solid))
    raise ValueError("unknown part %r" % part)


def cylindrical_faces(shape):
    """[(radius, axis, point_on_axis)] for every cylindrical face."""
    out = []
    for face in shape.Faces():
        ad = BRepAdaptor_Surface(face.wrapped)
        if ad.GetType() != GeomAbs_SurfaceType.GeomAbs_Cylinder:
            continue
        cyl = ad.Cylinder()
        ax = cyl.Axis()
        d = ax.Direction()
        p = ax.Location()
        out.append((cyl.Radius(),
                    (d.X(), d.Y(), d.Z()),
                    (p.X(), p.Y(), p.Z())))
    return out


def occ_volume(shape):
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, props)
    return props.Mass()


def tessellate(shape, deflection=0.02):
    """Tessellate a cadquery shape with BRepMesh into a trimesh mesh."""
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopoDS import TopoDS
    from OCP.TopLoc import TopLoc_Location
    from OCP.BRep import BRep_Tool

    BRepMesh_IncrementalMesh(shape.wrapped, deflection, False, 0.5, True)
    verts, faces = [], []
    explorer = TopExp_Explorer(shape.wrapped, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is not None:
            base = len(verts)
            trsf = loc.Transformation()
            for i in range(1, tri.NbNodes() + 1):
                p = tri.Node(i).Transformed(trsf)
                verts.append((p.X(), p.Y(), p.Z()))
            rev = face.Orientation() == TopAbs_REVERSED
            for i in range(1, tri.NbTriangles() + 1):
                a, b, c = tri.Triangle(i).Get()
                if rev:
                    a, c = c, a
                faces.append((base + a - 1, base + b - 1, base + c - 1))
        explorer.Next()
    return trimesh.Trimesh(vertices=np.array(verts), faces=np.array(faces), process=False)


def to_manifold(mesh):
    m = mesh.copy()
    m.merge_vertices()
    return manifold3d.Manifold(manifold3d.Mesh(
        np.ascontiguousarray(m.vertices, dtype=np.float32),
        np.ascontiguousarray(m.faces, dtype=np.uint32)))


def xor_volume(mesh_a, mesh_b):
    a, b = to_manifold(mesh_a), to_manifold(mesh_b)
    return float((a - b + b - a).volume())


def min_wall_thickness(mesh, seed, samples=2400):
    """Sampled minimum wall thickness: inward-ray chords from surface points.

    At each seeded surface sample, shoot a ray along the inward normal and
    take the distance to the first exit surface; the minimum over all samples
    is a conservative (lower-bound-ish) estimate of the wall thickness.
    """
    points, face_idx = trimesh.sample.sample_surface(mesh, samples, seed=seed)
    normals = mesh.face_normals[face_idx]
    origins = points - normals * 1e-4
    from trimesh.ray.ray_triangle import RayMeshIntersector
    rmi = RayMeshIntersector(mesh)
    hits = rmi.intersects_any(origins, -normals)
    if not np.any(hits):
        return float("inf")
    locations, ray_idx, _ = rmi.intersects_location(
        origins[hits], -normals[hits], multiple_hits=False)
    if len(locations) == 0:
        return float("inf")
    d = np.linalg.norm(locations - origins[hits][ray_idx], axis=1)
    return float(d[d > 1e-3].min())


def check_features(part, cylinders):
    """Spec-specific feature rules. Returns (ok, details)."""
    details = {"cylindrical_faces": len(cylinders),
               "radii": sorted(round(r, 4) for r, _, _ in cylinders)}

    def count(radius):
        return sum(1 for r, _, _ in cylinders if abs(r - radius) <= RADIUS_TOL)

    if part == "bushing":
        want = {10.0: 1, 18.0: 1, 30.0: 1}
        ok = all(count(r) >= n for r, n in want.items())
        ok = ok and len(cylinders) == sum(want.values())
        details["want_radii"] = {str(r): n for r, n in want.items()}
        for r, axis, _ in cylinders:
            if abs(abs(axis[2]) - 1.0) > 1e-6:
                ok, details["axis_error"] = False, list(axis)
        return ok, details

    if part == "plate":
        holes = [(r, p) for r, axis, p in cylinders
                 if abs(r - 2.75) <= RADIUS_TOL]
        bore = count(15.0)
        details["bolt_holes_found"] = len(holes)
        details["bore_faces_R15"] = bore
        ok = bore == 1 and len(holes) == 6
        angles = []
        for r, (px, py, _) in holes:
            rho = math.hypot(px, py)
            ang = math.degrees(math.atan2(py, px)) % 360.0
            angles.append((round(rho, 4), round(ang, 3)))
            if abs(rho - 35.0) > BBOX_TOL:
                ok = False
        details["hole_positions"] = sorted(angles)
        # every hole must sit within ANGLE_TOL of some multiple of 60 degrees
        for _, ang in angles:
            if min(abs(ang - k * 60.0) for k in range(6)) > ANGLE_TOL:
                ok = False
        return ok, details

    if part == "bracket":
        details["faces_R5"] = count(5.0)
        details["faces_R6"] = count(6.0)
        details["faces_R8_fillet"] = count(8.0)
        ok = (count(5.0) == 2 and count(6.0) == 2 and count(8.0) == 1)
        for r, axis, p in cylinders:
            if abs(r - 8.0) <= RADIUS_TOL:
                # fillet cylinder axis runs along +Y at x=62, z=18
                if not (abs(abs(axis[1]) - 1.0) < 1e-6
                        and abs(p[0] - 62.0) <= BBOX_TOL
                        and abs(p[2] - 18.0) <= BBOX_TOL):
                    ok, details["fillet_axis_error"] = False, list(p)
        return ok, details

    raise ValueError(part)


def check_dxf(path):
    doc = ezdxf.readfile(path)
    audit = doc.audit()
    msp = doc.modelspace()
    circles = msp.query("CIRCLE")
    details = {"audit_errors": len(audit.errors), "circles": len(circles)}
    ok = len(audit.errors) == 0 and len(circles) == 7
    bolt = sorted(
        (round(c.dxf.radius, 4),
         round(math.hypot(c.dxf.center.x, c.dxf.center.y), 4),
         round(math.degrees(math.atan2(c.dxf.center.y, c.dxf.center.x)) % 360.0, 3))
        for c in circles if abs(c.dxf.radius - 2.75) <= RADIUS_TOL)
    details["bolt_circles_rho_angle"] = bolt
    ok = ok and len(bolt) == 6
    for r, rho, ang in bolt:
        if abs(rho - 35.0) > BBOX_TOL or \
                min(abs(ang - k * 60.0) for k in range(6)) > ANGLE_TOL:
            ok = False
    bore = [c for c in circles if abs(c.dxf.radius - 15.0) <= RADIUS_TOL]
    ok = ok and len(bore) == 1 and abs(bore[0].dxf.center.x) < BBOX_TOL \
        and abs(bore[0].dxf.center.y) < BBOX_TOL
    lines = list(msp.query("LINE"))
    polys = list(msp.query("LWPOLYLINE"))
    xs, ys = [], []
    for ln in lines:
        for pt in (ln.dxf.start, ln.dxf.end):
            xs.append(pt[0])
            ys.append(pt[1])
    for poly in polys:
        for pt in poly.get_points():
            xs.append(pt[0])
            ys.append(pt[1])
    if xs:
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        cx, cy = (max(xs) + min(xs)) / 2.0, (max(ys) + min(ys)) / 2.0
        details["outline"] = {"w": round(w, 4), "h": round(h, 4),
                              "cx": round(cx, 4), "cy": round(cy, 4)}
        ok = ok and abs(w - 100.0) <= BBOX_TOL and abs(h - 80.0) <= BBOX_TOL \
            and abs(cx) <= BBOX_TOL and abs(cy) <= BBOX_TOL
    else:
        ok = False
        details["outline"] = None
    return ok, details


def grade(artifact_dir, seed):
    t0 = time.time()
    verdict = {"artifact": os.path.abspath(artifact_dir), "gates": {},
               "all_pass": False}
    steps = os.listdir(artifact_dir) if os.path.isdir(artifact_dir) else []
    steps = [f[:-5] for f in steps if f.endswith(".step")]
    verdict["artifact_files"] = sorted(steps)
    if len(steps) != 1 or steps[0] not in ("bushing", "plate", "bracket"):
        verdict["gates"]["files"] = {
            "pass": False,
            "error": "artifact must contain exactly one of bushing.step, "
                     "plate.step, bracket.step (found: %s)" % sorted(steps)}
        return verdict
    part = steps[0]
    verdict["part"] = part

    def gate(name, fn):
        t = time.time()
        try:
            verdict["gates"][name] = fn()
        except Exception as e:
            verdict["gates"][name] = {"pass": False, "error": "%s: %s" % (type(e).__name__, e)}
        verdict["gates"][name]["_s"] = round(time.time() - t, 3)

    step_path = os.path.join(artifact_dir, part + ".step")
    stl_path = os.path.join(artifact_dir, part + ".stl")

    def g_files():
        need = [step_path, stl_path] + ([os.path.join(artifact_dir, "plate.dxf")]
                                        if part == "plate" else [])
        missing = [p for p in need if not os.path.isfile(p)]
        return {"pass": not missing, "missing": missing}

    shape_state = {}

    def g_brep():
        shape = cq.importers.importStep(step_path).val()
        solids = shape.Solids()
        analyzer = BRepCheck_Analyzer(shape.wrapped)
        valid = analyzer.IsValid()
        vol = occ_volume(shape)
        shape_state["shape"] = shape
        shape_state["volume"] = vol
        va = analytic_volume(part)
        rel = abs(vol - va) / va
        return {"pass": len(solids) == 1 and valid and rel <= VOLUME_TOL,
                "solids": len(solids), "brepcheck_valid": bool(valid),
                "volume_mm3": round(vol, 4), "analytic_mm3": round(va, 4),
                "rel_error": round(rel, 6), "tolerance": VOLUME_TOL}

    def g_bbox():
        bb = shape_state["shape"].BoundingBox()
        ext = (bb.xlen, bb.ylen, bb.zlen)
        want = spec_bbox(part)
        err = max(abs(a - b) for a, b in zip(ext, want))
        return {"pass": err <= BBOX_TOL,
                "measured": [round(e, 4) for e in ext],
                "spec": list(want), "max_axis_error_mm": round(err, 5),
                "tolerance_mm": BBOX_TOL}

    def g_stl():
        mesh = trimesh.load(stl_path, force="mesh")
        shape_state["mesh"] = mesh
        watertight = bool(mesh.is_watertight)
        winding = bool(mesh.is_winding_consistent)
        va = analytic_volume(part)
        rel = abs(mesh.volume - va) / va
        return {"pass": watertight and winding and rel <= VOLUME_TOL,
                "watertight": watertight, "winding_consistent": winding,
                "stl_volume_mm3": round(float(mesh.volume), 4),
                "analytic_mm3": round(va, 4),
                "rel_error": round(rel, 6), "tolerance": VOLUME_TOL,
                "faces": int(len(mesh.faces))}

    def g_xor():
        ref = tessellate(reference_solid(part).val())
        xor = xor_volume(shape_state["mesh"], ref)
        vref = ref.volume
        return {"pass": xor <= XOR_FRAC * vref,
                "xor_mm3": round(xor, 4), "reference_mm3": round(float(vref), 4),
                "xor_fraction": round(xor / vref, 6),
                "tolerance_fraction": XOR_FRAC}

    def g_features():
        ok, details = check_features(part, cylindrical_faces(shape_state["shape"]))
        return dict({"pass": ok}, **details)

    def g_min_wall():
        t = min_wall_thickness(shape_state["mesh"], seed)
        return {"pass": t >= MIN_WALL, "measured_min_mm": round(t, 4),
                "limit_mm": MIN_WALL, "spec_min_mm": 1.5,
                "samples": 2400, "seed": seed}

    def g_dxf():
        ok, details = check_dxf(os.path.join(artifact_dir, "plate.dxf"))
        return dict({"pass": ok}, **details)

    gate("files", g_files)
    gate("brep", g_brep)
    gate("bbox", g_bbox)
    gate("stl_topology", g_stl)
    gate("xor_reference", g_xor)
    gate("features", g_features)
    gate("min_wall", g_min_wall)
    if part == "plate":
        gate("dxf", g_dxf)

    verdict["all_pass"] = all(g["pass"] for g in verdict["gates"].values())
    verdict["timing"] = {"grade_wall_s": round(time.time() - t0, 3)}
    return verdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("artifact", help="artifact directory (delivered files)")
    ap.add_argument("--seed", type=int, default=20261015)
    ap.add_argument("--json", default=None, help="also write verdict JSON here")
    args = ap.parse_args()
    verdict = grade(args.artifact, args.seed)

    def default(o):
        import numpy as _np
        if isinstance(o, (_np.bool_,)):
            return bool(o)
        if isinstance(o, _np.integer):
            return int(o)
        if isinstance(o, _np.floating):
            return float(o)
        raise TypeError(o)

    text = json.dumps(verdict, sort_keys=True, indent=2, default=default)
    print(text)
    if args.json:
        with open(args.json, "w") as f:
            f.write(text + "\n")
    return 0 if verdict["all_pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
