# Agent build script — L-bracket with fillet (spec: specs/bracket.md)
#
# Runs inside FreeCAD (via the freecad-mcp execute_code tool, or freecadcmd).
# The driver injects OUTPUT_DIR as a global before executing this script.

import os

import FreeCAD as App
import Mesh
import Part

BASE_L = 80.0        # base plate, x 0 -> 80
BASE_W = 50.0        # y 0 -> 50
BASE_T = 10.0        # base plate, z 0 -> 10
UP_X0 = 70.0         # upright inner face at x = 70
UP_H = 60.0          # upright top at z = 60
FILLET_R = 8.0       # inner fillet tangent to z=10 and x=70
BASE_HOLE_D = 10.0   # 2x through holes in the base, axis +Z
BASE_HOLE_XY = [(25.0, 25.0), (55.0, 25.0)]
UP_HOLE_D = 12.0     # 2x through holes in the upright, axis +X
UP_HOLE_YZ = [(15.0, 45.0), (35.0, 45.0)]


def build():
    profile = Part.makePolygon([
        App.Vector(0, 0, 0), App.Vector(BASE_L, 0, 0), App.Vector(BASE_L, 0, UP_H),
        App.Vector(UP_X0, 0, UP_H), App.Vector(UP_X0, 0, BASE_T), App.Vector(0, 0, BASE_T),
        App.Vector(0, 0, 0)])
    face = Part.Face(Part.Wire(profile))
    solid = face.extrude(App.Vector(0, BASE_W, 0))

    # fillet the inner concave edge (line at x = UP_X0, z = BASE_T, spanning y)
    edge = None
    for e in solid.Edges:
        p = e.Vertexes[0].Point
        if (abs(p.x - UP_X0) < 1e-6 and abs(p.z - BASE_T) < 1e-6
                and abs(e.Vertexes[-1].Point.y - e.Vertexes[0].Point.y - BASE_W) < 1e-6):
            edge = e
            break
    if edge is None:
        raise RuntimeError("inner edge not found for fillet")
    solid = solid.makeFillet(FILLET_R, [edge])

    for (x, y) in BASE_HOLE_XY:
        solid = solid.cut(Part.makeCylinder(
            BASE_HOLE_D / 2.0, BASE_T + 2.0,
            App.Vector(x, y, -1.0), App.Vector(0, 0, 1)))
    for (y, z) in UP_HOLE_YZ:
        solid = solid.cut(Part.makeCylinder(
            UP_HOLE_D / 2.0, BASE_L, App.Vector(UP_X0 - 1.0, y, z), App.Vector(1, 0, 0)))
    return solid.removeSplitter()


def export(solid):
    step = os.path.join(OUTPUT_DIR, "bracket.step")
    stl = os.path.join(OUTPUT_DIR, "bracket.stl")
    solid.exportStep(step)
    verts, facets = solid.tessellate(0.02)
    mesh = Mesh.Mesh([tuple(verts[i] for i in f) for f in facets])
    mesh.harmonizeNormals()
    mesh.write(stl)
    return step, stl


solid = build()
if not solid.isValid():
    raise RuntimeError("bracket shape failed BRepCheck")
step, stl = export(solid)
print("BRACKET_OK volume=%.4f step=%s stl=%s" % (solid.Volume, step, stl))
