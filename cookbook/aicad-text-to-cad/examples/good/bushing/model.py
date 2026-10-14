"""Flanged bushing — agent-written model for the text-to-cad demo.

Executed by cadgen 0.7.2 (`python3 model.py`): build123d builds the
geometry, the tool's runtime writes model.step and model.stl beside this
file.  Dimensions come from spec.txt.
"""
from cadgen import build123d as bd
from cadgen.authoring import step, stl

SHAFT_D = 20.0   # shaft diameter
SHAFT_H = 32.0   # shaft length above z=0
FLANGE_D = 36.0  # flange diameter
FLANGE_H = 8.0   # flange thickness
BORE_D = 10.0    # through bore


@step()
@stl()
def bushing():
    shaft = bd.Cylinder(
        radius=SHAFT_D / 2, height=SHAFT_H,
        align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
    )
    flange = bd.Pos(0, 0, SHAFT_H) * bd.Cylinder(
        radius=FLANGE_D / 2, height=FLANGE_H,
        align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
    )
    part = shaft + flange
    # bore must clear both ends so it is a real through hole
    bore = bd.Pos(0, 0, -1.0) * bd.Cylinder(
        radius=BORE_D / 2, height=SHAFT_H + FLANGE_H + 2.0,
        align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN),
    )
    return part - bore


if __name__ == "__main__":
    bushing()
