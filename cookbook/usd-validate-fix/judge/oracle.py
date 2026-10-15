#!/usr/bin/env python3
"""Independent acceptance oracle for the usd-validate-fix demo.

Re-derives every property the SPEC requires from the artifact with usd-core
(`pxr`) alone -- it never imports validator code -- so it can disagree with
the NVIDIA validator, and a disagreement fails the grade.

Three entry points used by judge/grade.sh:
  check_asset(path)          -> (errors, facts)   SPEC gate 2
  check_geometry(path, ref)  -> (errors, facts)   SPEC gate 3
  check_up_axis(path)        -> (errors, facts)   SPEC gate 5

All three return deterministic structures (sorted /
stage-traversal order).
"""
from __future__ import annotations

import math

# `Usd` must be imported before `Sdf`-adjacent first use: the usd-core wheel
# registers its plugins lazily and a bare Sdf open cannot resolve the usda
# file format otherwise.
from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade

# SPEC.md: which material each mesh must be bound to.  A gate that only
# checks "some material is bound" lets a repair bind the wrong one.
BAND_BINDING = "/TrafficCone/Looks/WhitePlastic"
BODY_BINDING = "/TrafficCone/Looks/OrangePlastic"
REQUIRED_BINDINGS = {"/TrafficCone/Band": BAND_BINDING,
                     "/TrafficCone/Body": BODY_BINDING,
                     "/TrafficCone/Base": BODY_BINDING}

METERS_PER_UNIT = 0.01          # the asset is authored in centimetres
UNIT_TOL = 1e-4                 # |norm|-1 tolerance, float32 normals
AREA_TOL = 1e-9                 # cm^2, triangle-fan total cross product
EXTENT_TOL = 1e-5               # cm, extent must contain every point
BBOX_TOL = 1e-6                 # cm, vs the original asset's points bbox
# gate 5: the height axis must win by this margin over the other two
# (the cone is 36 x 42 x 58 cm, so 58 - 42 = 16 cm clears it easily)
HEIGHT_MARGIN_CM = 5.0


def _layer_metadata(stage):
    """(root-layer-authored metersPerUnit, upAxis, defaultPrim) as text."""
    root = stage.GetRootLayer().pseudoRoot
    out = {}
    for key in ("metersPerUnit", "upAxis", "defaultPrim"):
        out[key] = root.GetInfo(key) if root.HasInfo(key) else None
    return out


def _meshes(stage):
    return [p for p in stage.Traverse() if p.IsA(UsdGeom.Mesh)]


def _world_bounds(prim, cache):
    """The composed world-space aligned bbox of one prim (Gf.Range3d)."""
    return cache.ComputeWorldBound(prim).ComputeAlignedRange()


def _axis_names():
    """{0: 'X', 1: 'Y', 2: 'Z'} -- UsdGeom's up-axis token to a range axis."""
    return {0: "X", 1: "Y", 2: "Z"}


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
            want = REQUIRED_BINDINGS.get(mid)
            if want is not None and fact["bound_material"] != want:
                errors.append("%s: bound to %s, must be %s (the reflective "
                              "band is the white plastic)" % (
                                  mid, fact["bound_material"], want))

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


def _stage_geometry(stage):
    """{mesh path: (point_count, composed world bbox)} for one stage.

    The bbox is the **world** bound from UsdGeom.BBoxCache, so it includes
    every xformOp on the ancestor chain: a repair that scales the mesh 100x,
    or moves and tips it over with a transform, changes this number even
    though the authored `points` array is untouched.
    """
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(),
                              [UsdGeom.Tokens.default_, UsdGeom.Tokens.render],
                              useExtentsHint=False)
    out = {}
    for prim in _meshes(stage):
        rng = _world_bounds(prim, cache)
        lo = [rng.GetMin()[a] for a in range(3)]
        hi = [rng.GetMax()[a] for a in range(3)]
        pts = UsdGeom.Mesh(prim).GetPointsAttr().Get()
        out[str(prim.GetPath())] = (len(pts or []), lo, hi)
    return out


