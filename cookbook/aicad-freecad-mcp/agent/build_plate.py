# Agent build script — adapter plate with bolt circle (spec: specs/plate.md)
#
# Runs inside FreeCAD (via the freecad-mcp execute_code tool, or freecadcmd).
# The driver injects OUTPUT_DIR as a global before executing this script.

import math
import os

import FreeCAD as App
import Mesh
import Part

PLATE_L = 100.0      # x extent, centred on origin
PLATE_W = 80.0       # y extent, centred on origin
PLATE_T = 10.0       # z extent, centred on origin
BORE_D = 30.0        # central through bore
BOLT_D = 5.5         # bolt hole diameter
BOLT_R = 35.0        # bolt circle radius
BOLT_N = 6           # number of bolt holes
BOLT_A0 = 0.0        # first hole angle from +X, degrees


def build():
    plate = Part.makeBox(PLATE_L, PLATE_W, PLATE_T,
                         App.Vector(-PLATE_L / 2.0, -PLATE_W / 2.0, -PLATE_T / 2.0))
    cutters = [Part.makeCylinder(BORE_D / 2.0, PLATE_T + 2.0,
                                 App.Vector(0, 0, -PLATE_T / 2.0 - 1.0), App.Vector(0, 0, 1))]
    for i in range(BOLT_N):
        a = math.radians(BOLT_A0 + i * 360.0 / BOLT_N)
        c = App.Vector(BOLT_R * math.cos(a), BOLT_R * math.sin(a), 0)
        cutters.append(Part.makeCylinder(BOLT_D / 2.0, PLATE_T + 2.0,
                                         c - App.Vector(0, 0, PLATE_T / 2.0 + 1.0),
                                         App.Vector(0, 0, 1)))
    for c in cutters:
        plate = plate.cut(c)
    return plate.removeSplitter()


def export(solid):
    step = os.path.join(OUTPUT_DIR, "plate.step")
    stl = os.path.join(OUTPUT_DIR, "plate.stl")
    solid.exportStep(step)
    verts, facets = solid.tessellate(0.02)
    mesh = Mesh.Mesh([tuple(verts[i] for i in f) for f in facets])
    mesh.harmonizeNormals()
    mesh.write(stl)
    return step, stl


solid = build()
if not solid.isValid():
    raise RuntimeError("plate shape failed BRepCheck")
step, stl = export(solid)
# The DXF top view is drawn by agent/draw_plate_dxf.py through the
# execute_code_headless tool: Draft's DXF writer needs a real 3D view on the
# GUI thread, so it runs in a separate freecadcmd process instead.
print("PLATE_OK volume=%.4f step=%s stl=%s" % (solid.Volume, step, stl))
