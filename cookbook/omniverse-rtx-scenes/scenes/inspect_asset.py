#!/usr/bin/env python3
"""inspect_asset.py — measure a localised asset directory offline.

For every USD layer under a directory, reports:
  * meshes, materials, MDL materials, UsdPreviewSurface materials
  * materials whose surface output is not connected to a shader
  * texture inputs that do not resolve inside this directory

This is the same information the stage-2 render needs, so it doubles as the
audit tool the build uses to prove every referenced texture/MDL is local.

  python3 inspect_asset.py <asset_dir> [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pxr import Sdf, Usd, UsdGeom, UsdShade

# Outputs a material may use to declare its surface, most-specific first.
# SimReady assets bind `outputs:mdl:surface` (MDL render context), some
# earlier packs bind `outputs:surface` with an `info:mdl:sourceAsset` shader.
SURFACE_OUTPUTS = ("outputs:mdl:surface", "outputs:surface",
                   "outputs:universal:surface")


def surface_shader(material_prim: Usd.Prim, stage: Usd.Stage) -> Usd.Prim | None:
    """The Shader prim a Material's surface output is connected to, if any.

    UsdShade.Material.GetConnectedSources() is unreliable across packaged
    asset layouts (it returns no source for materials bound by the SimReady
    packs even when `outputs:mdl:surface.connect` is authored), so read the
    connection straight off the attribute.
    """
    for name in SURFACE_OUTPUTS:
        attr = material_prim.GetAttribute(name)
        if not attr:
            continue
        conns = attr.GetConnections()
        if not conns:
            continue
        for path in conns:  # e.g. .../Shader.outputs:out
            p = path.GetPrimPath()
            sp = stage.GetPrimAtPath(p)
            if sp:
                return sp
    return None


def shader_mdl_source(shader_prim: Usd.Prim) -> str | None:
    """`info:mdl:sourceAsset` of a shader, or None if it is not MDL."""
    if not shader_prim:
        return None
    a = shader_prim.GetAttribute("info:mdl:sourceAsset")
    v = a.Get() if a else None
    return str(v) if v else None


def surface_output_name(material_prim: Usd.Prim) -> str | None:
    """Which of SURFACE_OUTPUTS the material actually defines."""
    for name in SURFACE_OUTPUTS:
        attr = material_prim.GetAttribute(name)
        if attr and attr.GetConnections():
            return name
    return None


def _exists(p, layer_dir, search) -> bool:
    """Does this asset path (str or Sdf.AssetPath) resolve under search?

    layer_dir is the directory of the layer that referenced it; search is a
    list of extra directories (scene assets root, the mdl/ chain, …) that a
    bare reference such as `OmniPBR.mdl` may resolve against offline.
    """
    try:
        s = str(p.path)
    except AttributeError:
        s = str(p)
    if not s or s.startswith("<"):
        return True  # placeholder (e.g. <UDIM>) — nothing to resolve
    bases = [layer_dir] + [Path(x) for x in search]
    for base in bases:
        if (Path(base) / s).exists():
            return True
    return False


def extents(usd_path: Path) -> dict:
    """Point-extent of one layer's meshes, in metres and in asset units.

    SimReady cm assets carry metersPerUnit=0.01, so a raw extent of 206 cm is
    2.06 m.  Measuring raw points (rather than ComputeWorldBound, which
    mis-sums across nested Xforms of an odd root scale) keeps the number the
    build needs for placement.
    """
    st = Usd.Stage.Open(str(usd_path), load=Usd.Stage.LoadAll)
    mp = UsdGeom.GetStageMetersPerUnit(st)
    mn, mx, n = [1e18] * 3, [-1e18] * 3, 0
    for prim in st.Traverse(Usd.TraverseInstanceProxies()):
        if prim.GetTypeName() != "Mesh":
            continue
        pts = UsdGeom.Mesh(prim).GetPointsAttr().Get()
        if not pts:
            continue
        n += 1
        for i in range(3):
            mn[i] = min(mn[i], min(q[i] for q in pts))
            mx[i] = max(mx[i], max(q[i] for q in pts))
    if not n:
        return {"layer": str(usd_path), "meshes": 0, "size_m": None}
    return {
        "layer": str(usd_path), "meshes": n,
        "metersPerUnit": mp,
        "min_m": [round(v * mp, 4) for v in mn],
        "max_m": [round(v * mp, 4) for v in mx],
        "size_m": [round((mx[i] - mn[i]) * mp, 4) for i in range(3)],
        "center_m": [round((mx[i] + mn[i]) / 2 * mp, 4) for i in range(3)],
    }


def audit(asset_dir: Path, search: list[Path]) -> dict:
    out = {
        "dir": str(asset_dir),
        "layers": 0, "meshes": 0, "materials": 0, "mdl": 0,
        "preview": 0, "unbound_surface": 0, "textures": 0,
        "problems": [],
    }
    seen = set()
    for usd in sorted(asset_dir.rglob("*.usd*")):
        if usd.suffix not in (".usd", ".usda", ".usdc"):
            continue
        if str(usd) in seen:
            continue
        seen.add(str(usd))
        out["layers"] += 1
        try:
            st = Usd.Stage.Open(str(usd), load=Usd.Stage.LoadAll)
        except Exception as e:  # noqa: BLE001
            out["problems"].append(f"open {usd.name}: {e}")
            continue
        for prim in st.Traverse(Usd.TraverseInstanceProxies()):
            if prim.GetTypeName() == "Mesh":
                out["meshes"] += 1
        for prim in st.Traverse(Usd.TraverseInstanceProxies()):
            if not prim.IsA(UsdShade.Material):
                continue
            out["materials"] += 1
            shader = surface_shader(prim, st)
            if not shader:
                out["unbound_surface"] += 1
                out["problems"].append(
                    f"{usd.name}: material {prim.GetName()} has no "
                    f"connected surface output")
                continue
            src = shader_mdl_source(shader)
            if src:
                out["mdl"] += 1
                if not _exists(src, usd.parent,
                               search + [asset_dir, asset_dir.parent]):
                    out["problems"].append(
                        f"{usd.name}: material {prim.GetName()} mdl "
                        f"{src} does not resolve")
            else:
                out["preview"] += 1
            for inp in UsdShade.Shader(shader).GetInputs():
                v = inp.Get()
                if isinstance(v, Sdf.AssetPath):
                    out["textures"] += 1
                    if not _exists(v, usd.parent, search + [asset_dir]):
                        out["problems"].append(
                            f"{usd.name}: {inp.GetAttr().GetName()} "
                            f"{v.path} missing")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("asset_dir", type=Path)
    ap.add_argument("--search", nargs="*", default=[],
                    help="extra dirs to resolve bare refs against")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--extents", type=Path, default=None,
                    help="also report point extents of one layer")
    a = ap.parse_args()
    if a.extents:
        print(json.dumps(extents(a.extents), indent=2))
        return 0
    r = audit(a.asset_dir, [Path(p) for p in a.search])
    print(json.dumps(r, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
