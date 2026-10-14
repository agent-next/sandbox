"""L-bracket with fillet — agent-written model for the text-to-cad demo.

Executed by cadgen 0.7.2 (`python3 model.py`): build123d builds the
geometry, the tool's runtime writes model.step and model.stl beside this
file.  Dimensions come from spec.txt.

The re-entrant corner fillet is drawn into the 2D profile as an explicit
R5 arc (tangent points (15,10) and (10,15), centre (15,15)) rather than
applied as a post-hoc fillet operation, so the delivered profile is the
spec geometry itself.
"""
from cadgen import build123d as bd
from cadgen.authoring import step, stl

WIDTH_X = 50.0    # overall width (x)
DEPTH_Y = 40.0    # extrusion depth (y)
HEIGHT_Z = 60.0   # overall height (z)
LEG_T = 10.0      # leg thickness
FILLET_R = 5.0    # inner-corner fillet radius
HOLE_D = 5.0      # mounting holes
# hole axes (x, z), drilled along Y
HOLES_XZ = [
    (5.0, 35.0),   # vertical leg
    (5.0, 55.0),   # vertical leg
    (25.0, 5.0),   # horizontal leg
    (45.0, 5.0),   # horizontal leg
]


@step()
@stl()
def bracket():
    with bd.BuildPart() as part:
        with bd.BuildSketch(bd.Plane.XZ) as profile:
            with bd.BuildLine():
                bd.Line((0, 0), (WIDTH_X, 0))
                bd.Line((WIDTH_X, 0), (WIDTH_X, LEG_T))
                bd.Line((WIDTH_X, LEG_T), (LEG_T + FILLET_R, LEG_T))
                # R5 fillet on the re-entrant corner: tangent at
                # (15,10) and (10,15), centre (15,15), concave
                bd.CenterArc((LEG_T + FILLET_R, LEG_T + FILLET_R), FILLET_R, -90, -90)
                bd.Line((LEG_T, LEG_T + FILLET_R), (LEG_T, HEIGHT_Z))
                bd.Line((LEG_T, HEIGHT_Z), (0, HEIGHT_Z))
                bd.Line((0, HEIGHT_Z), (0, 0))
            bd.make_face()
        # Plane.XZ extrudes towards -Y by default; -DEPTH_Y gives y = 0..40
        solid = bd.extrude(amount=-DEPTH_Y)
    # holes outside the builder context: plain boolean cuts
    for x, z in HOLES_XZ:
        hole = bd.Pos(x, DEPTH_Y / 2, z) * bd.Rot(90, 0, 0) * bd.Cylinder(
            radius=HOLE_D / 2, height=DEPTH_Y + 2.0,
            align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.CENTER),
        )
        solid = solid - hole
    return solid


if __name__ == "__main__":
    bracket()
