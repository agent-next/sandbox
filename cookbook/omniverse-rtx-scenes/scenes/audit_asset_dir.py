#!/usr/bin/env python3
"""audit_asset_dir.py — quick mesh/material/extent audit of an asset folder.

Thin wrapper around inspect_asset.py's audit + extents, so it can be run on
any asset root (HF dataset cache, Isaac S3 cache) to decide what to ship:

  python3 audit_asset_dir.py <asset_dir> [<one_usd_layer>]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "/home/user/w/cookbook/omniverse-rtx-scenes/scenes")


def main(argv: list[str]) -> int:
    import inspect_asset as ia  # noqa: PLC0415
    d = Path(argv[1])
    r = ia.audit(d, [d, d.parent])
    for k in ("layers", "meshes", "materials", "mdl", "preview",
              "unbound_surface", "textures"):
        print(f"{k:18s} {r[k]}")
    print(f"{'problems':18s} {len(r['problems'])}")
    for p in r["problems"][:4]:
        print("   ", p)
    if len(argv) > 2:
        from pxr import Usd, UsdGeom  # noqa: PLC0415
        layer = argv[2]
        st = Usd.Stage.Open(layer, load=Usd.Stage.LoadAll)
        mpm = UsdGeom.GetStageMetersPerUnit(st)
        mn, mx, n = [1e18] * 3, [-1e18] * 3, 0
        for p in st.Traverse(Usd.TraverseInstanceProxies()):
            if p.GetTypeName() != "Mesh":
                continue
            pts = UsdGeom.Mesh(p).GetPointsAttr().Get()
            if not pts:
                continue
            n += 1
            for i in range(3):
                mn[i] = min(mn[i], min(q[i] for q in pts))
                mx[i] = max(mx[i], max(q[i] for q in pts))
        if n:
            print(f"extents (m)  min {[round(v * mpm, 4) for v in mn]} "
                  f"max {[round(v * mpm, 4) for v in mx]} "
                  f"size {[round((mx[i] - mn[i]) * mpm, 4) for i in range(3)]}")
        joints = [p.GetPath().pathString for p in st.Traverse()
                  if "Joint" in p.GetTypeName()]
        print(f"joints {len(joints)} {joints[:6]}")
        lights = [p.GetPath().pathString for p in st.Traverse()
                  if "Light" in p.GetTypeName()]
        print(f"lights {len(lights)} {lights[:4]}")
        cams = [p.GetPath().pathString for p in st.Traverse()
                if p.GetTypeName() == "Camera"]
        print(f"cameras {len(cams)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
