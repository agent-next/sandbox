# Agent build script — DXF top view of the adapter plate (spec: specs/plate.md)
#
# Runs through the freecad-mcp execute_code_headless tool: Draft's DXF writer
# cannot run on the GUI thread without a 3D view, so the MCP server runs this
# in a separate freecadcmd process. The driver injects OUTPUT_DIR as a global.

import math
import os

import FreeCAD as App
import Part

PLATE_L = 100.0      # keep in sync with build_plate.py
PLATE_W = 80.0
BORE_D = 30.0
BOLT_D = 5.5
BOLT_R = 35.0
BOLT_N = 6
BOLT_A0 = 0.0

doc = App.newDocument("plate_dxf")
objs = []


def add(shape, name):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    objs.append(o)


add(Part.Wire(Part.makePolygon([
    App.Vector(-PLATE_L / 2.0, -PLATE_W / 2.0, 0), App.Vector(PLATE_L / 2.0, -PLATE_W / 2.0, 0),
    App.Vector(PLATE_L / 2.0, PLATE_W / 2.0, 0), App.Vector(-PLATE_L / 2.0, PLATE_W / 2.0, 0),
    App.Vector(-PLATE_L / 2.0, -PLATE_W / 2.0, 0)])), "outline")
add(Part.Wire(Part.makeCircle(BORE_D / 2.0, App.Vector(0, 0, 0), App.Vector(0, 0, 1))), "bore")
for i in range(BOLT_N):
    a = math.radians(BOLT_A0 + i * 360.0 / BOLT_N)
    add(Part.Wire(Part.makeCircle(
        BOLT_D / 2.0,
        App.Vector(BOLT_R * math.cos(a), BOLT_R * math.sin(a), 0),
        App.Vector(0, 0, 1))), "bolt%d" % i)
doc.recompute()

import importDXF
dxf = os.path.join(OUTPUT_DIR, "plate.dxf")
importDXF.export(objs, dxf)
print("PLATE_DXF_OK %s %d" % (dxf, os.path.getsize(dxf)))
