#!/usr/bin/env python3
"""Grade one delivered artifact against its spec (see SPEC.md).

Usage: check_gates.py <artifact_dir> [--seed N] [--json out.json]

Every gate is numeric and every measurement comes from a pinned library:
trimesh (watertight/winding/bbox/volume), manifold3d (boolean XOR), OCP /
OCCT (STEP re-import, BRepCheck_Analyzer, B-rep volume, cylindrical and
planar faces), ezdxf (DXF audit + entity read).  Only the spec-specific
feature rules (bolt-circle angles, ligaments) are our own code.

Verdict JSON gates are rounded to 1e-3 so identical geometry gives
byte-identical JSON (OpenSCAD vertex ordering is not deterministic).
"""

import contextlib
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import trimesh
from manifold3d import Manifold, Mesh, OpType

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cases import CASES, reference_solid  # noqa: E402

OPENSCAD = os.environ.get("OPENSCAD", "openscad")
R = 3  # decimals for every reported/compared number


@contextlib.contextmanager
def _silence():
    """OCCT prints transfer chatter on fd 1 from C++; silence at fd level."""
    saved = os.dup(1)
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, 1)
        yield
    finally:
        os.dup2(saved, 1)
        os.close(devnull)
        os.close(saved)


def r3(x):
    return round(float(x), R)


class Gates:
    def __init__(self, case, seed):
        self.case = case
        self.spec = CASES[case]
        self.seed = seed
        self.results = []
        self.timing = {"total_s": 0.0}

    def add(self, name, passed, detail=None, **fields):
        entry = {"gate": name, "passed": bool(passed)}
        if detail is not None:
            entry["detail"] = detail
        for k, v in fields.items():
            if isinstance(v, list):
                entry[k] = [r3(x) for x in v]
            else:
                entry[k] = v if isinstance(v, (int, bool, str)) else r3(v)
        self.results.append(entry)

    @property
    def ok(self):
        return all(g["passed"] for g in self.results)


def to_manifold(tm):
    return Manifold(
        Mesh(
            vert_properties=np.asarray(tm.vertices, dtype=np.float32),
            tri_verts=np.asarray(tm.faces, dtype=np.uint32),
        )
    )


def xor_volume(a, b):
    """Symmetric-difference volume via manifold3d booleans:
    (A - B) union (B - A).  manifold3d 3.0.1 has no XOR OpType, so the
    symmetric difference is composed from Subtract + Add."""
    amb = Manifold.batch_boolean([a, b], OpType.Subtract)
    bma = Manifold.batch_boolean([b, a], OpType.Subtract)
    both = Manifold.batch_boolean([amb, bma], OpType.Add)
    return float(both.volume())


# ---------------------------------------------------------------- OCP helpers
def occt_mesh_arrays(shape, linear_deflection=0.01, angular_deflection=0.05):
    """Tessellate an OCCT shape -> (vertices float64 Nx3, faces int Mx3)."""
    with _silence():
        from OCP.BRepMesh import BRepMesh_IncrementalMesh
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopoDS import TopoDS
        from OCP.BRep import BRep_Tool
        from OCP.TopLoc import TopLoc_Location

        BRepMesh_IncrementalMesh(
            shape, linear_deflection, False, angular_deflection, True
        )
        from OCP.TopAbs import TopAbs_REVERSED

        raw_tris = []
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        while exp.More():
            face = TopoDS.Face_s(exp.Current())
            loc = TopLoc_Location()
            tri = BRep_Tool.Triangulation_s(face, loc)
            if tri is None:
                exp.Next()
                continue
            trsf = loc.Transformation()
            pts = []
            for i in range(1, tri.NbNodes() + 1):
                p = tri.Node(i).Transformed(trsf)
                pts.append((p.X(), p.Y(), p.Z()))
            rev = face.Orientation() == TopAbs_REVERSED
            for i in range(1, tri.NbTriangles() + 1):
                a, b, c = tri.Triangle(i).Get()
                raw_tris.append(
                    [pts[a - 1], pts[c - 1], pts[b - 1]]
                    if rev else [pts[a - 1], pts[b - 1], pts[c - 1]]
                )
            exp.Next()
    tris = np.array(raw_tris, dtype=np.float64)
    flat = tris.reshape(-1, 3)
    uniq, inv = np.unique(flat, axis=0, return_inverse=True)
    faces = inv.reshape(-1, 3).astype(np.uint32)
    return uniq, faces