def check_geometry(path, reference):
    """SPEC gate 3: the repair must not move/scale/delete geometry."""
    errors = []

    def geometry(p):
        stage = Usd.Stage.Open(p)
        if stage is None:
            raise RuntimeError("stage failed to open: %s" % p)
        return _stage_geometry(stage)

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
        # world-space extent per axis: a transform is a repair-time edit
        span_a = [hi_a[a] - lo_a[a] for a in range(3)]
        span_r = [hi_r[a] - lo_r[a] for a in range(3)]
        for a in range(3):
            worst = max(worst, abs(lo_a[a] - lo_r[a]),
                        abs(hi_a[a] - hi_r[a]), abs(span_a[a] - span_r[a]))
        facts[key] = {"points": n_art,
                      "world_bbox_cm": [[round(c, 6) for c in lo_a],
                                        [round(c, 6) for c in hi_a]],
                      "bbox_dev_cm": round(worst, 9)}
        if worst > BBOX_TOL:
            errors.append("%s: world bbox deviates from the original by "
                          "%.3g cm > %g cm (a transform that moves, scales "
                          "or tips the mesh fails the repair)"
                          % (key, worst, BBOX_TOL))
    return errors, facts


def check_up_axis(path):
    """SPEC gate 5: the stage's up axis must be the model's height axis.

    `upAxis` is the stage's contract with every Y-up (or Z-up) consumer, so
    it must describe the geometry actually in the file.  The height axis is
    the world bbox's largest extent axis -- and it is measured, not read
    from the metadata the artifact just declared, so declaring "Y" while
    authoring the cone along some other axis fails here, and so does an
    artifact whose transforms tip the cone over.

    The bbox is taken over **all** meshes together (the whole prop is 36 x
    42 x 58 cm), because the individual pieces are not all elongated: the
    base is a 36 x 4 x 36 slab and has no height of its own.
    """
    errors = []
    stage = Usd.Stage.Open(path)
    if stage is None:
        return ["stage failed to open"], {}
    up = UsdGeom.GetStageUpAxis(stage)
    if up is None:
        return ["upAxis not authored on the root layer"], {}
    up_axis = {"X": 0, "Y": 1, "Z": 2}.get(str(up))
    if up_axis is None:
        return ["upAxis = %r is not one of X/Y/Z" % str(up)], {}

    meshes = _meshes(stage)
    if not meshes:
        return ["no Mesh prims on the stage"], {}

    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(),
                              [UsdGeom.Tokens.default_, UsdGeom.Tokens.render],
                              useExtentsHint=False)
    union = Gf.Range3d()
    per_mesh = {}
    for prim in meshes:
        rng = _world_bounds(prim, cache)
        union.UnionWith(rng)
        per_mesh[str(prim.GetPath())] = {
            "world_bbox_cm": [[round(rng.GetMin()[a], 6) for a in range(3)],
                              [round(rng.GetMax()[a], 6) for a in range(3)]]}
    spans = [union.GetMax()[a] - union.GetMin()[a] for a in range(3)]
    tallest = max(range(3), key=lambda a: spans[a])
    margin = spans[tallest] - max(spans[a] for a in range(3) if a != tallest)

    facts = {"upAxis": str(up),
             "world_bbox_cm": [[round(union.GetMin()[a], 6) for a in range(3)],
                               [round(union.GetMax()[a], 6) for a in range(3)]],
             "height_axis": _axis_names()[tallest],
             "height_margin_cm": round(margin, 6),
             "meshes": per_mesh}
    if margin < HEIGHT_MARGIN_CM:
        errors.append("the prop's height is not unambiguous (world spans %s "
                      "cm, margin %.3g cm < %g cm) -- cannot check the up axis"
                      % (", ".join("%s=%.3f" % (_axis_names()[a], spans[a])
                                   for a in range(3)), margin,
                         HEIGHT_MARGIN_CM))
    elif tallest != up_axis:
        errors.append("upAxis is %r but the prop's height axis measures as %r "
                      "(world spans %s cm) -- the geometry lies on its side "
                      "for this up axis"
                      % (str(up), _axis_names()[tallest],
                         ", ".join("%s=%.1f" % (_axis_names()[a], spans[a])
                                   for a in range(3))))
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
    errs5, facts5 = check_up_axis(sys.argv[1])
    out["gate5_up_axis"] = {"passed": not errs5, "errors": errs5}
    out["up_axis"] = facts5
    errs3, facts3 = check_geometry(sys.argv[1], sys.argv[2]) if len(
        sys.argv) == 3 else ([], {})
    if len(sys.argv) == 3:
        out["gate3_geometry"] = {"passed": not errs3, "errors": errs3}
        out["geometry"] = facts3
    print(json.dumps(out, indent=1, sort_keys=True))
    sys.exit(0 if not errs and not errs5 and not errs3 else 1)
