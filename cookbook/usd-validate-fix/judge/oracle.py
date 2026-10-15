#!/usr/bin/env python3
"""Independent acceptance oracle for the usd-validate-fix demo.

Re-derives every property the SPEC requires from the artifact with usd-core
(`pxr`) alone -- it never imports validator code -- so it can disagree with
the NVIDIA validator, and a disagreement fails the grade.

Two entry points used by judge/grade.sh:
  check_asset(path)          -> (errors, facts)   SPEC gate 2
  check_geometry(path, ref)  -> (errors, facts)   SPEC gate 3

Both return deterministic structures (sorted / stage-traversal order).
"""
from __future__ import annotations

import math

# `Usd` must be imported before `Sdf`-adjacent first use: the usd-core wheel
# registers its plugins lazily and a bare Sdf open cannot resolve the usda
# file format otherwise.
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade

METERS_PER_UNIT = 0.01          # the asset is authored in centimetres
UNIT_TOL = 1e-4                 # |norm|-1 tolerance, float32 normals
AREA_TOL = 1e-9                 # cm^2, triangle-fan total cross product
EXTENT_TOL = 1e-5               # cm, extent must contain every point
BBOX_TOL = 1e-6                 # cm, vs the original asset's points bbox


def _layer_metadata(stage):
    """(root-layer-authored metersPerUnit, upAxis, defaultPrim) as text."""
    root = stage.GetRootLayer().pseudoRoot
    out = {}
    for key in ("metersPerUnit", "upAxis", "defaultPrim"):
        out[key] = root.GetInfo(key) if root.HasInfo(key) else None
    return out


def _meshes(stage):
    return [p for p in stage.Traverse() if p.IsA(UsdGeom.Mesh)]


def _face_areas(points, counts, indices):
    """Total triangle-fan cross-product magnitude per face (2*area)."""
    out = []
    k = 0
    for count in counts:
        idx = indices[k:k + count]
        k += count
        v0 = Gf.Vec3d(points[idx[0]])
        acc = Gf.Vec3d(0.0)
        for j in range(1, count - 1):
            e1 = Gf.Vec3d(points[idx[j]]) - v0
            e2 = Gf.Vec3d(points[idx[j + 1]]) - v0
            acc += Gf.Cross(e1, e2)
        out.append(acc.GetLength())
    return out


def check_asset(path):
    """SPEC gate 2: recount every required property with usd-core alone."""
    errors = []
    stage = Usd.Stage.Open(path)
    if stage is None:
        return ["stage failed to open"], {}

    meta = _layer_metadata(stage)
    if meta["metersPerUnit"] is None:
        errors.append("metersPerUnit not authored on the root layer")
    elif abs(meta["metersPerUnit"] - METERS_PER_UNIT) > 1e-9:
        errors.append("metersPerUnit = %r != %r"
                      % (meta["metersPerUnit"], METERS_PER_UNIT))
    if meta["upAxis"] is None:
        errors.append("upAxis not authored on the root layer")
    elif meta["upAxis"] != "Y":
        errors.append("upAxis = %r != 'Y'" % meta["upAxis"])
    if meta["defaultPrim"] is None:
        errors.append("defaultPrim not authored on the root layer")
    elif not stage.GetPrimAtPath("/" + str(meta["defaultPrim"])).IsValid():
        errors.append("defaultPrim /%s does not resolve to a prim"
                      % meta["defaultPrim"])

    meshes = _meshes(stage)
    if not meshes:
        errors.append("no Mesh prims on the stage")

    colliders = 0
    for prim in stage.Traverse():
        if prim.HasAPI(UsdPhysics.CollisionAPI):
            colliders += 1
    if colliders == 0:
        errors.append("no prim carries UsdPhysics.CollisionAPI")

    mesh_facts = {}
    for prim in meshes:
        mid = str(prim.GetPath())
        mesh = UsdGeom.Mesh(prim)
        counts = list(mesh.GetFaceVertexCountsAttr().Get() or [])
        indices = list(mesh.GetFaceVertexIndicesAttr().Get() or [])
        points = list(mesh.GetPointsAttr().Get() or [])
        fact = {"points": len(points),
                "face_corners": sum(counts),
                "zero_area_faces": 0,
                "max_normal_dev": 0.0}

        normals_attr = mesh.GetNormalsAttr()
        if not normals_attr.HasAuthoredValue():
            errors.append("%s: normals not authored" % mid)
            fact["normals"] = None
        else:
            normals = list(normals_attr.Get() or [])
            fact["normals"] = len(normals)
            if len(normals) != sum(counts):
                errors.append("%s: %d normals != %d face-corners"
                              % (mid, len(normals), sum(counts)))
            interp = normals_attr.GetMetadata("interpolation")
            fact["normals_interpolation"] = str(interp)
            if interp != "faceVarying":
                errors.append("%s: normals interpolation %r != 'faceVarying'"
                              % (mid, interp))
            worst = 0.0
            for n in normals:
                if not all(math.isfinite(c) for c in n):
                    errors.append("%s: non-finite normal" % mid)
                    break
                worst = max(worst, abs(math.sqrt(n[0] ** 2 + n[1] ** 2
                                                 + n[2] ** 2) - 1.0))
            fact["max_normal_dev"] = round(worst, 9)
            if worst > UNIT_TOL:
                errors.append("%s: a normal deviates from unit length by "
                              "%.3g > %g" % (mid, worst, UNIT_TOL))

        if points and indices:
            areas = _face_areas(points, counts, indices)
            fact["zero_area_faces"] = sum(1 for a in areas if a < AREA_TOL)
            if fact["zero_area_faces"]:
                errors.append("%s: %d face(s) with triangle-fan area < %g "
                              "cm^2 (2*area %.3g)"
                              % (mid, fact["zero_area_faces"], AREA_TOL,
                                 min(a for a in areas if a < AREA_TOL)))

        bound = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]
        if not bound or not bound.GetPrim().IsValid():
            errors.append("%s: no computable bound material" % mid)
            fact["bound_material"] = None
        else:
            fact["bound_material"] = str(bound.GetPrim().GetPath())

        extent_attr = mesh.GetExtentAttr()
        if not extent_attr.HasAuthoredValue():
            errors.append("%s: extent not authored" % mid)
            fact["extent"] = None
        else:
            lo, hi = extent_attr.Get()
            lo, hi = Gf.Vec3d(lo), Gf.Vec3d(hi)
            fact["extent"] = [[round(c, 6) for c in lo],
                              [round(c, 6) for c in hi]]
            for pt in points:
                v = Gf.Vec3d(pt)
                if any(v[a] < lo[a] - EXTENT_TOL or v[a] > hi[a] + EXTENT_TOL
                       for a in range(3)):
                    errors.append("%s: point (%g, %g, %g) outside authored "
                                  "extent by more than %g cm"
                                  % (mid, v[0], v[1], v[2], EXTENT_TOL))
                    break
        mesh_facts[mid] = fact

    facts = {"metersPerUnit": meta["metersPerUnit"],
             "upAxis": meta["upAxis"],
             "defaultPrim": str(meta["defaultPrim"]),
             "meshes": mesh_facts,
             "colliders": colliders}
    return errors, facts


