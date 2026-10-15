# Agent build script — flanged bushing (spec: specs/bushing.md)
#
# Runs inside FreeCAD (via the freecad-mcp execute_code tool, or freecadcmd).
# The driver injects OUTPUT_DIR as a global before executing this script.

import os

import FreeCAD as App
import Mesh
import Part

BORE_D = 20.0       # through bore, axis +Z through origin
HUB_D = 36.0        # hub outer diameter
HUB_H = 40.0        # total height (z 0 -> 40)
FLANGE_D = 60.0     # flange outer diameter
FLANGE_T = 8.0      # flange thickness at the bottom (z 0 -> 8)


def build():
    hub = Part.makeCylinder(HUB_D / 2.0, HUB_H, App.Vector(0, 0, 0), App.Vector(0, 0, 1))
    flange = Part.makeCylinder(FLANGE_D / 2.0, FLANGE_T, App.Vector(0, 0, 0), App.Vector(0, 0, 1))
    bore = Part.makeCylinder(BORE_D / 2.0, HUB_H + 2.0, App.Vector(0, 0, -1.0), App.Vector(0, 0, 1))
    solid = hub.fuse(flange).cut(bore)
    return solid.removeSplitter()


def export(solid):
    step = os.path.join(OUTPUT_DIR, "bushing.step")
    stl = os.path.join(OUTPUT_DIR, "bushing.stl")
    solid.exportStep(step)
    verts, facets = solid.tessellate(0.02)
    mesh = Mesh.Mesh([tuple(verts[i] for i in f) for f in facets])
    mesh.harmonizeNormals()
    mesh.write(stl)
    return step, stl


solid = build()
if not solid.isValid():
    raise RuntimeError("bushing shape failed BRepCheck")
step, stl = export(solid)
print("BUSHING_OK volume=%.4f step=%s stl=%s" % (solid.Volume, step, stl))