def step_reimport(path):
    with _silence():
        from OCP.STEPControl import STEPControl_Reader
        from OCP.BRepCheck import BRepCheck_Analyzer
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopoDS import TopoDS
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.BRep import BRep_Tool
        from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane

        reader = STEPControl_Reader()
        reader.ReadFile(str(path))
        reader.TransferRoots()
        shape = reader.OneShape()
        # mesh so planar faces get vertex bboxes for the min-wall gate
        from OCP.BRepMesh import BRepMesh_IncrementalMesh

        BRepMesh_IncrementalMesh(shape, 0.05, False, 0.1, True)
        valid = BRepCheck_Analyzer(shape).IsValid()
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(shape, props)
        volume = props.Mass()

        cylinders, planes = [], []
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        while exp.More():
            face = TopoDS.Face_s(exp.Current())
            ad = BRepAdaptor_Surface(face)
            kind = ad.GetType()
            if kind == GeomAbs_Cylinder:
                cyl = ad.Cylinder()
                loc = cyl.Axis().Location()
                dirv = cyl.Axis().Direction()
                cylinders.append(
                    dict(radius=cyl.Radius(),
                         axis=(dirv.X(), dirv.Y(), dirv.Z()),
                         at=(loc.X(), loc.Y(), loc.Z()))
                )
            elif kind == GeomAbs_Plane:
                pl = ad.Plane()
                n = pl.Axis().Direction()
                p = pl.Location()
                # vertex bbox of this face, aligned with the planes list
                from OCP.TopLoc import TopLoc_Location

                loc2 = TopLoc_Location()
                tri = BRep_Tool.Triangulation_s(face, loc2)
                if tri is None:
                    bbox = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
                else:
                    pts = []
                    trsf = loc2.Transformation()
                    for i in range(1, tri.NbNodes() + 1):
                        q = tri.Node(i).Transformed(trsf)
                        pts.append([q.X(), q.Y(), q.Z()])
                    pts = np.array(pts)
                    bbox = (tuple(pts.min(axis=0)), tuple(pts.max(axis=0)))
                planes.append(
                    dict(normal=(n.X(), n.Y(), n.Z()),
                         point=(p.X(), p.Y(), p.Z()),
                         bbox=bbox)
                )
            exp.Next()
    return dict(shape=shape, valid=valid, volume=volume,
                cylinders=cylinders, planes=planes)


def planar_min_wall(planes):
    """Min distance between anti-parallel planar faces whose footprints
    overlap (a proxy for local wall thickness). Spec-specific tolerances
    live in SPEC.md; the measurement itself is plane geometry from OCCT."""
    best = math.inf
    for i in range(len(planes)):
        for j in range(i + 1, len(planes)):
            ni = np.array(planes[i]["normal"])
            nj = np.array(planes[j]["normal"])
            if np.dot(ni, nj) > -0.999:
                continue
            if not _boxes_overlap(planes[i]["bbox"], planes[j]["bbox"]):
                continue
            pi = np.array(planes[i]["point"])
            pj = np.array(planes[j]["point"])
            d = abs(float(np.dot(ni, pj - pi)))
            best = min(best, d)
    return best


def _boxes_overlap(bi, bj, margin=0.5):
    lo_i = np.array(bi[0]) + margin
    hi_i = np.array(bi[1]) - margin
    lo_j = np.array(bj[0]) + margin
    hi_j = np.array(bj[1]) - margin
    return bool(np.all(lo_i < hi_j) and np.all(lo_j < hi_i))


