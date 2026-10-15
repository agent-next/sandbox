#!/usr/bin/env python3
"""Write known-bad single-edit mutants of a good design.json.

Usage: mutants.py <examples/good dir> <out dir>

MUTANTS edit design.json (sketch + extrude); CSG_MUTANTS edit design-csg.json
(boxes and cylinders, whose rotated cylinders SolidCraft exports as B-spline
faces), so the judge's B-spline cylinder recognition is power-tested too.

Each mutant is one plausible modelling mistake an agent could make; the
self-test requires the judge to reject every one of them.
"""

from __future__ import annotations

import copy
import glob
import json
import math
import os
import sys
from pathlib import Path


def circles(cmds: list, diameter: float) -> list[dict]:
    return [c for c in cmds if c["command"] == "sketch.circle.center"
            and math.isclose(c["params"].get("diameter", -1), diameter)]


def param(cmds: list, name: str) -> dict:
    return next(c for c in cmds if c["command"] == "parameters.change" and c["params"]["name"] == name)


def bolt_holes(cmds):
    return circles(cmds, 3.4)


def hole_small(cmds):
    for c in bolt_holes(cmds):
        c["params"]["diameter"] = 3.1


def hole_off_pcd(cmds):
    c = bolt_holes(cmds)[0]["params"]
    c["center"] = [c["center"][0] + 0.2, c["center"][1] + 0.2]


def hole_rotated(cmds):
    c = bolt_holes(cmds)[0]["params"]
    r, a = math.hypot(*c["center"]), math.atan2(c["center"][1], c["center"][0]) + math.radians(3)
    c["center"] = [r * math.cos(a), r * math.sin(a)]


def hole_missing(cmds):
    cmds.remove(bolt_holes(cmds)[-1])


def hole_extra(cmds):
    i = cmds.index(bolt_holes(cmds)[-1])
    cmds.insert(i + 1, {"command": "sketch.circle.center", "params": {"center": [0, 17.5], "diameter": 3.4}})


def bore_missing(cmds):
    cmds.remove(circles(cmds, 22)[0])  # the plate sketch's bore; the boss keeps its own


def too_thick(cmds):
    param(cmds, "thickness")["params"]["expression"] = "7.5 mm"


def boss_height(cmds):
    param(cmds, "boss_height")["params"]["expression"] = "4 mm"


def no_fillet(cmds):
    c = next(c for c in cmds if c["command"] == "sketch.rectangle.rounded")
    c["command"] = "sketch.rectangle.two_point"
    del c["params"]["radius"]


def literal_thickness(cmds):
    for c in cmds:
        if c["command"] == "solid.extrude" and c["params"].get("distance") == "thickness":
            c["params"]["distance"] = "6 mm"
        if c["command"] == "sketch.create" and c["params"].get("offset") == "thickness":
            c["params"]["offset"] = "6 mm"


def broken_command(cmds):
    next(c for c in cmds if c["command"] == "solid.extrude")["command"] = "solid.extrudee"


def file_export(cmds):
    cmds.append({"command": "file.export", "params": {"path": "../../escape.step"}})


def holes_all_rotated(cmds):
    a = math.radians(10)  # spacing and PCD unchanged, the whole 31 mm square pattern turned
    for c in bolt_holes(cmds):
        x, y = c["params"]["center"]
        c["params"]["center"] = [x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)]


def font_outside(cmds):
    # sketch.text may name a font *file*; a real one outside the work dir, here
    # the judge venv's own DejaVu font.  The text sits off the part, so the
    # geometry is unchanged: only the command check can refuse it.
    font = sorted(glob.glob(os.path.expanduser(
        "~/.local/solidcraft-judge-venv/lib/python3*/site-packages/matplotlib/mpl-data/fonts/ttf/DejaVuSans.ttf")))
    i = next(i for i, c in enumerate(cmds) if c["command"] == "sketch.finish")
    cmds.insert(i, {"command": "sketch.text", "params": {
        "text": "X", "at": [100, 100], "font": font[0] if font else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"}})


def csg_bore_shifted(cmds):
    tool = next(c for c in cmds if c["params"].get("body_name") == "BoreTool")
    tool["params"]["base"] = [0.3, 0, 0]


def csg_corner_missing(cmds):
    i = next(i for i, c in enumerate(cmds) if c["command"] == "solid.combine"
             and c["params"].get("tools") == ["CornerNE"])
    del cmds[i]
    cmds.append({"command": "solid.remove", "params": {"bodies": ["CornerNE"]}})


def csg_blocked_holes(cmds):
    # a 0.5 mm web inside each bolt hole: +0.11 % volume (under the 0.2 % gate),
    # the hole's wall faces still span 0..T, but no bolt can pass
    for c in circles_csg(cmds, 3.4):
        x, y, _ = c["params"]["base"]
        cmds.append({"command": "solid.cylinder", "params": {
            "diameter": 3.5, "height": 0.5, "base": [x, y, 3], "operation": "join", "targets": ["MotorAdapter"]}})


def csg_thin_web(cmds):
    # a 0.1 mm web at z 3.1..3.2 inside each bolt hole: +0.02 % volume
    for c in circles_csg(cmds, 3.4):
        x, y, _ = c["params"]["base"]
        cmds.append({"command": "solid.cylinder", "params": {
            "diameter": 3.5, "height": 0.1, "base": [x, y, 3.1], "operation": "join", "targets": ["MotorAdapter"]}})


def csg_shift_on_rebuild(cmds):
    # unchanged at thickness 6; moves 20 mm sideways when the judge sets 8
    cmds.append({"command": "solid.move", "params": {
        "bodies": ["MotorAdapter"], "translate": ["10 * (thickness - 6 mm)", 0, 0]}})


def circles_csg(cmds, diameter):
    return [c for c in cmds if c["command"] == "solid.cylinder"
            and math.isclose(c["params"].get("diameter", -1), diameter)]


CSG_MUTANTS = [csg_bore_shifted, csg_corner_missing, csg_blocked_holes, csg_thin_web, csg_shift_on_rebuild]
MUTANTS = [hole_small, hole_off_pcd, hole_rotated, hole_missing, hole_extra, bore_missing,
           too_thick, boss_height, no_fillet, literal_thickness, broken_command, file_export,
           holes_all_rotated, font_outside]


def main() -> int:
    good_dir, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for src, fns in (("design.json", MUTANTS), ("design-csg.json", CSG_MUTANTS)):
        good = json.loads((good_dir / src).read_text())
        for fn in fns:
            d = copy.deepcopy(good)
            fn(d["commands"])
            if d == good:
                print(f"mutants: {fn.__name__} made no change", file=sys.stderr)
                return 1
            (out / f"{fn.__name__}.json").write_text(json.dumps(d, indent=1) + "\n")
            print(f"mutants: wrote {fn.__name__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