def check_geometry(path, reference):
    """SPEC gate 3: the repair must not move/scale/delete geometry."""
    errors = []

    def geometry(p):
        stage = Usd.Stage.Open(p)
        if stage is None:
            raise RuntimeError("stage failed to open: %s" % p)
        out = {}
        for prim in _meshes(stage):
            pts = list(UsdGeom.Mesh(prim).GetPointsAttr().Get() or [])
            if pts:
                lo = [min(q[a] for q in pts) for a in range(3)]
                hi = [max(q[a] for q in pts) for a in range(3)]
            else:
                lo = hi = [0.0, 0.0, 0.0]
            out[str(prim.GetPath())] = (len(pts), lo, hi)
        return out

    try:
        art, ref = geometry(path), geometry(reference)
    except RuntimeError as exc:
        return [str(exc)], {}

    if set(art) != set(ref):
        errors.append("Mesh prim paths differ from the original: "
                      "artifact %s vs original %s"
                      % (sorted(art), sorted(ref)))
    facts = {}
    for key in sorted(set(art) & set(ref)):
        n_art, lo_a, hi_a = art[key]
        n_ref, lo_r, hi_r = ref[key]
        worst = 0.0
        if n_art != n_ref:
            errors.append("%s: point count %d != original %d"
                          % (key, n_art, n_ref))
        for a in range(3):
            worst = max(worst,
                        abs(lo_a[a] - lo_r[a]), abs(hi_a[a] - hi_r[a]))
        facts[key] = {"points": n_art, "bbox_dev_cm": round(worst, 9)}
        if worst > BBOX_TOL:
            errors.append("%s: points bbox deviates from the original by "
                          "%.3g cm > %g cm" % (key, worst, BBOX_TOL))
    return errors, facts


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) not in (2, 3):
        print("usage: oracle.py <artifact.usda> [reference.usda]",
              file=sys.stderr)
        sys.exit(2)
    errs, facts = check_asset(sys.argv[1])
    out = {"gate2_oracle": {"passed": not errs, "errors": errs},
           "facts": facts}
    if len(sys.argv) == 3:
        errs3, facts3 = check_geometry(sys.argv[1], sys.argv[2])
        out["gate3_geometry"] = {"passed": not errs3, "errors": errs3}
        out["geometry"] = facts3
    print(json.dumps(out, indent=1, sort_keys=True))
    sys.exit(0 if not errs and (len(sys.argv) == 2 or not errs3) else 1)