# ----------------------------------------------------------------- DXF gates
def dxf_loops(path):
    """Read a DXF written by OpenSCAD (LINE entities), chain them into
    closed loops, and fit circles where a loop is round.  ezdxf does the
    audit and entity read; the chaining/fitting rule is spec code."""
    import ezdxf

    doc = ezdxf.readfile(str(path))
    audit = doc.audit()
    n_errors = len(audit.errors)
    msp = doc.modelspace()
    lines = list(msp.query("LINE"))
    adj = {}
    for e in lines:
        a = (round(e.dxf.start.x, 6), round(e.dxf.start.y, 6))
        b = (round(e.dxf.end.x, 6), round(e.dxf.end.y, 6))
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    loops, seen = [], set()
    for start in adj:
        if start in seen:
            continue
        loop, prev, cur = [start], None, start
        seen.add(start)
        while True:
            nxt = [p for p in adj.get(cur, []) if p != prev]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            if cur == start or cur in seen:
                break
            loop.append(cur)
            seen.add(cur)
        loops.append(loop)
    fits = []
    for loop in loops:
        v = np.array(loop)
        c = v.mean(axis=0)
        r = np.linalg.norm(v - c, axis=1)
        if len(loop) >= 8 and r.std() < 0.02 * max(r.mean(), 1e-9):
            fits.append(dict(kind="circle", center=(c[0], c[1]),
                             radius=float(r.mean()), n=len(loop)))
        else:
            fits.append(dict(kind="polyline", n=len(loop),
                             bbox=(v.min(axis=0), v.max(axis=0))))
    return dict(audit_errors=n_errors, n_lines=len(lines), loops=fits)


