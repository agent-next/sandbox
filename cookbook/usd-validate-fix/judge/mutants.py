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
  sublayer_cheat       write no geometry at all: an empty root layer that
                       borrows the good asset through subLayers = @abs path@.
                       pxr composes it, so the validator and the pxr oracle
                       see the good stage -- only the clean-room text
                       recount (which reads the artifact's own layer) sees
                       the cheat.
  xform_scale          wrap the good asset in a xformOp:scale = (100, 100,
                       100) on /TrafficCone: the authored points are
                       untouched, so the old gate-3 points comparison could
                       not see it.  Killed by gate 3's world-bbox check and
                       gate 4's xformOp rejection.
  xform_rot            xformOp:translate (500, 0, 0) + rotateX 90 on
                       /TrafficCone: moves and tips the whole prop.  Killed
                       by gate 3 (world bbox) and gate 5 (height axis vs
                       upAxis).
  latin1_comment       one non-UTF-8 byte in a comment.  No gate can open
                       it, so every gate reports a named error in a verdict;
                       the self-test uses it to prove it does not count a
                       crash as a kill (it remains a kill, but only because
                       the verdict names a real gate and the errors).

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


def edit_xform_scale(stage):
    # A transform-only cheat: the authored points are untouched, but the root
    # Xform scales the whole prop by 100, so at metersPerUnit = 0.01 the
    # "repaired" cone is 5.8 m tall.  Killed by gate 3 (world bbox) and
    # gate 4 (the artifact authors an xformOp the original does not have).
    xform = UsdGeom.Xform.Define(stage, "/TrafficCone")
    xform.AddScaleOp().Set(Gf.Vec3f(100.0, 100.0, 100.0))


def edit_xform_rot(stage):
    # A transform-only cheat that also tips the cone over: translate 500 cm
    # and rotate 90 deg about X, so the height axis is no longer Y.  Killed
    # by gate 3 (world bbox moved and tipped) and gate 5 (height axis vs
    # upAxis) -- the authored points are either way identical.
    xform = UsdGeom.Xform.Define(stage, "/TrafficCone")
    xform.AddTranslateOp().Set(Gf.Vec3f(500.0, 0.0, 0.0))
    xform.AddRotateXOp().Set(90.0)


def edit_latin1_comment(stage):
    # A malformed artifact: one non-UTF-8 byte in a comment.  No USD stack
    # can open it, so every gate must report a named error in a verdict.
    # This is the control for the self-test's rule that a crash is not a
    # kill: it always fails the grade, but it must fail BY A NAMED GATE.
    return None            # the byte is added by the harness, after export


def edit_wrong_material(stage):
    # Bind the reflective Band to the orange plastic instead of the white:
    # a gate that only checks "some material is bound" lets this through.
    prim = stage.GetPrimAtPath(BAND)
    UsdShade.MaterialBindingAPI(prim).Bind(
        UsdShade.Material(stage.GetPrimAtPath("/TrafficCone/Looks/"
                                              "OrangePlastic")))


def edit_sublayer_cheat(stage):
    # Replace the entire root layer's contents with nothing but a subLayers
    # reference to the good asset's absolute path.  pxr follows the
    # reference, so gates 1-3 (validator + pxr oracle) see the complete
    # good stage; only the clean-room text recount sees the empty layer.
    good = os.path.abspath(os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "examples", "good", "traffic_cone_fixed.usda"))
    layer = stage.GetRootLayer()
    layer.rootPrims.clear()
    layer.subLayerPaths.append(good)


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
    ("sublayer_cheat", edit_sublayer_cheat),
    ("xform_scale", edit_xform_scale),
    ("xform_rot", edit_xform_rot),
    ("latin1_comment", edit_latin1_comment),
    ("wrong_material", edit_wrong_material),
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
        # latin1_comment needs a byte ASCII/USD tooling rejects; pxr's export
        # is UTF-8, so the corrupting byte is written after the export.
        if name in ("latin1_comment",):
            with open(path, "rb") as fh:
                blob = fh.read()
            blob = blob.replace(b"#usda 1.0\n", b"#usda 1.0\n# caf\xe9\n", 1)
            with open(path, "wb") as fh:
                fh.write(blob)
        print("mutants: wrote %s (%s)" % (path, name))
    print("mutants: %d mutants" % len(MUTANTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
