#!/usr/bin/env python3
"""collect_meshes.py — dump the judged USD geometry for the video renderer.

Usage (run with the judge venv python — it has usd-core):
    python -I media/collect_meshes.py <verdict.json> <out.npz> [<stage-dir>]

Reads the artifact stage files named by the verdict JSON (default:
examples/good), walks every Mesh prim with usd-core exactly like the
judge's oracle (world-space triangles via the points/faceVertexCounts/
faceVertexIndices attributes), and stores the triangles in scene units
plus the judge-measured counts in a single .npz for render_media.py.

No data is invented: the vertex arrays come from the same .usda files the
judge graded, in the same order.
"""

import json
import sys

import numpy as np


def triangles_from_usda(path):
    from pxr import Usd, UsdGeom, Gf
    stage = Usd.Stage.Open(path)
    if not stage:
        sys.exit(f"collect: cannot open {path}")
    xc = UsdGeom.XformCache()
    tris = []
    for prim in stage.Traverse():
        if not prim.IsA(UsdGeom.Mesh):
            continue
        mesh = UsdGeom.Mesh(prim)
        points = mesh.GetPointsAttr().Get()
        counts = mesh.GetFaceVertexCountsAttr().Get()
        idx = mesh.GetFaceVertexIndicesAttr().Get()
        if not (points and counts and idx):
            continue
        xf = xc.GetLocalToWorldTransform(prim)
        wp = np.array(
            [[*xf.Transform(Gf.Vec3d(p[0], p[1], p[2]))] for p in points])
        i0 = 0
        for c in counts:
            for k in range(1, c - 1):
                tris.append((wp[idx[i0]], wp[idx[i0 + k]], wp[idx[i0 + k + 1]]))
            i0 += c
    if not tris:
        sys.exit(f"collect: no triangles in {path}")
    return np.array(tris, dtype=np.float64)


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: collect_meshes.py <verdict.json> <out.npz> "
                 "[<stage-dir>]")
    verdict_path, out_path = sys.argv[1], sys.argv[2]
    stage_dir = sys.argv[3] if len(sys.argv) > 3 else "examples/good"
    with open(verdict_path) as f:
        verdict = json.load(f)
    if verdict.get("all_gates_passed") is not True:
        sys.exit("collect: refusing to render a non-PASS verdict")
    blobs = {}
    for key in verdict["measures"]:
        tris = triangles_from_usda(f"{stage_dir}/{key}.usda")
        # store centered: the renderer orbits the part's own centroid
        centroid = tris.reshape(-1, 3).mean(axis=0)
        blobs[key] = (tris - centroid).astype(np.float32)
        print(f"[collect] {key}: {len(tris)} triangles from {stage_dir}/{key}.usda")
    np.savez_compressed(out_path, **blobs)


if __name__ == "__main__":
    main()
