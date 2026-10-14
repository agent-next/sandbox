"""Spec table for the three graded cases + analytic oracles.

Single source of truth (with SPEC.md) for every dimension the judge gates
on.  The judge builds its reference solids from THESE constants only --
never from anything an artifact ships -- so a part can only pass by
actually matching the spec.

All dimensions mm, all angles degrees CCW from +x.
"""

import math

# OCCT (via OCP) is imported lazily so cases.py can also be read on
# machines without the judge venv.


def _cyl(x, y, z, dx, dy, dz, r, h):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder
    from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
    return BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(x, y, z), gp_Dir(dx, dy, dz)), r, h
    ).Shape()


def _box(x, y, z, dx, dy, dz):
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.gp import gp_Pnt
    return BRepPrimAPI_MakeBox(gp_Pnt(x, y, z), dx, dy, dz).Shape()


def _fuse(a, b, *rest):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse
    shape = BRepAlgoAPI_Fuse(a, b).Shape()
    for s in rest:
        shape = BRepAlgoAPI_Fuse(shape, s).Shape()
    return shape


def _cut(a, b):
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    return BRepAlgoAPI_Cut(a, b).Shape()


CASES = {}


# --------------------------------------------------------------------------
# bushing
# --------------------------------------------------------------------------
BUSHING = dict(
    name="bushing",
    bbox_expect=((-25.0, -25.0, 0.0), (25.0, 25.0, 30.0)),  # axis-centred
    volume_analytic=math.pi / 4.0
    * ((50**2 - 12**2) * 5.0 + (30**2 - 12**2) * 25.0),
    cyl_faces_expect=([6.0, 15.0, 25.0], 0.05),
    # spec rule: radial wall = r_body - r_bore
    min_wall=2.0,
)

CASES["bushing"] = BUSHING


def _bushing_body():
    return _cyl(0, 0, 0, 0, 0, 1, 15.0, 25.0)


def _bushing_flange():
    return _cyl(0, 0, 25, 0, 0, 1, 25.0, 5.0)


def _bushing_bore():
    return _cyl(0, 0, -1, 0, 0, 1, 6.0, 32.0)


def ref_bushing():
    return _cut(_fuse(_bushing_body(), _bushing_flange()), _bushing_bore())


# --------------------------------------------------------------------------
# plate
# --------------------------------------------------------------------------
PLATE = dict(
    name="plate",
    bbox_expect=((0.0, 0.0, 0.0), (80.0, 60.0, 8.0)),
    volume_analytic=80.0 * 60.0 * 8.0
    - math.pi / 4.0 * 20**2 * 8.0
    - 6 * math.pi / 4.0 * 6**2 * 8.0,
    cyl_faces_expect=([3.0] * 6 + [10.0], 0.05),
    bolt=dict(center=(40.0, 30.0), circle_r=24.0, hole_d=6.0,
              count=6, spacing_deg=60.0, first_deg=0.0),
    bore=dict(center=(40.0, 30.0), d=20.0),
    outline=(80.0, 60.0),
    # spec rules: ligaments bore-to-hole and hole-to-nearest-edge
    min_wall=2.0,
)

CASES["plate"] = PLATE


def _plate_bolts():
    import math as _m
    cx, cy = 40.0, 30.0
    return [
        _cyl(cx + 24.0 * _m.cos(_m.radians(i * 60.0)),
             cy + 24.0 * _m.sin(_m.radians(i * 60.0)),
             -1, 0, 0, 1, 3.0, 10.0)
        for i in range(6)
    ]


def ref_plate():
    solid = _box(0, 0, 0, 80.0, 60.0, 8.0)
    solid = _cut(solid, _cyl(40, 30, -1, 0, 0, 1, 10.0, 10.0))
    for hole in _plate_bolts():
        solid = _cut(solid, hole)
    return solid


# --------------------------------------------------------------------------
# bracket
# --------------------------------------------------------------------------
BASE = dict(l=60.0, w=40.0, t=6.0)
UPRIGHT = dict(t=6.0, h=40.0)  # height above the base -> z 6..46

BRACKET = dict(
    name="bracket",
    bbox_expect=((0.0, 0.0, 0.0), (60.0, 40.0, 46.0)),
    volume_analytic=BASE["l"] * BASE["w"] * BASE["t"]
    + UPRIGHT["t"] * BASE["w"] * UPRIGHT["h"]
    + 6**2 * (1 - math.pi / 4.0) * BASE["w"]
    - 4**2 * (1 - math.pi / 4.0) * BASE["w"],
    cyl_faces_expect=([4.0, 6.0], 0.05),
    min_wall=2.0,  # generic planar min-wall gate
)

CASES["bracket"] = BRACKET


def ref_bracket():
    l, w, t = BASE["l"], BASE["w"], BASE["t"]
    ut, uh = UPRIGHT["t"], UPRIGHT["h"]
    base = _box(0, 0, 0, l, w, t)
    upright = _box(l - ut, 0, t, ut, w, uh)
    # concave fillet: square x[l-ut-6, l-ut] z[t, t+6] minus quarter cyl
    # of R6 centred (l-ut-6, t+6) axis +y, full depth
    fr = 6.0
    cbox = _box(l - ut - fr, 0, t, fr, w, fr)
    ccyl = _cyl(l - ut - fr, 0, t + fr, 0, 1, 0, fr, w)
    concave = _cut(cbox, ccyl)
    solid = _fuse(base, upright, concave)
    # convex fillet: remove square x[l-4, l] z[46-4, 46] minus quarter cyl
    # of R4 centred (l-4, 46-4) axis +y
    er = 4.0
    ebox = _box(l - er, 0, t + uh - er, er, w, er)
    ecyl = _cyl(l - er, 0, t + uh - er, 0, 1, 0, er, w)
    return _cut(solid, _cut(ebox, ecyl))


def reference_solid(case):
    return {"bushing": ref_bushing, "plate": ref_plate,
            "bracket": ref_bracket}[case]()


def volume_analytic(case):
    return CASES[case]["volume_analytic"]
