#!/usr/bin/env python3
"""Dump the renderable facts of one .usda asset to JSON (media pipeline).

Run with the judge venv python (needs pxr):

  <venv>/python -I media/extract_mesh.py <asset.usda> <out.json>

Reads the asset itself -- points, face topology, authored normals, authored
extent, bound material and its diffuseColor, and the root-layer metadata --
so the figures and the video render the artifact the judge graded, not a
redraw of the generator.  Nothing here invents data; missing values (e.g.
no authored normals on the broken asset) come out as null.
"""
import json
import sys

from pxr import Usd, UsdGeom, UsdShade


def material_color(stage, prim):
    """(material path, diffuseColor) bound to a prim, or (None, None)."""
    bound = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]
    if not bound or not bound.GetPrim().IsValid():
        return None, None
    src = bound.GetSurfaceOutput().GetConnectedSource()
    if not src:
        return str(bound.GetPath()), None
    shader = UsdShade.Shader(src[0].GetPrim())
    color = shader.GetInput("diffuseColor").Get()
    if color is None:
        return str(bound.GetPath()), None
    return str(bound.GetPath()), [float(c) for c in color]


def main():
    if len(sys.argv) != 3:
        print("usage: extract_mesh.py <asset.usda> <out.json>", file=sys.stderr)
        return 2
    stage = Usd.Stage.Open(sys.argv[1])
    if stage is None:
        print("extract_mesh: cannot open %s" % sys.argv[1], file=sys.stderr)
        return 1

    pseudo = stage.GetRootLayer().pseudoRoot
    meta = {}
    for key in ("metersPerUnit", "upAxis", "defaultPrim"):
        meta[key] = (str(pseudo.GetInfo(key))
                     if pseudo.HasInfo(key) else None)

    meshes = []
    for prim in stage.Traverse():
        if not prim.IsA(UsdGeom.Mesh):
            continue
        mesh = UsdGeom.Mesh(prim)
        normals_attr = mesh.GetNormalsAttr()
        extent_attr = mesh.GetExtentAttr()
        mat_path, color = material_color(stage, prim)
        meshes.append({
            "path": str(prim.GetPath()),
            "points": [[float(c) for c in p]
                       for p in (mesh.GetPointsAttr().Get() or [])],
            "faceVertexCounts": [int(c) for c in
                                 (mesh.GetFaceVertexCountsAttr().Get() or [])],
            "faceVertexIndices": [int(i) for i in
                                  (mesh.GetFaceVertexIndicesAttr().Get() or [])],
            "normals": ([[float(c) for c in n]
                         for n in (normals_attr.Get() or [])]
                        if normals_attr.HasAuthoredValue() else None),
            "normals_interpolation": (
                str(normals_attr.GetMetadata("interpolation"))
                if normals_attr.HasAuthoredValue() else None),
            "extent": ([[float(c) for c in v]
                        for v in extent_attr.Get()]
                       if extent_attr.HasAuthoredValue() else None),
            "bound_material": mat_path,
            "diffuseColor": color,
        })

    out = {"asset": sys.argv[1], "metadata": meta, "meshes": meshes}
    with open(sys.argv[2], "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
        fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
