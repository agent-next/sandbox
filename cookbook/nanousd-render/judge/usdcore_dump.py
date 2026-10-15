#!/usr/bin/env python3
"""Out-of-process usd-core reader for the nanousd-render judge.

judge.py never imports pxr while grading: the artifact under test is
opened by THIS script in its own process, so a crafted USDA cannot touch
the judge's process (the C dumper and the renderer were already separate
processes; this closes the last in-process path). Output is one JSON
record on stdout, shaped exactly like the nanousd dump:

    {"prims": [...], "forbidden_arcs": [...]}   or   {"error": "..."}

Any failure is reported as an {"error": ...} record (or a non-zero exit
if the process itself dies); the judge fails closed on both.

The record also carries `forbidden_arcs`: composition arcs and plugin
schemas as REPORTED BY THE PARSER (Sdf field keys, prim type names) --
not by scanning the file text, which formatting can smuggle past (a
mutant does exactly that: ``inherits=[</Nope>]`` with no spaces).
"""

from __future__ import annotations

import json
import sys

# composition-arc fields usd-core authors on a prim/layer spec; anything
# here can make two readers disagree about what is in the stage
ARC_FIELDS = ("references", "payload", "inherits", "variantSets",
              "variants", "instanceable")
SCHEMA_FORBIDDEN_PREFIXES = ("SkelRoot", "PhysicsScene", "PhysicsRigidBody")


def vt_to_py(v):
    """Convert a pxr value to plain Python (Vec arrays -> flat float lists
    to match nanousd_dump's shape)."""
    from pxr import Gf
    if isinstance(v, (int, float, str, bool)):
        return v
    if isinstance(v, (Gf.Vec2f, Gf.Vec2d, Gf.Vec3f, Gf.Vec3d, Gf.Vec4f,
                      Gf.Vec4d)):
        return [float(c) for c in v]
    if hasattr(v, "__iter__"):
        out = []
        for item in v:
            c = vt_to_py(item)
            if c is None:
                return None
            out.extend(c) if isinstance(c, list) else out.append(c)
        return out
    return None


def find_forbidden_arcs(stage):
    """Composition arcs and forbidden schemas straight from the parsed
    layer specs -- formatting cannot hide from this."""
    arcs = []
    layer = stage.GetRootLayer()
    subs = list(layer.subLayerPaths or [])
    if subs:
        arcs.append({"where": "<layer>", "arc": "subLayers",
                     "detail": [str(p) for p in subs]})
    for spec in layer.Traverse():
        path = str(spec.path)
        for field in spec.ListInfoKeys():
            if field in ARC_FIELDS:
                arcs.append({"where": path, "arc": field,
                             "detail": str(spec.GetInfo(field))[:80]})
    for prim in stage.Traverse():
        type_name = prim.GetTypeName() or ""
        if type_name.startswith(SCHEMA_FORBIDDEN_PREFIXES):
            arcs.append({"where": str(prim.GetPath()), "arc": "schema",
                         "detail": f"prim type {type_name}"})
    return arcs


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"error": "usage: usdcore_dump.py <file.usda>"}))
        return 2
    path = sys.argv[1]
    try:
        from pxr import Usd, UsdGeom  # noqa: F401 (UsdGeom used below)
    except ImportError as e:
        print(json.dumps({"error": f"usd-core not importable: {e}"}))
        return 0
    try:
        stage = Usd.Stage.Open(path)
    except Exception as e:
        print(json.dumps({"error": f"stage open raised: {e}"}))
        return 0
    if stage is None:
        print(json.dumps({"error": "Usd.Stage.Open returned None"}))
        return 0
    try:
        record = dump_stage(stage)
        record["forbidden_arcs"] = find_forbidden_arcs(stage)
        print(json.dumps(record))
        return 0
    except Exception as e:
        print(json.dumps({"error": f"usd-core traversal raised: {e}"}))
        return 0


def dump_stage(stage) -> dict:
    from pxr import UsdGeom
    world = stage.GetPrimAtPath("/World")
    prims = []
    if world and world.IsActive():
        xc = UsdGeom.XformCache()
        for p in world.GetAllChildren():
            entry = {"path": str(p.GetPath()),
                     "type": p.GetTypeName() or "",
                     "defined": int(p.IsActive())}
            try:
                entry["xform"] = [float(c) for row in
                                  xc.GetLocalToWorldTransform(p)
                                  for c in row]
                entry["xform_ok"] = 1
            except Exception:
                entry["xform"] = [0.0] * 16
                entry["xform_ok"] = 0
            entry["attribs"] = {}
            for name in ("points", "faceVertexCounts", "faceVertexIndices",
                         "primvars:displayColor", "focalLength",
                         "horizontalAperture", "verticalAperture",
                         "clippingRange", "inputs:intensity"):
                attr = p.GetAttribute(name)
                if not attr or not attr.HasValue():
                    continue
                conv = vt_to_py(attr.Get())
                if conv is not None:
                    entry["attribs"][name] = conv
            prims.append(entry)
    return {"prims": prims}


if __name__ == "__main__":
    sys.exit(main())