# ------------------------------------------------------------------- grading
def grade(artifact: Path, seed: int):
    case = json.loads((artifact / "case.json").read_text())["case"]
    spec = CASES[case]
    g = Gates(case, seed)
    t0 = time.time()

    scratch = Path(tempfile.mkdtemp(prefix="aicad-"))
    work = scratch / "a"
    shutil.copytree(artifact, work)
    try:
        # -- the tool run: pinned OpenSCAD re-exports from the shipped source
        reexport = scratch / "reexport.stl"
        with _silence():
            rc = subprocess.run(
                [OPENSCAD, "-o", str(reexport), str(work / "part.scad")],
                capture_output=True, text=True)
        if rc.returncode != 0 or not reexport.exists():
            g.add("scad_export", False, "openscad failed: " + rc.stderr[-300:])
            return verdict(g, t0)
        g.add("scad_export", True, "openscad 2021.01 exit 0")

        stl = trimesh.load(str(work / "part.stl"))
        re_stl = trimesh.load(str(reexport))

        # 2: shipped STL must match what the shipped source produces
        x = xor_volume(to_manifold(stl), to_manifold(re_stl))
        g.add("stl_matches_scad",
              x <= 0.001 * spec["volume_analytic"],
              measured_mm3=x, limit_mm3=0.001 * spec["volume_analytic"])

        # 3-6: mesh quality against the analytic spec
        g.add("stl_watertight", bool(stl.is_watertight))
        g.add("stl_winding", bool(stl.is_winding_consistent))

        lo_e, hi_e = spec["bbox_expect"]
        lo_e, hi_e = np.array(lo_e), np.array(hi_e)
        dev = float(np.max(np.abs(np.array(stl.bounds) - np.array([lo_e, hi_e]))))
        g.add("bbox", dev <= 0.05, measured_max_dev_mm=dev, limit_mm=0.05)

        v_stl = float(stl.volume)
        rel = abs(v_stl - spec["volume_analytic"]) / spec["volume_analytic"]
        g.add("volume_stl", rel <= 0.005, measured_mm3=v_stl,
              analytic_mm3=spec["volume_analytic"], rel=rel, limit=0.005)

        # 7: XOR against the judge-built OCCT reference solid
        ref = reference_solid(case)
        rv, rf = occt_mesh_arrays(ref)
        ref_tm = trimesh.Trimesh(vertices=rv, faces=rf)
        v_ref = float(ref_tm.volume)
        # oracle sanity: the reference itself must match the analytic volume
        ref_rel = abs(v_ref - spec["volume_analytic"]) / spec["volume_analytic"]
        if ref_rel > 0.001:
            raise RuntimeError(
                f"judge reference solid disagrees with analytic volume "
                f"({ref_rel:.5f}); refusing to grade")
        xref = xor_volume(to_manifold(stl), to_manifold(ref_tm))
        g.add("xor_reference", xref <= 0.01 * v_ref,
              measured_mm3=xref, limit_mm3=0.01 * v_ref, ref_volume_mm3=v_ref)

        # 8-11: the delivered STEP B-rep
        info = step_reimport(work / "part.step")
        g.add("step_reimport", bool(info["valid"]),
              detail="BRepCheck_Analyzer on re-imported STEP")
        v_step = float(info["volume"])
        rel_s = abs(v_step - spec["volume_analytic"]) / spec["volume_analytic"]
        rel_x = abs(v_step - v_stl) / v_stl
        g.add("volume_step", rel_s <= 0.005 and rel_x <= 0.01,
              measured_mm3=v_step, rel_vs_analytic=rel_s,
              rel_vs_stl=rel_x, limit_analytic=0.005, limit_stl=0.01)

        radii = sorted(c["radius"] for c in info["cylinders"])
        want, tol = spec["cyl_faces_expect"]
        ok_faces = len(radii) == len(want) and all(
            abs(a - b) <= tol for a, b in zip(sorted(radii), want))
        g.add("cyl_faces", ok_faces, measured_radii=sorted(radii),
              expected_radii=want, tol_mm=tol)

        # 11: minimum wall between anti-parallel planar faces
        mw = planar_min_wall(info["planes"])
        g.add("planar_min_wall", mw >= spec["min_wall"],
              measured_mm=mw, limit_mm=spec["min_wall"])

        # 12: spec-specific feature rules (our own code on library results)
        case_feature_gates(g, spec, info)

        # 13-14: DXF drawing (plate only)
        if "bolt" in spec:
            redxf = scratch / "reexport.dxf"
            with _silence():
                rc = subprocess.run(
                    [OPENSCAD, "-o", str(redxf), str(work / "drawing.scad")],
                    capture_output=True, text=True)
            if rc.returncode != 0 or not redxf.exists():
                g.add("dxf_valid", False, "openscad dxf export failed")
            else:
                reg = dxf_loops(redxf)
                ship = dxf_loops(work / "drawing.dxf")
                same = (
                    ship["audit_errors"] == 0
                    and ship["n_lines"] == reg["n_lines"]
                    and len(ship["loops"]) == len(reg["loops"])
                    and all(
                        a["kind"] == b["kind"]
                        and (
                            a["kind"] == "polyline"
                            or (abs(a["radius"] - b["radius"]) <= 0.05
                                and np.allclose(a["center"], b["center"],
                                                atol=0.05))
                        )
                        for a, b in zip(sorted_loops(ship), sorted_loops(reg))
                    )
                )
                g.add("dxf_valid", bool(same),
                      audit_errors=ship["audit_errors"],
                      shipped_lines=ship["n_lines"],
                      regenerated_lines=reg["n_lines"])
                dxf_feature_gates(g, spec, reg)
        return verdict(g, t0)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def sorted_loops(d):
    def key(f):
        if f["kind"] == "circle":
            return (0, round(f["center"][0], 3), round(f["center"][1], 3))
        return (1,)
    return sorted(d["loops"], key=key)


