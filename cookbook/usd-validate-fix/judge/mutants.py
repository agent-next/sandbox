#!/usr/bin/env python3
"""Generate the known-bad mutants for the usd-validate-fix self-test.

Each mutant is a single semantic edit of examples/good/traffic_cone_fixed
.usda, applied with usd-core (pxr) and re-exported as ASCII, so the edits
survive any formatting change of the good asset:

  no_normals       D1  strip the authored normals from every mesh
  mpu_1            D2a metersPerUnit = 1 (asset is authored in cm)
  upaxis_z         D2b upAxis = "Z"
  zero_face        D3  append a degenerate zero-area quad to the Band
  unbind           D4  remove the Band's material binding
  no_defaultprim   D5  clear defaultPrim
  no_extent        D6  strip the authored extents from every mesh
  delete_band          delete the offending prim instead of fixing it
  scale_points         scale all points by 100 and set metersPerUnit = 1
                       ("fix" the unit error by moving geometry)
  short_normals        drop one normal (count no longer matches topology)
  no_collision         strip the physics collider

Usage (run with the venv python, needs pxr):
  python -I judge/mutants.py <good.usda> <outdir>
"""
from __future__ import annotations

import os
import sys

from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade

BAND = "/TrafficCone/Band"
BODY = "/TrafficCone/Body"


def meshes(stage):
    return [p for p in stage.Traverse() if p.IsA(UsdGeom.Mesh)]


def edit_no_normals(stage):
    for p in meshes(stage):
        UsdGeom.Mesh(p).GetNormalsAttr().Clear()


def edit_mpu_1(stage):
    stage.GetRootLayer().pseudoRoot.SetInfo("metersPerUnit", 1.0)


def edit_upaxis_z(stage):
    stage.GetRootLayer().pseudoRoot.SetInfo("upAxis", "Z")


def edit_zero_face(stage):
    mesh = UsdGeom.Mesh(stage.GetPrimAtPath(BAND))
    counts = list(mesh.GetFaceVertexCountsAttr().Get())
    indices = list(mesh.GetFaceVertexIndicesAttr().Get())
    mesh.CreateFaceVertexCountsAttr(counts + [4], True)
    mesh.CreateFaceVertexIndicesAttr(indices + [0, 0, 0, 0], True)


def edit_unbind(stage):
    prim = stage.GetPrimAtPath(BAND)
    prim.GetRelationship("material:binding").ClearTargets(True)


def edit_no_defaultprim(stage):
    stage.GetRootLayer().ClearDefaultPrim()


def edit_no_extent(stage):
    for p in meshes(stage):
        UsdGeom.Mesh(p).GetExtentAttr().Clear()


def edit_delete_band(stage):
    stage.RemovePrim(Sdf.Path(BAND))


def edit_scale_points(stage):
    for p in meshes(stage):
        mesh = UsdGeom.Mesh(p)
        pts = [Gf.Vec3f(*[100.0 * c for c in v])
               for v in (mesh.GetPointsAttr().Get() or [])]
        mesh.CreatePointsAttr(pts, True)
        mesh.GetExtentAttr().Clear()          # a scale of 100 invalidates it
    stage.GetRootLayer().pseudoRoot.SetInfo("metersPerUnit", 1.0)


def edit_short_normals(stage):
    prim = stage.GetPrimAtPath(BAND)
    if not prim.IsValid():
        raise RuntimeError("good asset has no Band mesh")
    mesh = UsdGeom.Mesh(prim)
    normals = list(mesh.GetNormalsAttr().Get() or [])
    if not normals:
        raise RuntimeError("good asset has no Band normals to drop")
    mesh.CreateNormalsAttr(normals[:-1], True)


def edit_no_collision(stage):
    UsdPhysics.CollisionAPI(
        stage.GetPrimAtPath(BODY)).GetPrim().RemoveAPI(
            UsdPhysics.CollisionAPI)


MUTANTS = [
    ("no_normals", edit_no_normals),
    ("mpu_1", edit_mpu_1),
    ("upaxis_z", edit_upaxis_z),
    ("zero_face", edit_zero_face),
    ("unbind", edit_unbind),
    ("no_defaultprim", edit_no_defaultprim),
    ("no_extent", edit_no_extent),
    ("delete_band", edit_delete_band),
    ("scale_points", edit_scale_points),
    ("short_normals", edit_short_normals),
    ("no_collision", edit_no_collision),
]


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: mutants.py <good.usda> <outdir>", file=sys.stderr)
        return 2
    good, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    for name, edit in MUTANTS:
        # A fresh anonymous layer per mutant: Stage.Open caches the root
        # layer in the Sdf registry, so re-opening the good file would
        # accumulate edits across iterations.
        layer = Sdf.Layer.CreateAnonymous("mutant-%s.usda" % name)
        layer.Import(good)
        stage = Usd.Stage.Open(layer)
        if stage is None:
            print("mutants: cannot open %s" % good, file=sys.stderr)
            return 1
        edit(stage)
        path = os.path.join(outdir, "%s.usda" % name)
        stage.GetRootLayer().Export(path)
        print("mutants: wrote %s (%s)" % (path, name))
    print("mutants: %d mutants" % len(MUTANTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
