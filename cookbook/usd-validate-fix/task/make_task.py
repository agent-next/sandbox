#!/usr/bin/env python3
"""Generate the traffic-cone task assets with pxr (usd-core only).

Writes, relative to this script's parent directory:
  task/traffic_cone_broken.usda   the broken input the agent must repair
  ../examples/good/traffic_cone_fixed.usda  the known-good artifact

Run inside the venv judge/setup.sh creates:
  judge/setup.sh --make-assets
or directly:  <venv-python> task/make_task.py

The asset is a 61 cm road traffic cone authored in CENTIMETRES (as if
exported from a cm-based DCC), so the correct stage metersPerUnit is
0.01.  The broken variant seeds the six defects listed in SPEC.md.
"""
import os
import sys

from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade

SEG = 10  # circle segment count; keeps every ASCII array <= 64 entries
          # (UsdAsciiPerformanceChecker flags usda arrays longer than 64)

ROOT = "/TrafficCone"


def add_material(stage, looks_path, name, color):
    mat = UsdShade.Material.Define(stage, looks_path.AppendChild(name))
    shader = UsdShade.Shader.Define(
        stage, mat.GetPath().AppendChild(name + "_shader"))
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(color)
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.45)
    mat.CreateSurfaceOutput().ConnectToSource(
        shader.ConnectableAPI(), "outputs:out")
    return mat


def mesh(stage, path, points, fvc, fvi, normals=None):
    m = UsdGeom.Mesh.Define(stage, path)
    m.CreatePointsAttr([Gf.Vec3f(*p) for p in points])
    m.CreateFaceVertexCountsAttr(fvc)
    m.CreateFaceVertexIndicesAttr(fvi)
    m.CreateSubdivisionSchemeAttr("none")
    if normals is not None:
        attr = m.CreateNormalsAttr([Gf.Vec3f(*n) for n in normals], True)
        attr.SetMetadata("interpolation", "faceVarying")
    return m


def cone_geometry():
    """Traffic cone, coordinates in cm -> {name: (points, fvc, fvi)}."""
    import math
    geoms = {}
    # ---- base: square frustum --------------------------------------
    hw0, hw1, h = 18.0, 14.0, 4.0
    pts = []
    for z, hw in ((0.0, hw0), (h, hw1)):
        for x, y in ((-hw, -hw), (hw, -hw), (hw, hw), (-hw, hw)):
            pts.append((x, y, z))
    fvi = [3, 2, 1, 0,
           4, 5, 6, 7,
           0, 1, 5, 4,
           1, 2, 6, 5,
           2, 3, 7, 6,
           3, 0, 4, 7]
    geoms["Base"] = (pts, [4] * 6, fvi)

    # ---- body: cone frustum -----------------------------------------
    r0, r1, z0, z1 = 13.0, 7.5, 4.0, 58.0
    pts = []
    for z, r in ((z0, r0), (z1, r1)):
        for i in range(SEG):
            a = 2.0 * math.pi * i / SEG
            pts.append((r * math.cos(a), r * math.sin(a), z))
    fvi = list(range(SEG - 1, -1, -1))      # bottom cap, outward -Z
    fvi += list(range(SEG, 2 * SEG))        # top cap, outward +Z
    for i in range(SEG):                    # side quads
        a0, a1 = i, (i + 1) % SEG
        fvi += [a0, a1, SEG + a1, SEG + a0]
    geoms["Body"] = (pts, [SEG, SEG] + [4] * SEG, fvi)

    # ---- band: closed frustum ring ----------------------------------
    rb0, rb1, zb0, zb1 = 13.8, 9.0, 30.0, 44.0
    pts = []
    for z, r in ((zb0, rb0), (zb1, rb1)):
        for i in range(SEG):
            a = 2.0 * math.pi * i / SEG
            pts.append((r * math.cos(a), r * math.sin(a), z))
    fvi = []
    for i in range(SEG):
        a0, a1 = i, (i + 1) % SEG
        fvi += [a0, a1, SEG + a1, SEG + a0]
    geoms["Band"] = (pts, [4] * SEG, fvi)
    return geoms


def face_normals(points, fvc, fvi):
    """Flat face normals per face-corner (faceVarying), Newell's method."""
    normals = []
    k = 0
    for count in fvc:
        idx = fvi[k:k + count]
        nx = ny = nz = 0.0
        for j in range(count):
            cur, nxt = points[idx[j]], points[idx[(j + 1) % count]]
            nx += (cur[1] - nxt[1]) * (cur[2] + nxt[2])
            ny += (cur[2] - nxt[2]) * (cur[0] + nxt[0])
            nz += (cur[0] - nxt[0]) * (cur[1] + nxt[1])
        ln = (nx * nx + ny * ny + nz * nz) ** 0.5
        normals += [(nx / ln, ny / ln, nz / ln)] * count
        k += count
    return normals


def bbox(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))


def build(stage, broken):
    xform = UsdGeom.Xform.Define(stage, ROOT)
    UsdGeom.Scope.Define(stage, ROOT + "/Looks")
    looks_path = Sdf.Path(ROOT + "/Looks")
    orange = add_material(stage, looks_path, "OrangePlastic",
                          Gf.Vec3f(0.87, 0.26, 0.03))
    white = add_material(stage, looks_path, "WhitePlastic",
                         Gf.Vec3f(0.93, 0.93, 0.93))

    geoms = cone_geometry()
    for name in ("Base", "Body", "Band"):
        points, fvc, fvi = geoms[name]
        if broken and name == "Band":
            # D3: degenerate zero-area quad (all four corners = vertex 0)
            fvc = fvc + [4]
            fvi = fvi + [0, 0, 0, 0]
        m = mesh(stage, f"{ROOT}/{name}", points, fvc, fvi,
                 normals=None if broken else face_normals(points, fvc, fvi))
        if not broken:
            lo, hi = bbox(points)
            m.CreateExtentAttr([Gf.Vec3f(*lo), Gf.Vec3f(*hi)], True)
        if not (broken and name == "Band"):   # D4: Band left unbound
            prim = m.GetPrim()
            UsdShade.MaterialBindingAPI.Apply(prim)
            UsdShade.MaterialBindingAPI(prim).Bind(
                orange if name != "Band" else white)

    # physics collider on the body mesh
    UsdPhysics.CollisionAPI.Apply(stage.GetPrimAtPath(ROOT + "/Body"))

    # stage metadata
    stage.SetDefaultPrim(xform.GetPrim())
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.y)
    UsdGeom.SetStageMetersPerUnit(stage, 0.01)  # centimetres
    if broken:
        # D2: wrong linear unit (asset is authored in cm) and wrong up axis
        UsdGeom.SetStageMetersPerUnit(stage, 1.0)
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        # D5: missing defaultPrim
        stage.GetRootLayer().ClearDefaultPrim()


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    base = os.path.dirname(here)
    for rel, broken in (
            ("task/traffic_cone_broken.usda", True),
            ("examples/good/traffic_cone_fixed.usda", False)):
        path = os.path.join(base, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        stage = Usd.Stage.CreateInMemory()
        build(stage, broken)
        stage.GetRootLayer().Export(path)
        print("wrote", os.path.relpath(path, base))
    return 0


if __name__ == "__main__":
    sys.exit(main())
