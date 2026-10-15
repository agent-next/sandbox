"""Adapter plate — agent-written model for the text-to-cad demo.

Executed by cadgen 0.7.2 (`python3 model.py`): build123d builds the
geometry, the tool's runtime writes model.step and model.stl beside this
file.  Dimensions come from spec.txt.
"""
from math import cos, sin, radians

from cadgen import build123d as bd
from cadgen.authoring import step, stl

PLATE_SIDE = 60.0      # square plate side
PLATE_T = 8.0          # thickness
CENTRE_BORE_D = 12.0   # centre through bore
BOLT_HOLE_D = 5.0      # bolt-circle holes
BOLT_CIRCLE_D = 44.0   # bolt-circle diameter
N_BOLT_HOLES = 4       # hole count
FIRST_ANGLE_DEG = 45.0 # first hole at 45°, then every 90°


@step()
@stl()
def adapter_plate():
    plate = bd.Box(
        PLATE_SIDE, PLATE_SIDE, PLATE_T,
        align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
    )
    # centre bore (positioned at mid-thickness so it clears both faces)
    plate = plate - bd.Pos(0, 0, PLATE_T / 2) * bd.Cylinder(
        radius=CENTRE_BORE_D / 2, height=PLATE_T + 2.0,
        align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.CENTER),
    )
    # bolt circle: FIRST_ANGLE_DEG, then every 360/N
    for i in range(N_BOLT_HOLES):
        ang = radians(FIRST_ANGLE_DEG + i * 360.0 / N_BOLT_HOLES)
        x = BOLT_CIRCLE_D / 2 * cos(ang)
        y = BOLT_CIRCLE_D / 2 * sin(ang)
        plate = plate - bd.Pos(x, y, PLATE_T / 2) * bd.Cylinder(
            radius=BOLT_HOLE_D / 2, height=PLATE_T + 2.0,
            align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.CENTER),
        )
    return plate


if __name__ == "__main__":
    adapter_plate()