def case_feature_gates(g, spec, info):
    """Spec-specific rules from measured STEP features (SPEC.md gate 12)."""
    if spec["name"] == "bushing":
        radii = sorted(c["radius"] for c in info["cylinders"])
        wall = radii[1] - radii[0]  # r_body(15) - r_bore(6) after sorting
        g.add("case_features", wall >= spec["min_wall"],
              detail="radial wall = r_body - r_bore",
              measured_mm=wall, limit_mm=spec["min_wall"])
    elif spec["name"] == "plate":
        bolts = [c for c in info["cylinders"] if abs(c["radius"] - 3.0) < 0.5]
        cx, cy = spec["bolt"]["center"]
        d = sorted(
            math.hypot(c["at"][0] - cx, c["at"][1] - cy) for c in bolts
        )
        ok_count = len(bolts) == spec["bolt"]["count"]
        ok_radius = all(
            abs(x - spec["bolt"]["circle_r"]) <= 0.05 for x in d
        )
        angs = sorted(
            math.degrees(math.atan2(c["at"][1] - cy, c["at"][0] - cx)) % 360
            for c in bolts
        )
        gaps = [(b - a) % 360 for a, b in zip(angs, angs[1:] + [angs[0] + 360])]
        ok_spacing = all(
            abs(gp - spec["bolt"]["spacing_deg"]) <= 0.05 for gp in gaps
        ) if ok_count else False
        # ligament rules: bore-to-hole, hole-to-nearest-edge
        lig_bore = min(d) - 3.0 - 10.0
        lig_edge = 30.0 - max(d) - 3.0  # half of the 60 mm side
        g.add("case_features",
              ok_count and ok_radius and ok_spacing
              and lig_bore >= spec["min_wall"] and lig_edge >= spec["min_wall"],
              bolt_count=len(bolts), bolt_circle_r=d,
              spacing_deg=gaps, bore_ligament_mm=lig_bore,
              edge_ligament_mm=lig_edge, limit_mm=spec["min_wall"])
    else:  # bracket: both fillet radii present (already in cyl_faces)
        g.add("case_features", True,
              detail="bracket fillets covered by cyl_faces radii")


def dxf_feature_gates(g, spec, reg):
    circles = [f for f in reg["loops"] if f["kind"] == "circle"]
    polys = [f for f in reg["loops"] if f["kind"] == "polyline"]
    cx, cy = spec["bolt"]["center"]
    holes = [c for c in circles if abs(c["radius"] - 3.0) <= 0.5]
    bore = [c for c in circles if abs(c["radius"] - 10.0) <= 0.5]
    ok_count = len(holes) == spec["bolt"]["count"] and len(bore) == 1
    d = sorted(math.hypot(c["center"][0] - cx, c["center"][1] - cy)
               for c in holes)
    ok_radius = all(abs(x - 24.0) <= 0.05 for x in d)
    ok_radii = all(abs(c["radius"] - 3.0) <= 0.05 for c in holes)
    angs = sorted(
        math.degrees(math.atan2(c["center"][1] - cy, c["center"][0] - cx)) % 360
        for c in holes
    )
    gaps = [(b - a) % 360 for a, b in zip(angs, angs[1:] + [angs[0] + 360])]
    ok_spacing = (len(gaps) == 6 and all(abs(gp - 60.0) <= 0.05 for gp in gaps))
    ok_outline = False
    if polys:
        lo, hi = polys[0]["bbox"]
        ok_outline = (abs((hi[0] - lo[0]) - 80.0) <= 0.05
                      and abs((hi[1] - lo[1]) - 60.0) <= 0.05)
    g.add("dxf_features",
          bool(ok_count and ok_radius and ok_radii and ok_spacing and ok_outline),
          hole_count=len(holes), bore_count=len(bore),
          bolt_circle_r=d, hole_radii=[c["radius"] for c in holes],
          spacing_deg=gaps)


def verdict(g, t0):
    g.timing["total_s"] = r3(time.time() - t0)
    out = dict(case=g.case, seed=g.seed, passed=g.ok,
               gates=g.results, timing=g.timing)
    return out


def main():
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("artifact")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json")
    args = ap.parse_args()
    v = grade(Path(args.artifact), args.seed)
    text = json.dumps(v, indent=1, sort_keys=True)
    if args.json:
        Path(args.json).write_text(text + "\n")
    print(text)
    sys.exit(0 if v["passed"] else 1)


if __name__ == "__main__":
    main()
